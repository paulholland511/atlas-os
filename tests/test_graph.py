"""Tests for the knowledge-graph viewer (``/graph``, ``/api/graph``).

Two layers, mirroring ``test_dashboard.py``:

* The **data layer** (``data.graph_data`` and its helpers) — pure functions that
  scan a vault for ``[[wikilinks]]`` and shape nodes/edges for the viewer. Tested
  directly against temp vaults, no Flask required.
* The **Flask routes** — the ``/graph`` page and the ``/api/graph`` JSON
  endpoint, exercised through Flask's test client. Skipped automatically when the
  ``dashboard`` extra (Flask) isn't installed.

Everything is hermetic: ``VAULT_PATH`` / ``RAG_DIR`` point at temp paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas_os.dashboard import data


@pytest.fixture()
def graph_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the data layer at a temp vault and return its root."""
    vault = tmp_path / "vault"
    (vault / ".rag").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("RAG_DIR", str(vault / ".rag"))
    return vault


def _write(vault: Path, rel: str, body: str = "") -> None:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


# ── classification ───────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("sessions/2026-06-04.md", "session"),
        ("daily-session-log.md", "session"),
        ("sources/some-paper.md", "source"),
        ("skills/autoresearch/SKILL.md", "skill"),
        ("research/market-scan.md", "research"),
        ("wiki/index.md", "wiki"),
        ("memory/preferences.md", "memory"),
        ("notes/random-thought.md", "note"),
    ],
)
def test_classify_node(rel: str, expected: str) -> None:
    assert data._classify_node(rel) == expected


# ── data layer ───────────────────────────────────────────────────────────────
def test_graph_data_no_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAULT_PATH", raising=False)
    monkeypatch.delenv("RAG_DIR", raising=False)
    result = data.graph_data()
    assert result["available"] is False
    assert "VAULT_PATH" in result["reason"]
    # A legend is always present so the page can render even with nothing to show.
    assert {t["type"] for t in result["types"]} >= {"session", "skill", "note"}


def test_graph_data_empty_vault(graph_env: Path) -> None:
    result = data.graph_data()
    assert result["available"] is True
    assert result["nodes"] == []
    assert "no markdown" in result["reason"]


def test_graph_data_nodes_and_edges(graph_env: Path) -> None:
    _write(graph_env, "a.md", "links to [[b]] and [[c]]")
    _write(graph_env, "b.md", "back to [[a]]")
    _write(graph_env, "c.md", "an orphan target with no outgoing links")

    result = data.graph_data()
    assert result["available"] is True
    ids = {n["id"] for n in result["nodes"]}
    assert ids == {"a.md", "b.md", "c.md"}

    edges = {(e["source"], e["target"]) for e in result["edges"]}
    assert ("a.md", "b.md") in edges
    assert ("a.md", "c.md") in edges
    assert ("b.md", "a.md") in edges

    by_id = {n["id"]: n for n in result["nodes"]}
    assert by_id["a.md"]["out"] == 2
    assert by_id["a.md"]["in"] == 1  # b links back
    assert by_id["c.md"]["out"] == 0
    assert by_id["c.md"]["in"] == 1
    assert by_id["c.md"]["degree"] == 1
    assert by_id["a.md"]["label"] == "a"


def test_graph_data_resolves_piped_and_heading_links(graph_env: Path) -> None:
    _write(graph_env, "a.md", "see [[b|Pretty Name]] and [[b#Section]]")
    _write(graph_env, "b.md", "target")
    result = data.graph_data()
    edges = {(e["source"], e["target"]) for e in result["edges"]}
    # Both forms resolve to b.md, deduplicated to a single edge.
    assert edges == {("a.md", "b.md")}


def test_graph_data_ignores_self_and_unresolved_links(graph_env: Path) -> None:
    _write(graph_env, "a.md", "[[a]] self-link and [[ghost]] that does not exist")
    result = data.graph_data()
    assert result["edges"] == []
    by_id = {n["id"]: n for n in result["nodes"]}
    assert by_id["a.md"]["degree"] == 0


def test_graph_data_resolves_nested_path_links(graph_env: Path) -> None:
    _write(graph_env, "index.md", "[[folder/deep]]")
    _write(graph_env, "folder/deep.md", "nested note")
    result = data.graph_data()
    edges = {(e["source"], e["target"]) for e in result["edges"]}
    assert ("index.md", "folder/deep.md") in edges


def test_graph_data_skips_infra_dirs(graph_env: Path) -> None:
    _write(graph_env, "real.md", "note")
    _write(graph_env, ".obsidian/config.md", "should be ignored")
    _write(graph_env, ".rag/cache.md", "should be ignored")
    result = data.graph_data()
    assert {n["id"] for n in result["nodes"]} == {"real.md"}


def test_graph_data_stats(graph_env: Path) -> None:
    _write(graph_env, "a.md", "[[b]]")
    _write(graph_env, "b.md", "[[a]]")
    _write(graph_env, "lonely.md", "no links here")
    stats = data.graph_data()["stats"]
    assert stats["nodes"] == 3
    assert stats["edges"] == 2
    assert stats["orphans"] == 1
    assert stats["truncated"] == 0
    assert stats["avg_degree"] == pytest.approx(4 / 3)


def test_graph_data_caps_to_max_nodes(graph_env: Path) -> None:
    # Hub links to ten leaves; with max_nodes=3 we keep the hub (highest degree)
    # plus two leaves, and drop edges whose endpoints fell away.
    leaves = [f"leaf{i}" for i in range(10)]
    _write(graph_env, "hub.md", " ".join(f"[[{leaf}]]" for leaf in leaves))
    for leaf in leaves:
        _write(graph_env, f"{leaf}.md", "leaf")

    result = data.graph_data(max_nodes=3)
    assert len(result["nodes"]) == 3
    assert "hub.md" in {n["id"] for n in result["nodes"]}
    assert result["stats"]["truncated"] == 8
    kept = {n["id"] for n in result["nodes"]}
    for edge in result["edges"]:
        assert edge["source"] in kept and edge["target"] in kept


# ── routes (need Flask) ──────────────────────────────────────────────────────
flask = pytest.importorskip("flask", reason="dashboard extra (flask) not installed")


@pytest.fixture()
def client(graph_env: Path):  # noqa: ANN201 - Flask test client
    from atlas_os.dashboard.app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_graph_route_renders(client) -> None:  # noqa: ANN001
    resp = client.get("/graph")
    assert resp.status_code == 200
    assert b"Knowledge graph" in resp.data
    # The viewer loads D3 and fetches the API endpoint.
    assert b"d3" in resp.data
    assert b"/api/graph" in resp.data


def test_api_graph_returns_json(client, graph_env: Path) -> None:  # noqa: ANN001
    _write(graph_env, "a.md", "[[b]]")
    _write(graph_env, "b.md", "[[a]]")
    resp = client.get("/api/graph")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["available"] is True
    assert {n["id"] for n in payload["nodes"]} == {"a.md", "b.md"}
    assert payload["stats"]["edges"] == 2
    assert any(t["type"] == "note" for t in payload["types"])


def test_api_graph_empty_vault_is_ok(client, graph_env: Path) -> None:  # noqa: ANN001
    resp = client.get("/api/graph")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["nodes"] == []
    assert "types" in payload
