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
