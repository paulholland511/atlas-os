"""Tests for scripts/build_graph.py — wikilink extraction and graph building."""

from __future__ import annotations

import build_graph


def test_module_imports() -> None:
    assert hasattr(build_graph, "build_graph")
    assert hasattr(build_graph, "extract_wikilinks")


class TestExtractWikilinks:
    def test_plain_link(self) -> None:
        assert build_graph.extract_wikilinks("see [[note]] here") == ["note"]

    def test_display_alias_is_stripped(self) -> None:
        assert build_graph.extract_wikilinks("[[note|Pretty Name]]") == ["note"]

    def test_heading_anchor_is_stripped(self) -> None:
        assert build_graph.extract_wikilinks("[[note#Section]]") == ["note"]

    def test_multiple_links(self) -> None:
        assert build_graph.extract_wikilinks("[[a]] and [[b]] and [[c]]") == ["a", "b", "c"]

    def test_no_links(self) -> None:
        assert build_graph.extract_wikilinks("just plain text, no links") == []


class TestResolveLink:
    def test_resolves_by_stem(self) -> None:
        index = build_graph.build_file_index([])
        index["my-note"] = "folder/my-note.md"
        assert build_graph.resolve_link("my-note", index) == "folder/my-note.md"

    def test_unresolvable_returns_none(self) -> None:
        assert build_graph.resolve_link("does-not-exist", {}) is None


def test_build_file_index_maps_stem_and_relpath(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(build_graph, "VAULT_DIR", tmp_path)
    a = tmp_path / "notes" / "alpha.md"
    a.parent.mkdir(parents=True)
    a.write_text("# alpha")
    index = build_graph.build_file_index([a])
    assert index["alpha"] == "notes/alpha.md"
    assert index["notes/alpha"] == "notes/alpha.md"


def test_build_graph_produces_nodes_and_edges(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(build_graph, "VAULT_DIR", tmp_path)
    (tmp_path / "a.md").write_text("Link to [[b]] and [[c]].")
    (tmp_path / "b.md").write_text("Back to [[a]].")
    (tmp_path / "c.md").write_text("No links here.")

    graph, stats = build_graph.build_graph()

    assert set(graph["nodes"]) == {"a.md", "b.md", "c.md"}
    assert {"source": "a.md", "target": "b.md"} in graph["edges"]
    assert {"source": "b.md", "target": "a.md"} in graph["edges"]
    assert stats["total_nodes"] == 3
    assert stats["total_edges"] == 3  # a->b, a->c, b->a
    assert "a.md" in graph["backlinks"]["b.md"]


def test_build_graph_ignores_self_and_duplicate_links(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(build_graph, "VAULT_DIR", tmp_path)
    (tmp_path / "a.md").write_text("[[a]] self link, [[b]] then [[b]] again.")
    (tmp_path / "b.md").write_text("plain")

    graph, _ = build_graph.build_graph()

    # self-link dropped, duplicate b deduplicated → exactly one edge a->b
    assert graph["edges"] == [{"source": "a.md", "target": "b.md"}]
