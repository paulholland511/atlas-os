"""Tiered memory architecture — Core / Recall / Archival (Feature #31).

The fact store (:mod:`eidetic_os.facts`) keeps every fact in one flat table and
the memory scorer (:mod:`eidetic_os.memory_scoring`, Feature #27) tells us *how
live* each one is. This module layers Letta-inspired **tiers** on top of that
signal, so the store behaves like a memory hierarchy rather than a single pool:

* **Core** — the hot working set. Small (``core_limit`` facts) and always
  injected into context. These are the things the assistant should "just know".
* **Recall** — the warm cache of recent / moderately-relevant facts. Larger
  (``recall_limit``), searched on demand rather than always loaded.
* **Archival** — cold storage. Unbounded; everything that has decayed out of the
  working set still lives here and is reachable by explicit search.

A fact's tier is just a column on its row (``facts.tier``); this manager owns the
*policy* that moves facts between tiers. Tiering is driven by the relevance score
the #27 scorer already maintains:

    score  > 0.7          → CORE
    0.3 <= score <= 0.7   → RECALL
    score  < 0.3          → ARCHIVAL

:meth:`TieredMemory.auto_tier` applies that mapping to every active fact;
:meth:`~TieredMemory.compact` runs it and then enforces the tier *size limits*,
demoting the least-relevant overflow (Core → Recall → Archival) so the hot set
stays small. The sleeptime consolidation daemon calls ``compact`` on every pass,
so tiers stay balanced as a background side effect — exactly like the decay pass.

Everything here is synchronous and offline: the policy needs only the
``relevance_score`` and ``tier`` columns already on each row, so a ``TieredMemory``
opened with no embedder works fully locally. ``promote``/``demote`` give manual
control for the cases the automatic policy gets wrong.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final

from eidetic_os.facts import FactStore, StoredFact


class MemoryTier(str, Enum):
    """The three memory tiers, hottest to coldest.

    A ``str`` enum so the value round-trips straight to/from the ``facts.tier``
    column and serialises cleanly to JSON (``MemoryTier.CORE == "core"``).
    """

    CORE = "core"
    RECALL = "recall"
    ARCHIVAL = "archival"


# Coldest-to-hottest ordering, so promotion walks right and demotion walks left.
_TIER_ORDER: Final[tuple[MemoryTier, ...]] = (
    MemoryTier.ARCHIVAL,
    MemoryTier.RECALL,
    MemoryTier.CORE,
)

# Relevance-score cutoffs for :meth:`TieredMemory.auto_tier`. ``> CORE_THRESHOLD``
# is core; ``< RECALL_THRESHOLD`` is archival; the band between (inclusive) is
# recall — matching the documented mapping.
CORE_THRESHOLD: Final = 0.7
RECALL_THRESHOLD: Final = 0.3

DEFAULT_CORE_LIMIT: Final = 50
DEFAULT_RECALL_LIMIT: Final = 500


def tier_for_score(score: float) -> MemoryTier:
    """The tier a fact with this relevance ``score`` belongs in (pure)."""
    if score > CORE_THRESHOLD:
        return MemoryTier.CORE
    if score < RECALL_THRESHOLD:
        return MemoryTier.ARCHIVAL
    return MemoryTier.RECALL


def _coerce_tier(value: str | MemoryTier) -> MemoryTier:
    """Normalise a tier name (or enum) to a :class:`MemoryTier`."""
    if isinstance(value, MemoryTier):
        return value
    return MemoryTier(str(value).strip().lower())


@dataclass(frozen=True)
class TierStats:
    """A snapshot of tier occupancy for ``eidetic memory tiers``.

    ``counts`` is active facts per tier; ``sizes`` is the total character length
    of those facts' text per tier (a rough proxy for context cost); ``limits``
    echoes the configured ceilings (``None`` for the unbounded archival tier).
    """

    counts: dict[str, int]
    sizes: dict[str, int]
    limits: dict[str, int | None]
    total: int


@dataclass(frozen=True)
class CompactionResult:
    """The outcome of a :meth:`TieredMemory.compact` pass.

    ``retiered`` is how many facts ``auto_tier`` moved by score; ``demoted_core``
    and ``demoted_recall`` are how many were pushed down to honour the Core and
    Recall size limits. ``stats`` is the resulting :class:`TierStats`.
    """

    retiered: int
    demoted_core: int
    demoted_recall: int
    stats: TierStats


class TieredMemory:
    """Assign and rebalance fact tiers over a :class:`~eidetic_os.facts.FactStore`.

    Construct against a vault directory — ``TieredMemory(vault_path)`` opens the
    conventional fact store at ``<vault>/.eidetic/facts.db`` (offline, no
    embedder) — or inject an open store directly with ``store=`` (tests and
    callers that already hold one do this). The two size limits bound the hot
    Core set and the warm Recall cache; Archival is unbounded cold storage.
    """

    def __init__(
        self,
        vault_path: str | Path | None = None,
        core_limit: int = DEFAULT_CORE_LIMIT,
        recall_limit: int = DEFAULT_RECALL_LIMIT,
        *,
        store: FactStore | None = None,
    ) -> None:
        if store is None and vault_path is None:
            raise ValueError("provide either vault_path or store")
        self.core_limit = core_limit
        self.recall_limit = recall_limit
        self._owns_store = store is None
        self.store = store if store is not None else self._open_store(vault_path)

    @staticmethod
    def _open_store(vault_path: str | Path | None) -> FactStore:
        base = Path(os.path.expanduser(str(vault_path)))
        db_path = base / ".eidetic" / "facts.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return FactStore(db_path)  # offline: tiering needs no embedder

    # ── lifecycle ───────────────────────────────────────────────────────────────
    def close(self) -> None:
        """Close the underlying store — only if this manager opened it."""
        if self._owns_store:
            self.store.close()

    def __enter__(self) -> TieredMemory:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── manual movement ──────────────────────────────────────────────────────────
    def promote(self, fact_id: int) -> MemoryTier | None:
        """Move a fact one tier hotter (archival→recall→core). Returns the new tier.

        A fact already in Core stays in Core. Returns ``None`` if no fact has
        that id (or it is inactive).
        """
        return self._shift(fact_id, +1)

    def demote(self, fact_id: int) -> MemoryTier | None:
        """Move a fact one tier colder (core→recall→archival). Returns the new tier.

        A fact already in Archival stays in Archival. Returns ``None`` if no fact
        has that id (or it is inactive).
        """
        return self._shift(fact_id, -1)

    def _shift(self, fact_id: int, direction: int) -> MemoryTier | None:
        fact = self.store.get(fact_id)
        if fact is None or not fact.active:
            return None
        current = _coerce_tier(fact.tier)
        index = _TIER_ORDER.index(current)
        target = min(len(_TIER_ORDER) - 1, max(0, index + direction))
        new_tier = _TIER_ORDER[target]
        if new_tier is not current:
            self.store.set_tier(fact_id, new_tier.value)
        return new_tier

    # ── automatic tiering ────────────────────────────────────────────────────────
    def auto_tier(self) -> dict[str, int]:
        """Assign every active fact a tier from its relevance score.

        Applies the documented score→tier mapping (see :func:`tier_for_score`) to
        each active fact, writing only the rows whose tier actually changes.
        Returns a tally keyed by tier name plus ``"moved"`` (rows rewritten) — the
        scorer should have run first so the relevance scores are current.
        """
        tally = {t.value: 0 for t in MemoryTier}
        tally["moved"] = 0
        for fact in self.store.active_facts():
            target = tier_for_score(fact.relevance_score)
            tally[target.value] += 1
            if _coerce_tier(fact.tier) is not target:
                self.store.set_tier(fact.id, target.value)
                tally["moved"] += 1
        return tally

    # ── reads ─────────────────────────────────────────────────────────────────────
    def get_core(self) -> list[StoredFact]:
        """All Core facts, most relevant first — the context-injection set."""
        return self.store.facts_in_tier(MemoryTier.CORE.value)

    def get_recall(
        self, query: str, limit: int = 10
    ) -> list[tuple[StoredFact, float]]:
        """Search the Recall tier for ``query``; ``(fact, score)`` best-first."""
        return self.store.query_facts(query, limit=limit, tier=MemoryTier.RECALL.value)

    def get_archival(
        self, query: str, limit: int = 10
    ) -> list[tuple[StoredFact, float]]:
        """Search the Archival (cold) tier for ``query``; ``(fact, score)`` best-first."""
        return self.store.query_facts(
            query, limit=limit, tier=MemoryTier.ARCHIVAL.value
        )

    # ── compaction ────────────────────────────────────────────────────────────────
    def compact(self) -> CompactionResult:
        """Re-tier by score, then demote overflow to honour the size limits.

        Runs :meth:`auto_tier`, then — if Core holds more than ``core_limit`` —
        demotes the least-relevant overflow to Recall, and likewise spills any
        Recall overflow beyond ``recall_limit`` down to Archival (which is
        unbounded). Demotion always sheds the *coldest* facts first, so the hot
        set keeps the most relevant. Returns a :class:`CompactionResult`.
        """
        moved = self.auto_tier()["moved"]
        demoted_core = self._enforce_limit(MemoryTier.CORE, MemoryTier.RECALL, self.core_limit)
        # Spill happens after Core overflow lands in Recall, so the freshly
        # demoted facts count against the Recall ceiling too.
        demoted_recall = self._enforce_limit(
            MemoryTier.RECALL, MemoryTier.ARCHIVAL, self.recall_limit
        )
        return CompactionResult(
            retiered=moved,
            demoted_core=demoted_core,
            demoted_recall=demoted_recall,
            stats=self.stats(),
        )

    def _enforce_limit(
        self, tier: MemoryTier, spill_to: MemoryTier, limit: int
    ) -> int:
        """Demote the coldest overflow of ``tier`` into ``spill_to``; return how many."""
        facts = self.store.facts_in_tier(tier.value)  # relevance DESC
        overflow = facts[limit:] if limit >= 0 else []
        for fact in overflow:
            self.store.set_tier(fact.id, spill_to.value)
        return len(overflow)

    # ── introspection ─────────────────────────────────────────────────────────────
    def stats(self) -> TierStats:
        """Current tier occupancy: counts, byte sizes, and the configured limits."""
        counts = {t.value: 0 for t in MemoryTier}
        sizes = {t.value: 0 for t in MemoryTier}
        for fact in self.store.active_facts():
            key = _coerce_tier(fact.tier).value
            counts[key] += 1
            sizes[key] += len(fact.fact)
        limits: dict[str, int | None] = {
            MemoryTier.CORE.value: self.core_limit,
            MemoryTier.RECALL.value: self.recall_limit,
            MemoryTier.ARCHIVAL.value: None,
        }
        return TierStats(
            counts=counts,
            sizes=sizes,
            limits=limits,
            total=sum(counts.values()),
        )

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly view of :meth:`stats` (for ``--json`` CLI output)."""
        s = self.stats()
        return {
            "counts": s.counts,
            "sizes": s.sizes,
            "limits": s.limits,
            "total": s.total,
        }
