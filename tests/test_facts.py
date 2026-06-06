"""Tests for eidetic_os.facts — Mem0-style extraction and the fact store.

The store's semantic dedup/search paths are exercised with a deterministic
bag-of-content-words stand-in for a real embedder (:class:`FakeEmbedder`), so the
tests are fully offline and reproducible. The heuristic extractor and the
token-overlap fallback are tested without any embedder at all.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from eidetic_os import facts


class FakeEmbedder:
    """A deterministic bag-of-content-words embedder.

    Each distinct content word gets a fixed slot; a text's vector is the
    indicator over its content words. Two texts that differ only in stopwords (or
    a negation cue, which is a stopword here) map to identical vectors — exactly
    the case real embeddings collapse and the dedup logic must handle.
    """

    def __init__(self) -> None:
        self.vocab: dict[str, int] = {}

    def __call__(self, texts):
        for text in texts:
            for word in facts._content_tokens(text):
                self.vocab.setdefault(word, len(self.vocab))
        dim = max(8, len(self.vocab))
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * dim
            for word in facts._content_tokens(text):
                vec[self.vocab[word]] = 1.0
            out.append(vec)
        return out


@pytest.fixture()
def store(tmp_path: Path) -> facts.FactStore:
    s = facts.FactStore(tmp_path / "facts.db", embed_fn=FakeEmbedder())
    yield s
    s.close()


@pytest.fixture()
def offline_store(tmp_path: Path) -> facts.FactStore:
    """A store with no embedder — token-overlap similarity path."""
    s = facts.FactStore(tmp_path / "facts_offline.db")
    yield s
    s.close()


# ── CRUD ──────────────────────────────────────────────────────────────────────
class TestCrud:
    def test_add_and_get(self, store: facts.FactStore) -> None:
        fid = store.add_fact("Paul uses uv", "chat.md", category="technical", confidence=0.8)
        got = store.get(fid)
        assert got is not None
        assert got.fact == "Paul uses uv"
        assert got.source == "chat.md"
        assert got.category == "technical"
        assert got.confidence == 0.8
        assert got.active is True
        assert got.access_count == 0

    def test_unknown_category_falls_back_to_other(self, store: facts.FactStore) -> None:
        fid = store.add_fact("something", category="nonsense")
        assert store.get(fid).category == "other"

    def test_confidence_is_clamped(self, store: facts.FactStore) -> None:
        hi = store.get(store.add_fact("a", confidence=5.0))
        lo = store.get(store.add_fact("b", confidence=-1.0))
        assert hi.confidence == 1.0
        assert lo.confidence == 0.0

    def test_touch_bumps_access(self, store: facts.FactStore) -> None:
        fid = store.add_fact("x")
        store.touch(fid)
        store.touch(fid)
        assert store.get(fid).access_count == 2

    def test_deactivate_is_soft_delete(self, store: facts.FactStore) -> None:
        fid = store.add_fact("x")
        store.deactivate(fid)
        assert store.get(fid).active is False
        assert store.count() == 0  # active-only
        assert store.count(active_only=False) == 1

    def test_count_and_clear(self, store: facts.FactStore) -> None:
        store.add_fact("a")
        store.add_fact("b")
        assert store.count() == 2
        store.clear()
        assert store.count() == 0

    def test_list_filters_by_category(self, store: facts.FactStore) -> None:
        store.add_fact("a pref", category="preference")
        store.add_fact("a tech", category="technical")
        prefs = store.list_facts(category="preference")
        assert len(prefs) == 1
        assert prefs[0].category == "preference"

    def test_list_newest_first(self, store: facts.FactStore) -> None:
        first = store.add_fact("first")
        second = store.add_fact("second")
        ids = [f.id for f in store.list_facts()]
        assert ids == [second, first]


# ── Heuristic extraction ──────────────────────────────────────────────────────
class TestHeuristicExtraction:
    def test_decision_is_caught(self) -> None:
        out = facts.extract_facts_heuristic("We decided to use Postgres for storage.")
        assert len(out) == 1
        assert out[0].category == "decision"

    def test_preference_is_caught(self) -> None:
        out = facts.extract_facts_heuristic("I prefer bullet lists over tables.")
        assert out[0].category == "preference"

    def test_technical_version_is_caught(self) -> None:
        out = facts.extract_facts_heuristic("The service runs Python 3.13 on localhost:5555.")
        assert out[0].category == "technical"

    def test_questions_are_ignored(self) -> None:
        assert facts.extract_facts_heuristic("How should we handle errors here?") == []

    def test_short_fragments_are_ignored(self) -> None:
        assert facts.extract_facts_heuristic("ok") == []

    def test_duplicate_sentences_collapse(self) -> None:
        text = "We decided to use uv. We decided to use uv."
        assert len(facts.extract_facts_heuristic(text)) == 1

    def test_markdown_noise_is_stripped(self) -> None:
        out = facts.extract_facts_heuristic("- We decided to adopt the new schema.")
        assert out[0].fact.startswith("We decided")

    def test_empty_text(self) -> None:
        assert facts.extract_facts("") == []
        assert facts.extract_facts("   \n  ") == []

    def test_extract_dispatches_to_heuristic_without_llm(self) -> None:
        out = facts.extract_facts(
            "We chose Rust for the parser.", "src.md", use_llm=False
        )
        assert out and out[0].category == "decision"


# ── LLM extraction parsing (no network) ───────────────────────────────────────
class TestLlmParsing:
    def test_extract_json_array_plain(self) -> None:
        payload = facts._extract_json_array('[{"fact":"x","category":"technical"}]')
        assert payload == [{"fact": "x", "category": "technical"}]

    def test_extract_json_array_fenced(self) -> None:
        content = '```json\n[{"fact":"x"}]\n```'
        assert facts._extract_json_array(content) == [{"fact": "x"}]

    def test_extract_json_array_with_prose(self) -> None:
        content = 'Sure! Here are the facts:\n[{"fact":"x"}]\nHope that helps.'
        assert facts._extract_json_array(content) == [{"fact": "x"}]

    def test_extract_json_array_invalid(self) -> None:
        assert facts._extract_json_array("not json at all") is None

    def test_facts_from_payload_normalises(self) -> None:
        payload = [
            {"fact": "  spaced  out ", "category": "PREFERENCE", "confidence": "0.9"},
            {"fact": "", "category": "decision"},  # dropped (empty)
            {"fact": "bad conf", "confidence": "oops"},  # confidence default
            "not a dict",  # ignored
        ]
        out = facts._facts_from_payload(payload)
        assert len(out) == 2
        assert out[0].fact == "spaced out"
        assert out[0].category == "preference"
        assert out[0].confidence == 0.9

    def test_extract_facts_llm_handles_unreachable(self) -> None:
        class DeadClient:
            model = "m"
            chat_url = "http://127.0.0.1:1/v1/chat/completions"

            def headers(self):
                return {}

        # Connection refused → None (so the caller falls back), never raises.
        assert facts.extract_facts_llm("text", DeadClient(), timeout=0.2) is None


# ── Relation classification ───────────────────────────────────────────────────
class TestClassifyRelation:
    def test_identical_is_duplicate(self) -> None:
        assert facts.classify_relation("a b c", "a b c", 0.99) == "duplicate"

    def test_high_similarity_is_duplicate(self) -> None:
        assert facts.classify_relation("a b c d", "a b c e", 0.98) == "duplicate"

    def test_polarity_flip_is_supersede(self) -> None:
        rel = facts.classify_relation(
            "the api is not deprecated", "the api is deprecated", 0.9
        )
        assert rel == "supersede"

    def test_containment_is_merge(self) -> None:
        rel = facts.classify_relation(
            "Paul prefers uv for packages", "Paul prefers uv", 0.9
        )
        assert rel == "merge"

    def test_polarity_helper(self) -> None:
        assert facts._polarity("we do not use pip") is True
        assert facts._polarity("we use pip") is False
        assert facts._polarity("never deploy on friday") is True


# ── Deduplication ─────────────────────────────────────────────────────────────
class TestDeduplicate:
    def test_first_fact_inserts(self, store: facts.FactStore) -> None:
        ex = [facts.ExtractedFact("Paul uses uv", "technical", 0.7)]
        assert store.ingest(ex, "a.md") == {
            "inserted": 1, "duplicate": 0, "superseded": 0, "merged": 0
        }
        assert store.count() == 1

    def test_exact_duplicate_bumps_existing(self, store: facts.FactStore) -> None:
        ex = [facts.ExtractedFact("user prefers dark mode", "preference", 0.7)]
        store.ingest(ex, "a.md")
        tally = store.ingest(ex, "b.md")
        assert tally["duplicate"] == 1
        assert store.count() == 1  # not duplicated
        # The surviving fact recorded the re-access.
        assert store.list_facts()[0].access_count >= 1

    def test_contradiction_supersedes(self, store: facts.FactStore) -> None:
        store.ingest([facts.ExtractedFact("the database is encrypted", "technical", 0.8)], "a.md")
        tally = store.ingest(
            [facts.ExtractedFact("the database is not encrypted", "technical", 0.8)], "b.md"
        )
        assert tally["superseded"] == 1
        assert store.count() == 1  # only the new one is active
        assert store.count(active_only=False) == 2  # the old one is retained
        assert store.list_facts()[0].fact == "the database is not encrypted"

    def test_extension_merges(self, store: facts.FactStore) -> None:
        store.ingest([facts.ExtractedFact("Paul prefers uv", "preference", 0.6)], "a.md")
        tally = store.ingest(
            [facts.ExtractedFact("Paul prefers uv strongly", "preference", 0.7)], "b.md"
        )
        assert tally["merged"] == 1
        assert store.count() == 1
        # The merged fact keeps the more informative (longer) statement.
        assert "strongly" in store.list_facts()[0].fact

    def test_unrelated_facts_coexist(self, store: facts.FactStore) -> None:
        store.ingest([facts.ExtractedFact("Paul lives in London", "person", 0.7)], "a.md")
        store.ingest([facts.ExtractedFact("the bot uses Kelly sizing", "project", 0.7)], "b.md")
        assert store.count() == 2

    def test_threshold_controls_sensitivity(self, store: facts.FactStore) -> None:
        store.add_fact("the cache layer is redis", category="technical")
        # A different fact sharing a couple of words: at threshold 1.0 nothing
        # ever dedups, so it must insert.
        result = store.deduplicate("the queue layer is redis", threshold=1.0)
        assert result.action == "insert"

    def test_offline_exact_duplicate(self, offline_store: facts.FactStore) -> None:
        ex = [facts.ExtractedFact("we ship on fridays", "decision", 0.6)]
        offline_store.ingest(ex, "a.md")
        tally = offline_store.ingest(ex, "b.md")  # token Jaccard == 1.0
        assert tally["duplicate"] == 1
        assert offline_store.count() == 1


# ── Query / search ────────────────────────────────────────────────────────────
class TestQuery:
    def test_semantic_search_ranks_relevant_first(self, store: facts.FactStore) -> None:
        store.add_fact("the database is encrypted", category="technical")
        store.add_fact("Paul enjoys mountain biking", category="person")
        results = store.query_facts("is the database encrypted", limit=5)
        assert results
        assert results[0][0].fact == "the database is encrypted"
        assert results[0][1] > 0

    def test_search_records_access(self, store: facts.FactStore) -> None:
        fid = store.add_fact("the database is encrypted", category="technical")
        store.query_facts("database encrypted")
        assert store.get(fid).access_count == 1

    def test_search_can_skip_access(self, store: facts.FactStore) -> None:
        fid = store.add_fact("the database is encrypted", category="technical")
        store.query_facts("database encrypted", record_access=False)
        assert store.get(fid).access_count == 0

    def test_offline_token_search(self, offline_store: facts.FactStore) -> None:
        offline_store.add_fact("kelly criterion bet sizing", category="project")
        offline_store.add_fact("unrelated note about gardening", category="other")
        results = offline_store.query_facts("kelly sizing")
        assert results[0][0].fact == "kelly criterion bet sizing"

    def test_inactive_facts_excluded_from_search(self, store: facts.FactStore) -> None:
        fid = store.add_fact("the database is encrypted", category="technical")
        store.deactivate(fid)
        assert store.query_facts("database encrypted") == []


# ── Context selection ─────────────────────────────────────────────────────────
class TestContext:
    def test_orders_by_salience(self, store: facts.FactStore) -> None:
        low = store.add_fact("rarely used fact", confidence=0.5)
        high = store.add_fact("important fact", confidence=0.9)
        for _ in range(5):
            store.touch(high)
        ctx = store.get_facts_for_context(limit=10)
        assert ctx[0].id == high
        assert {low, high} == {f.id for f in ctx}

    def test_filters_by_categories(self, store: facts.FactStore) -> None:
        store.add_fact("a pref", category="preference")
        store.add_fact("a tech", category="technical")
        ctx = store.get_facts_for_context(categories=["preference"])
        assert len(ctx) == 1
        assert ctx[0].category == "preference"

    def test_excludes_inactive(self, store: facts.FactStore) -> None:
        fid = store.add_fact("gone", category="other")
        store.deactivate(fid)
        assert store.get_facts_for_context() == []


# ── Decay ─────────────────────────────────────────────────────────────────────
class TestDecay:
    def test_one_half_life_halves_confidence(self, store: facts.FactStore) -> None:
        fid = store.add_fact("a fact", confidence=0.8)
        future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)
        changed = store.decay_scores(half_life_days=30, now=future)
        assert changed == 1
        assert store.get(fid).confidence == pytest.approx(0.4, abs=1e-3)

    def test_recent_access_resists_decay(self, store: facts.FactStore) -> None:
        fid = store.add_fact("fresh fact", confidence=0.8)
        # now == last_accessed → age 0 → untouched.
        changed = store.decay_scores(half_life_days=30)
        assert changed == 0
        assert store.get(fid).confidence == 0.8

    def test_decayed_below_floor_is_forgotten(self, store: facts.FactStore) -> None:
        fid = store.add_fact("ancient fact", confidence=0.6)
        future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=365)
        store.decay_scores(half_life_days=30, min_confidence=0.05, now=future)
        assert store.get(fid).active is False

    def test_decay_ignores_inactive(self, store: facts.FactStore) -> None:
        fid = store.add_fact("x", confidence=0.8)
        store.deactivate(fid)
        future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)
        assert store.decay_scores(now=future) == 0


# ── Stats ─────────────────────────────────────────────────────────────────────
class TestStats:
    def test_stats_shape(self, store: facts.FactStore) -> None:
        store.add_fact("a", "src1.md", category="preference", confidence=0.8)
        store.add_fact("b", "src1.md", category="technical", confidence=0.6)
        gone = store.add_fact("c", "src2.md", category="other", confidence=0.4)
        store.deactivate(gone)

        stats = store.stats()
        assert stats["total"] == 3
        assert stats["active"] == 2
        assert stats["superseded"] == 1
        assert stats["by_category"] == {"preference": 1, "technical": 1}
        assert stats["by_source"]["src1.md"] == 2
        assert stats["avg_confidence"] == pytest.approx(0.7, abs=1e-6)
        assert stats["has_embeddings"] is True

    def test_offline_stats_reports_no_embeddings(self, offline_store: facts.FactStore) -> None:
        offline_store.add_fact("a")
        assert offline_store.stats()["has_embeddings"] is False


# ── End-to-end extract + ingest ───────────────────────────────────────────────
class TestExtractAndIngest:
    def test_full_pipeline_offline(self, offline_store: facts.FactStore) -> None:
        text = (
            "We decided to use uv instead of pip.\n"
            "Paul prefers bullet lists over tables.\n"
            "The service runs Python 3.13 on localhost:5555.\n"
            "What time is the meeting?\n"
        )
        tally = offline_store.extract_and_ingest(text, "notes.md", use_llm=False)
        assert tally["inserted"] >= 3  # the question is dropped
        cats = {f.category for f in offline_store.list_facts()}
        assert {"decision", "preference", "technical"} <= cats


# ── Path resolution ───────────────────────────────────────────────────────────
class TestPaths:
    def test_facts_db_path_honours_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EIDETIC_FACTS_PATH", "/tmp/custom/facts.db")
        assert facts.facts_db_path() == Path("/tmp/custom/facts.db")

    def test_facts_db_path_uses_vault(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EIDETIC_FACTS_PATH", raising=False)
        monkeypatch.setenv("VAULT_PATH", "/tmp/vault")
        assert facts.facts_db_path() == Path("/tmp/vault/.eidetic/facts.db")
