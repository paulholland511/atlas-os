"""Tests for atlas_os.vectordb — the SQLite vector store.

Each test runs against both backends where possible: the sqlite-vec KNN index
(when the extension is installed) and the brute-force cosine fallback (forced via
``ATLAS_VECTORDB_NO_VEC``). The two must return identical rankings and scores.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas_os import vectordb


def _entries() -> list[dict]:
    return [
        {"id": "a::1", "file": "research/a.md", "chunk_text": "kelly criterion bet sizing",
         "heading": "Kelly", "embedding": [1.0, 0.0, 0.0],
         "folder": "research", "doc_type": "research", "tags": ["trading"]},
        {"id": "b::1", "file": "wiki/b.md", "chunk_text": "totally unrelated content",
         "heading": "", "embedding": [0.0, 1.0, 0.0],
         "folder": "wiki", "doc_type": "wiki", "tags": ["wiki"]},
        {"id": "c::1", "file": "research/c.md", "chunk_text": "kelly sizing revisited",
         "heading": "", "embedding": [0.9, 0.1, 0.0],
         "folder": "research", "doc_type": "research", "tags": ["trading"]},
    ]


@pytest.fixture(params=["auto", "no_vec"])
def store(request: pytest.FixtureRequest, tmp_path: Path,
          monkeypatch: pytest.MonkeyPatch) -> vectordb.VectorStore:
    """A populated store, once per backend (sqlite-vec if available, brute-force)."""
    if request.param == "no_vec":
        monkeypatch.setenv("ATLAS_VECTORDB_NO_VEC", "1")
    s = vectordb.VectorStore(tmp_path / "vectors.db")
    s.add_vectors(_entries())
    yield s
    s.close()


class TestBasics:
    def test_count_and_files(self, store: vectordb.VectorStore) -> None:
        assert store.count() == 3
        assert store.files() == {"research/a.md", "wiki/b.md", "research/c.md"}

    def test_clear_empties_the_store(self, store: vectordb.VectorStore) -> None:
        store.clear()
        assert store.count() == 0
        assert store.search([1.0, 0.0, 0.0]) == []

    def test_delete_by_file(self, store: vectordb.VectorStore) -> None:
        assert store.delete_by_file("wiki/b.md") == 1
        assert store.count() == 2
        assert "wiki/b.md" not in store.files()
        assert store.delete_by_file("does/not/exist.md") == 0

    def test_add_is_idempotent_on_id(self, store: vectordb.VectorStore) -> None:
        # Re-adding the same id updates in place rather than duplicating.
        store.add_vectors([{
            "id": "a::1", "file": "research/a.md", "chunk_text": "updated text",
            "embedding": [1.0, 0.0, 0.0], "folder": "research", "doc_type": "research",
            "tags": ["trading"],
        }])
        assert store.count() == 3
        match = next(c for c in store.all_chunks() if c["id"] == "a::1")
        assert match["chunk_text"] == "updated text"

    def test_skips_entries_without_embedding(self, store: vectordb.VectorStore) -> None:
        added = store.add_vectors([{"id": "x", "file": "x.md", "chunk_text": "x",
                                    "embedding": []}])
        assert added == 0
        assert store.count() == 3


class TestSearch:
    def test_ranks_by_similarity(self, store: vectordb.VectorStore) -> None:
        results = store.search([1.0, 0.0, 0.0], top_k=3)
        assert [r["file"] for r in results] == ["research/a.md", "research/c.md", "wiki/b.md"]
        assert results[0]["score"] == pytest.approx(1.0, abs=1e-4)
        assert results[2]["score"] == pytest.approx(0.0, abs=1e-4)

    def test_top_k_limits_results(self, store: vectordb.VectorStore) -> None:
        assert len(store.search([1.0, 0.0, 0.0], top_k=1)) == 1

    def test_result_shape(self, store: vectordb.VectorStore) -> None:
        r = store.search([1.0, 0.0, 0.0], top_k=1)[0]
        assert set(r) == {"file", "heading", "text", "score"}

    def test_filters_restrict_candidates(self, store: vectordb.VectorStore) -> None:
        results = store.search([1.0, 0.0, 0.0], top_k=3, filters=["wiki"])
        assert [r["file"] for r in results] == ["wiki/b.md"]

    def test_filter_by_tag(self, store: vectordb.VectorStore) -> None:
        results = store.search([1.0, 0.0, 0.0], top_k=3, filters=["trading"])
        assert {r["file"] for r in results} == {"research/a.md", "research/c.md"}

    def test_empty_store_returns_nothing(self, tmp_path: Path) -> None:
        empty = vectordb.VectorStore(tmp_path / "empty.db")
        assert empty.search([1.0, 0.0, 0.0]) == []
        empty.close()


class TestTagsRoundTrip:
    def test_tags_stored_as_list(self, store: vectordb.VectorStore) -> None:
        chunk = next(c for c in store.all_chunks() if c["id"] == "a::1")
        assert chunk["tags"] == ["trading"]

    def test_accepts_pre_serialised_tags(self, tmp_path: Path) -> None:
        s = vectordb.VectorStore(tmp_path / "v.db")
        s.add_vectors([{"id": "z", "file": "z.md", "chunk_text": "z",
                        "embedding": [1.0, 0.0], "tags": json.dumps(["x", "y"])}])
        assert next(iter(s.all_chunks()))["tags"] == ["x", "y"]
        s.close()


class TestMigration:
    def test_read_from_json_missing(self, tmp_path: Path) -> None:
        assert vectordb.VectorStore.read_from_json(tmp_path / "nope.json") == []

    def test_read_from_json_corrupt(self, tmp_path: Path) -> None:
        bad = tmp_path / "vectors.json"
        bad.write_text("{ not valid json")
        assert vectordb.VectorStore.read_from_json(bad) == []

    def test_open_store_auto_migrates(self, tmp_path: Path) -> None:
        (tmp_path / "vectors.json").write_text(json.dumps(_entries()))
        store = vectordb.open_store(tmp_path)
        assert store.count() == 3
        assert (tmp_path / "vectors.db").exists()
        store.close()

    def test_open_store_no_double_migrate(self, tmp_path: Path) -> None:
        (tmp_path / "vectors.json").write_text(json.dumps(_entries()))
        vectordb.open_store(tmp_path).close()           # migrates once
        # Second open sees an existing DB and must not re-import on top.
        store = vectordb.open_store(tmp_path)
        assert store.count() == 3
        store.close()

    def test_import_from_json(self, tmp_path: Path) -> None:
        (tmp_path / "vectors.json").write_text(json.dumps(_entries()))
        store = vectordb.VectorStore(tmp_path / "vectors.db")
        assert store.import_from_json(tmp_path / "vectors.json") == 3
        store.close()


class TestEmbeddingCache:
    def test_round_trip(self, tmp_path: Path) -> None:
        s = vectordb.VectorStore(tmp_path / "v.db")
        s.cache_embeddings([("h1", [0.1, 0.2]), ("h2", [0.3, 0.4])])
        assert s.cache_size() == 2
        got = s.cached_embeddings(["h1", "h2", "missing"])
        assert set(got) == {"h1", "h2"}
        assert got["h1"] == pytest.approx([0.1, 0.2])
        s.close()

    def test_insert_is_idempotent(self, tmp_path: Path) -> None:
        s = vectordb.VectorStore(tmp_path / "v.db")
        s.cache_embeddings([("h1", [0.1, 0.2])])
        s.cache_embeddings([("h1", [9.9, 9.9])])  # same key — first write wins
        assert s.cache_size() == 1
        assert s.cached_embeddings(["h1"])["h1"] == pytest.approx([0.1, 0.2])
        s.close()

    def test_cache_survives_clear(self, tmp_path: Path) -> None:
        # The whole point: a full re-embed (clear) must not drop the cache.
        s = vectordb.VectorStore(tmp_path / "v.db")
        s.add_vectors(_entries())
        s.cache_embeddings([("h1", [0.1, 0.2])])
        s.clear()
        assert s.count() == 0
        assert s.cache_size() == 1
        s.close()

    def test_clear_cache(self, tmp_path: Path) -> None:
        s = vectordb.VectorStore(tmp_path / "v.db")
        s.cache_embeddings([("h1", [0.1, 0.2])])
        s.clear_cache()
        assert s.cache_size() == 0
        s.close()

    def test_empty_lookup(self, tmp_path: Path) -> None:
        s = vectordb.VectorStore(tmp_path / "v.db")
        assert s.cached_embeddings([]) == {}
        s.close()


def test_persists_across_reopen(tmp_path: Path) -> None:
    db = tmp_path / "vectors.db"
    s1 = vectordb.VectorStore(db)
    s1.add_vectors(_entries())
    s1.close()

    s2 = vectordb.VectorStore(db)
    assert s2.count() == 3
    # The embedding dimension is recovered from the meta table on reopen.
    results = s2.search([1.0, 0.0, 0.0], top_k=1)
    assert results[0]["file"] == "research/a.md"
    s2.close()
