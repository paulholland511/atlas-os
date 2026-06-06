"""Tests for eidetic_os.memory_tiers — tiered memory architecture (#31).

The tier policy is pure and offline: it reads each fact's ``relevance_score`` and
writes its ``tier`` column, so every test here drives a real (embedder-free)
:class:`~eidetic_os.facts.FactStore` with relevance scores set explicitly. That
keeps the score→tier mapping, the promote/demote walk, the limit-enforcing
compaction, and the fact-store integration all deterministic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eidetic_os import facts
from eidetic_os.memory_tiers import (
    CORE_THRESHOLD,
    RECALL_THRESHOLD,
    MemoryTier,
    TieredMemory,
    tier_for_score,
)


@pytest.fixture()
def store(tmp_path: Path) -> facts.FactStore:
    s = facts.FactStore(tmp_path / "facts.db")  # offline: no embedder
    yield s
    s.close()


@pytest.fixture()
def tiers(store: facts.FactStore) -> TieredMemory:
    return TieredMemory(store=store, core_limit=3, recall_limit=5)


def _add(store: facts.FactStore, text: str, *, score: float) -> int:
    """Add a fact and pin its relevance score (no scoring pass needed)."""
    fid = store.add_fact(text)
    store.set_relevance(fid, score)
    return fid


# ── the pure score→tier mapping ────────────────────────────────────────────────
class TestTierForScore:
    def test_high_score_is_core(self) -> None:
        assert tier_for_score(0.9) is MemoryTier.CORE

    def test_mid_score_is_recall(self) -> None:
        assert tier_for_score(0.5) is MemoryTier.RECALL

    def test_low_score_is_archival(self) -> None:
        assert tier_for_score(0.1) is MemoryTier.ARCHIVAL

    def test_boundaries_are_inclusive_to_recall(self) -> None:
        # > 0.7 is core, so exactly 0.7 is recall; 0.3 is the bottom of recall.
        assert tier_for_score(CORE_THRESHOLD) is MemoryTier.RECALL
        assert tier_for_score(RECALL_THRESHOLD) is MemoryTier.RECALL

    def test_just_above_core_threshold_is_core(self) -> None:
        assert tier_for_score(CORE_THRESHOLD + 0.001) is MemoryTier.CORE

    def test_just_below_recall_threshold_is_archival(self) -> None:
        assert tier_for_score(RECALL_THRESHOLD - 0.001) is MemoryTier.ARCHIVAL


# ── auto-tiering from scores ───────────────────────────────────────────────────
class TestAutoTier:
    def test_assigns_each_fact_its_score_tier(
        self, store: facts.FactStore, tiers: TieredMemory
    ) -> None:
        hot = _add(store, "hot fact", score=0.95)
        warm = _add(store, "warm fact", score=0.5)
        cold = _add(store, "cold fact", score=0.05)

        tally = tiers.auto_tier()

        assert store.get(hot).tier == "core"
        assert store.get(warm).tier == "recall"
        assert store.get(cold).tier == "archival"
        assert tally["core"] == 1
        assert tally["recall"] == 1
        assert tally["archival"] == 1

    def test_reports_only_changed_rows_as_moved(
        self, store: facts.FactStore, tiers: TieredMemory
    ) -> None:
        # A fresh fact defaults to recall; a mid score keeps it there (no move).
        _add(store, "stays in recall", score=0.5)
        _add(store, "promotes to core", score=0.9)

        moved = tiers.auto_tier()["moved"]
        assert moved == 1  # only the core promotion rewrote a row

    def test_is_idempotent(
        self, store: facts.FactStore, tiers: TieredMemory
    ) -> None:
        _add(store, "hot", score=0.9)
        tiers.auto_tier()
        assert tiers.auto_tier()["moved"] == 0  # second pass changes nothing


# ── manual promote / demote ────────────────────────────────────────────────────
class TestPromoteDemote:
    def test_promote_walks_archival_to_recall_to_core(
        self, store: facts.FactStore, tiers: TieredMemory
    ) -> None:
        fid = _add(store, "fact", score=0.05)
        tiers.auto_tier()  # lands in archival
        assert store.get(fid).tier == "archival"

        assert tiers.promote(fid) is MemoryTier.RECALL
        assert store.get(fid).tier == "recall"
        assert tiers.promote(fid) is MemoryTier.CORE
        assert store.get(fid).tier == "core"

    def test_promote_caps_at_core(
        self, store: facts.FactStore, tiers: TieredMemory
    ) -> None:
        fid = _add(store, "fact", score=0.95)
        tiers.auto_tier()  # core
        assert tiers.promote(fid) is MemoryTier.CORE  # stays, no error
        assert store.get(fid).tier == "core"

    def test_demote_walks_core_to_recall_to_archival(
        self, store: facts.FactStore, tiers: TieredMemory
    ) -> None:
        fid = _add(store, "fact", score=0.95)
        tiers.auto_tier()  # core
        assert tiers.demote(fid) is MemoryTier.RECALL
        assert tiers.demote(fid) is MemoryTier.ARCHIVAL
        assert tiers.demote(fid) is MemoryTier.ARCHIVAL  # caps at archival

    def test_promote_unknown_fact_returns_none(self, tiers: TieredMemory) -> None:
        assert tiers.promote(999) is None
        assert tiers.demote(999) is None

    def test_demote_ignores_inactive_fact(
        self, store: facts.FactStore, tiers: TieredMemory
    ) -> None:
        fid = _add(store, "fact", score=0.9)
        store.deactivate(fid)
        assert tiers.demote(fid) is None


# ── compaction + limit enforcement ─────────────────────────────────────────────
class TestCompact:
    def test_demotes_core_overflow_coldest_first(
        self, store: facts.FactStore, tiers: TieredMemory
    ) -> None:
        # core_limit is 3; create 5 core-eligible facts with distinct scores.
        ids = [
            _add(store, f"core fact {i}", score=0.8 + i * 0.02) for i in range(5)
        ]
        result = tiers.compact()

        # The 3 highest-scoring stay in core; the 2 coldest spill to recall.
        kept = {f.id for f in store.facts_in_tier("core")}
        assert kept == {ids[4], ids[3], ids[2]}
        assert result.demoted_core == 2
        assert store.get(ids[0]).tier == "recall"
        assert store.get(ids[1]).tier == "recall"

    def test_recall_overflow_spills_to_archival(
        self, store: facts.FactStore, tiers: TieredMemory
    ) -> None:
        # recall_limit is 5. Make 7 recall-band facts → 2 spill to archival.
        for i in range(7):
            _add(store, f"recall fact {i}", score=0.4 + i * 0.001)
        result = tiers.compact()

        assert result.stats.counts["recall"] == 5
        assert result.stats.counts["archival"] == 2
        assert result.demoted_recall == 2

    def test_core_overflow_counts_against_recall_limit(
        self, store: facts.FactStore, tiers: TieredMemory
    ) -> None:
        # 5 core-band facts (limit 3 → 2 spill to recall) plus 4 recall-band
        # facts. Recall then holds 6, over its limit of 5 → 1 spills to archival.
        for i in range(5):
            _add(store, f"core {i}", score=0.85 + i * 0.01)
        for i in range(4):
            _add(store, f"recall {i}", score=0.4 + i * 0.001)
        result = tiers.compact()

        assert result.stats.counts["core"] == 3
        assert result.stats.counts["recall"] == 5
        assert result.stats.counts["archival"] == 1
        assert result.demoted_recall == 1

    def test_under_limit_demotes_nothing(
        self, store: facts.FactStore, tiers: TieredMemory
    ) -> None:
        _add(store, "a", score=0.9)
        _add(store, "b", score=0.5)
        result = tiers.compact()
        assert result.demoted_core == 0
        assert result.demoted_recall == 0


# ── stats ───────────────────────────────────────────────────────────────────────
class TestStats:
    def test_counts_sizes_and_limits(
        self, store: facts.FactStore, tiers: TieredMemory
    ) -> None:
        _add(store, "hot", score=0.9)
        _add(store, "warm one", score=0.5)
        _add(store, "cold", score=0.05)
        tiers.auto_tier()

        s = tiers.stats()
        assert s.counts == {"core": 1, "recall": 1, "archival": 1}
        assert s.total == 3
        assert s.sizes["core"] == len("hot")
        assert s.sizes["recall"] == len("warm one")
        assert s.limits == {"core": 3, "recall": 5, "archival": None}

    def test_empty_store_is_all_zeros(self, tiers: TieredMemory) -> None:
        s = tiers.stats()
        assert s.total == 0
        assert s.counts == {"core": 0, "recall": 0, "archival": 0}

    def test_as_dict_is_json_shaped(
        self, store: facts.FactStore, tiers: TieredMemory
    ) -> None:
        _add(store, "hot", score=0.9)
        tiers.auto_tier()
        view = tiers.as_dict()
        assert set(view) == {"counts", "sizes", "limits", "total"}
        assert view["total"] == 1


# ── fact-store integration ──────────────────────────────────────────────────────
class TestFactStoreIntegration:
    def test_new_facts_default_to_recall(self, store: facts.FactStore) -> None:
        fid = store.add_fact("a fresh fact")
        assert store.get(fid).tier == "recall"

    def test_tier_column_added_to_legacy_store(self, tmp_path: Path) -> None:
        # A store created without the tier column (simulating a pre-#31 db) gains
        # it on the next open via the additive migration.
        import sqlite3

        db = tmp_path / "legacy.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE facts ("
            "id INTEGER PRIMARY KEY, fact TEXT NOT NULL, source TEXT DEFAULT '', "
            "created_at TIMESTAMP NOT NULL, last_accessed TIMESTAMP NOT NULL, "
            "access_count INTEGER NOT NULL DEFAULT 0, confidence REAL NOT NULL DEFAULT 0.6, "
            "category TEXT NOT NULL DEFAULT 'other', embedding BLOB, "
            "active INTEGER NOT NULL DEFAULT 1)"
        )
        conn.execute(
            "INSERT INTO facts(fact, created_at, last_accessed) VALUES('old', 'x', 'x')"
        )
        conn.commit()
        conn.close()

        s = facts.FactStore(db)
        try:
            stored = s.list_facts(active_only=False)[0]
            assert stored.tier == "recall"  # default backfilled
        finally:
            s.close()

    def test_facts_in_tier_orders_by_relevance(self, store: facts.FactStore) -> None:
        low = _add(store, "low", score=0.9)
        high = _add(store, "high", score=0.95)
        store.set_tier(low, "core")
        store.set_tier(high, "core")
        ordered = store.facts_in_tier("core")
        assert [f.id for f in ordered] == [high, low]

    def test_get_recall_searches_only_recall_tier(
        self, store: facts.FactStore, tiers: TieredMemory
    ) -> None:
        recall = _add(store, "kelly criterion sizing", score=0.5)
        archival = _add(store, "kelly criterion archived", score=0.05)
        tiers.auto_tier()

        hits = tiers.get_recall("kelly criterion", limit=10)
        ids = {fact.id for fact, _ in hits}
        assert recall in ids
        assert archival not in ids

    def test_get_archival_searches_only_archival_tier(
        self, store: facts.FactStore, tiers: TieredMemory
    ) -> None:
        recall = _add(store, "kelly criterion sizing", score=0.5)
        archival = _add(store, "kelly criterion archived", score=0.05)
        tiers.auto_tier()

        hits = tiers.get_archival("kelly criterion", limit=10)
        ids = {fact.id for fact, _ in hits}
        assert archival in ids
        assert recall not in ids

    def test_get_core_returns_core_facts(
        self, store: facts.FactStore, tiers: TieredMemory
    ) -> None:
        core = _add(store, "always-on fact", score=0.9)
        _add(store, "warm fact", score=0.5)
        tiers.auto_tier()
        assert [f.id for f in tiers.get_core()] == [core]

    def test_stats_exposed_on_fact_store(self, store: facts.FactStore) -> None:
        _add(store, "fact", score=0.5)
        assert "by_tier" in store.stats()
        assert store.stats()["by_tier"].get("recall") == 1


# ── construction ────────────────────────────────────────────────────────────────
class TestConstruction:
    def test_opens_store_from_vault_path(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        with TieredMemory(vault) as tm:
            fid = tm.store.add_fact("fact in vault store")
            assert tm.store.get(fid).tier == "recall"
        # The db was created under the conventional location.
        assert (vault / ".eidetic" / "facts.db").exists()

    def test_requires_vault_or_store(self) -> None:
        with pytest.raises(ValueError):
            TieredMemory()

    def test_injected_store_not_closed_by_manager(
        self, store: facts.FactStore
    ) -> None:
        tm = TieredMemory(store=store)
        tm.close()  # must NOT close an injected store
        assert store.count(active_only=False) == 0  # still usable, no error
