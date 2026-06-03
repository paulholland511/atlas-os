"""Tests for scripts/embed_vault.py — text helpers, scoring, and the embed call."""

from __future__ import annotations

import embed_vault


def test_module_imports() -> None:
    assert hasattr(embed_vault, "run_embed")
    assert hasattr(embed_vault, "embed")


class TestTextHelpers:
    def test_approx_tokens_minimum_one(self) -> None:
        assert embed_vault.approx_tokens("") == 1
        assert embed_vault.approx_tokens("a" * 8) == 2

    def test_get_folder(self) -> None:
        assert embed_vault.get_folder("research/foo.md") == "research"
        assert embed_vault.get_folder("root-level.md") == ""

    def test_get_doc_type_known_and_unknown(self) -> None:
        assert embed_vault.get_doc_type("research") == "research"
        assert embed_vault.get_doc_type("totally-unknown") == "misc"


class TestFrontmatterTags:
    def test_inline_tags(self) -> None:
        text = "---\ntags: [alpha, beta, gamma]\n---\nbody"
        assert embed_vault.extract_frontmatter_tags(text) == ["alpha", "beta", "gamma"]

    def test_block_tags(self) -> None:
        text = "---\ntags:\n  - alpha\n  - beta\n---\nbody"
        assert embed_vault.extract_frontmatter_tags(text) == ["alpha", "beta"]

    def test_no_frontmatter(self) -> None:
        assert embed_vault.extract_frontmatter_tags("no frontmatter here") == []


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        assert embed_vault.cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0

    def test_orthogonal_vectors(self) -> None:
        assert embed_vault.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_zero_vector_is_safe(self) -> None:
        assert embed_vault.cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


class TestKeywordSearch:
    def _chunks(self) -> list[dict]:
        return [
            {"file": "a.md", "heading": "", "chunk_text": "the quick brown fox"},
            {"file": "b.md", "heading": "", "chunk_text": "nothing relevant at all"},
            {"file": "c.md", "heading": "", "chunk_text": "fox fox fox everywhere"},
        ]

    def test_ranks_by_term_frequency(self) -> None:
        results = embed_vault.keyword_search("fox", self._chunks(), top_k=3)
        assert results[0]["file"] == "c.md"  # three matches ranks first
        assert results[0]["score"] == 1.0    # normalized to max

    def test_empty_query_returns_nothing(self) -> None:
        assert embed_vault.keyword_search("   ", self._chunks()) == []


class TestChunkMatchesFilters:
    def test_matches_on_folder(self) -> None:
        v = {"folder": "research", "doc_type": "research", "tags": ["ai"]}
        assert embed_vault.chunk_matches_filters(v, ["research"]) is True

    def test_matches_on_tag(self) -> None:
        v = {"folder": "research", "doc_type": "research", "tags": ["ai"]}
        assert embed_vault.chunk_matches_filters(v, ["ai"]) is True

    def test_requires_all_filters(self) -> None:
        v = {"folder": "research", "doc_type": "research", "tags": ["ai"]}
        assert embed_vault.chunk_matches_filters(v, ["research", "missing"]) is False


def test_chunk_text_carries_heading_and_relative_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(embed_vault, "VAULT_DIR", tmp_path)
    fp = tmp_path / "doc.md"
    text = "# Title\n\n" + ("word " * 50)
    chunks = embed_vault.chunk_text(text, str(fp))
    assert chunks
    assert chunks[0]["file"] == "doc.md"
    assert chunks[0]["heading"] == "Title"


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_embed_calls_endpoint_and_orders_by_index(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url, headers, json, timeout):  # noqa: A002 - mirror requests signature
        captured["url"] = url
        captured["input"] = json["input"]
        # return out of order to verify sorting by "index"
        return _FakeResponse(
            {"data": [
                {"index": 1, "embedding": [0.2]},
                {"index": 0, "embedding": [0.1]},
            ]}
        )

    monkeypatch.setattr(embed_vault.requests, "post", fake_post)
    vectors = embed_vault.embed(["first", "second"])
    assert vectors == [[0.1], [0.2]]
    assert captured["input"] == ["first", "second"]


