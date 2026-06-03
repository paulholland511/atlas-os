"""Tests for atlas_os.rag — semantic chunking, BM25, fusion, rerank, filtering."""

from __future__ import annotations

from pathlib import Path

from atlas_os import rag


class TestSemanticChunk:
    def test_relative_file_and_heading(self, tmp_path: Path) -> None:
        fp = tmp_path / "doc.md"
        chunks = rag.semantic_chunk("# Title\n\n" + ("word " * 50), str(fp), tmp_path)
        assert chunks
        assert chunks[0]["file"] == "doc.md"
        assert chunks[0]["heading"] == "Title"

    def test_splits_on_heading_boundaries(self, tmp_path: Path) -> None:
        text = "# Alpha\n\nFirst section body.\n\n# Beta\n\nSecond section body."
        chunks = rag.semantic_chunk(text, str(tmp_path / "d.md"), tmp_path)
        headings = {c["heading"] for c in chunks}
        assert headings == {"Alpha", "Beta"}
        # A heading never bleeds across into the wrong chunk's text.
        alpha = next(c for c in chunks if c["heading"] == "Alpha")
        assert "Second section" not in alpha["chunk_text"]

    def test_preamble_before_first_heading_kept(self, tmp_path: Path) -> None:
        text = "Intro paragraph with no heading.\n\n# Real Heading\n\nBody."
        chunks = rag.semantic_chunk(text, str(tmp_path / "d.md"), tmp_path)
        assert chunks[0]["heading"] == ""
        assert "Intro paragraph" in chunks[0]["chunk_text"]

    def test_packs_paragraphs_up_to_budget(self, tmp_path: Path) -> None:
        # Five ~40-char paragraphs, target ~25 tokens (~100 chars) → multiple chunks,
        # but each chunk holds whole paragraphs (no mid-paragraph cut).
        paras = "\n\n".join(f"Paragraph number {i} has some words in it." for i in range(5))
        chunks = rag.semantic_chunk(
            paras, str(tmp_path / "d.md"), tmp_path, target_tokens=25, overlap_tokens=5
        )
        assert len(chunks) > 1
        for c in chunks:
            assert "Paragraph number" in c["chunk_text"]

    def test_oversized_paragraph_is_windowed(self, tmp_path: Path) -> None:
        big = "word " * 1000  # one huge paragraph, no breaks
        chunks = rag.semantic_chunk(
            big, str(tmp_path / "d.md"), tmp_path, target_tokens=100, max_tokens=200
        )
        assert len(chunks) > 1

    def test_empty_text_yields_no_chunks(self, tmp_path: Path) -> None:
        assert rag.semantic_chunk("   \n\n  ", str(tmp_path / "d.md"), tmp_path) == []


class TestBM25:
    def _chunks(self) -> list[dict]:
        return [
            {"file": "a.md", "heading": "", "chunk_text": "the quick brown fox jumps"},
            {"file": "b.md", "heading": "", "chunk_text": "nothing relevant at all here"},
            {"file": "c.md", "heading": "", "chunk_text": "fox fox fox everywhere fox"},
        ]

    def test_ranks_by_relevance(self) -> None:
        results = rag.bm25_search("fox", self._chunks(), top_k=3)
        assert results[0]["file"] == "c.md"  # most fox mentions
        assert results[0]["score"] == 1.0     # normalised to top
        files = {r["file"] for r in results}
        assert "b.md" not in files            # zero-score chunk dropped

    def test_empty_query(self) -> None:
        assert rag.bm25_search("   ", self._chunks()) == []

    def test_idf_downweights_common_terms(self) -> None:
        # "common" appears everywhere (no discriminating power); "rare" in one doc.
        chunks = [
            {"file": "a.md", "heading": "", "chunk_text": "common common rare"},
            {"file": "b.md", "heading": "", "chunk_text": "common common common"},
            {"file": "c.md", "heading": "", "chunk_text": "common text only"},
        ]
        results = rag.bm25_search("rare common", chunks, top_k=3)
        assert results[0]["file"] == "a.md"  # the doc with the rare term wins


class TestReciprocalRankFusion:
    def test_agreement_is_rewarded(self) -> None:
        vec = [
            {"file": "a.md", "heading": "", "text": "alpha"},
            {"file": "b.md", "heading": "", "text": "beta"},
        ]
        kw = [
            {"file": "a.md", "heading": "", "text": "alpha"},
            {"file": "c.md", "heading": "", "text": "gamma"},
        ]
        fused = rag.reciprocal_rank_fusion([vec, kw], top_k=3)
        # a.md is ranked highly by BOTH lists → must come first.
        assert fused[0]["file"] == "a.md"
        assert {r["file"] for r in fused} == {"a.md", "b.md", "c.md"}

    def test_empty_inputs(self) -> None:
        assert rag.reciprocal_rank_fusion([[], []]) == []


class TestTfidfRerank:
    def test_reorders_by_query_similarity(self) -> None:
        candidates = [
            {"file": "a.md", "heading": "", "text": "machine learning models"},
            {"file": "b.md", "heading": "", "text": "kelly criterion bet sizing"},
            {"file": "c.md", "heading": "", "text": "gardening tips for spring"},
        ]
        reranked = rag.tfidf_rerank("kelly criterion", candidates, top_k=3)
        assert reranked[0]["file"] == "b.md"
        assert "rerank_score" in reranked[0]

    def test_no_signal_preserves_order(self) -> None:
        candidates = [
            {"file": "a.md", "heading": "", "text": "alpha"},
            {"file": "b.md", "heading": "", "text": "beta"},
        ]
        reranked = rag.tfidf_rerank("zzz nomatch", candidates, top_k=2)
        assert [r["file"] for r in reranked] == ["a.md", "b.md"]


class TestContentHash:
    def test_stable_and_text_sensitive(self) -> None:
        assert rag.content_hash("hello", "m1") == rag.content_hash("hello", "m1")
        assert rag.content_hash("hello", "m1") != rag.content_hash("world", "m1")

    def test_model_scoped(self) -> None:
        assert rag.content_hash("hello", "m1") != rag.content_hash("hello", "m2")


class TestFilterChunks:
    def _chunks(self) -> list[dict]:
        return [
            {"file": "research/a.md", "folder": "research", "doc_type": "research",
             "tags": ["ai"], "modified_time": 1000.0},
            {"file": "wiki/b.pdf", "folder": "wiki", "doc_type": "pdf",
             "tags": ["ref"], "modified_time": 2000.0},
            {"file": "research/c.md", "folder": "research", "doc_type": "research",
             "tags": ["trading"], "modified_time": 3000.0},
        ]

    def test_no_filters_returns_all(self) -> None:
        assert len(rag.filter_chunks(self._chunks())) == 3

    def test_folder_filter(self) -> None:
        out = rag.filter_chunks(self._chunks(), folders=["research"])
        assert {c["file"] for c in out} == {"research/a.md", "research/c.md"}

    def test_tag_filter_any_of(self) -> None:
        out = rag.filter_chunks(self._chunks(), tags=["ai", "trading"])
        assert {c["file"] for c in out} == {"research/a.md", "research/c.md"}

    def test_file_type_filter_with_or_without_dot(self) -> None:
        assert {c["file"] for c in rag.filter_chunks(self._chunks(), file_types=["pdf"])} \
            == {"wiki/b.pdf"}
        assert {c["file"] for c in rag.filter_chunks(self._chunks(), file_types=[".md"])} \
            == {"research/a.md", "research/c.md"}

    def test_date_window(self) -> None:
        out = rag.filter_chunks(self._chunks(), since=1500.0, until=2500.0)
        assert {c["file"] for c in out} == {"wiki/b.pdf"}

    def test_criteria_are_anded(self) -> None:
        out = rag.filter_chunks(self._chunks(), folders=["research"], tags=["trading"])
        assert {c["file"] for c in out} == {"research/c.md"}