def test_search_keyword_mode_uses_loaded_vectors(monkeypatch) -> None:
    fake_vectors = [
        {"file": "a.md", "heading": "", "chunk_text": "kelly criterion sizing"},
        {"file": "b.md", "heading": "", "chunk_text": "unrelated text"},
    ]
    monkeypatch.setattr(embed_vault, "load_vectors", lambda: fake_vectors)
    results = embed_vault.search("kelly", top_k=2, mode="keyword")
    assert results[0]["file"] == "a.md"


def _populate_store(tmp_path, monkeypatch) -> None:
    """Point embed_vault at a temp RAG dir and seed a small store."""
    monkeypatch.setattr(embed_vault, "RAG_DIR", tmp_path)
    store = embed_vault.open_store()
    store.add_vectors([
        {"id": "a::1", "file": "research/a.md", "chunk_text": "kelly criterion bet sizing",
         "heading": "Kelly", "embedding": [1.0, 0.0, 0.0],
         "folder": "research", "doc_type": "research", "tags": ["trading"]},
        {"id": "b::1", "file": "wiki/b.pdf", "chunk_text": "totally unrelated content",
         "heading": "", "embedding": [0.0, 1.0, 0.0],
         "folder": "wiki", "doc_type": "pdf", "tags": ["ref"]},
        {"id": "c::1", "file": "research/c.md", "chunk_text": "kelly sizing revisited",
         "heading": "", "embedding": [0.9, 0.1, 0.0],
         "folder": "research", "doc_type": "research", "tags": ["trading"]},
    ])
    store.close()


class TestHybridSearch:
    def test_hybrid_ranks_relevant_first(self, tmp_path, monkeypatch) -> None:
        _populate_store(tmp_path, monkeypatch)
        monkeypatch.setattr(embed_vault, "embed", lambda texts: [[1.0, 0.0, 0.0]])
        results = embed_vault.search("kelly criterion", top_k=3, mode="hybrid")
        assert results[0]["file"] == "research/a.md"  # vector + lexical match
        assert results[0].get("rerank_score") is not None  # rerank ran

    def test_vector_mode_uses_knn(self, tmp_path, monkeypatch) -> None:
        _populate_store(tmp_path, monkeypatch)
        monkeypatch.setattr(embed_vault, "embed", lambda texts: [[1.0, 0.0, 0.0]])
        results = embed_vault.search("anything", top_k=2, mode="vector")
        assert results[0]["file"] == "research/a.md"
        assert "rerank_score" not in results[0]  # vector mode doesn't rerank

    def test_no_rerank_flag(self, tmp_path, monkeypatch) -> None:
        _populate_store(tmp_path, monkeypatch)
        monkeypatch.setattr(embed_vault, "embed", lambda texts: [[1.0, 0.0, 0.0]])
        results = embed_vault.search("kelly", top_k=3, mode="hybrid", rerank=False)
        assert results and "rerank_score" not in results[0]


class TestAdvancedSearch:
    def test_file_type_filter(self, tmp_path, monkeypatch) -> None:
        _populate_store(tmp_path, monkeypatch)
        monkeypatch.setattr(embed_vault, "embed", lambda texts: [[1.0, 0.0, 0.0]])
        results = embed_vault.advanced_search(
            "kelly", top_k=5, mode="vector", file_types=["md"]
        )
        assert results
        assert all(r["file"].endswith(".md") for r in results)

    def test_folder_filter_keyword_mode_needs_no_endpoint(self, tmp_path, monkeypatch) -> None:
        _populate_store(tmp_path, monkeypatch)
        # mode=keyword must not call embed() at all.
        def _boom(texts):  # pragma: no cover - asserts it is never called
            raise AssertionError("embed() should not be called in keyword mode")
        monkeypatch.setattr(embed_vault, "embed", _boom)
        results = embed_vault.advanced_search(
            "kelly", top_k=5, mode="keyword", folders=["research"]
        )
        assert results
        assert all(r["file"].startswith("research/") for r in results)

    def test_empty_filter_result(self, tmp_path, monkeypatch) -> None:
        _populate_store(tmp_path, monkeypatch)
        monkeypatch.setattr(embed_vault, "embed", lambda texts: [[1.0, 0.0, 0.0]])
        assert embed_vault.advanced_search("kelly", tags=["nonexistent"]) == []
