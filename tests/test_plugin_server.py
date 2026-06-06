"""Tests for the Obsidian-plugin REST API (``eidetic_os.plugin_server``).

The server is a thin Flask routing layer over the dashboard data helpers and the
fact store, so the tests drive it through Flask's test client and assert the JSON
shape and the CORS headers each endpoint returns. Everything is hermetic: the
``plugin_env`` fixture points ``VAULT_PATH`` / ``RAG_DIR`` / ``EIDETIC_FACTS_PATH``
at a temp vault, and the offline ``keyword`` search mode (BM25) keeps the search
endpoint from needing an embeddings backend.

Skipped automatically when Flask (the optional ``dashboard`` extra) isn't
installed, so a core install still passes the suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eidetic_os import facts, vectordb

# The whole module needs Flask; skip cleanly when the extra isn't installed.
pytest.importorskip("flask", reason="dashboard extra (flask) not installed")


@pytest.fixture()
def plugin_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the vault, RAG dir, and fact store at a temp tree; return the vault."""
    vault = tmp_path / "vault"
    (vault / ".rag").mkdir(parents=True, exist_ok=True)
    (vault / ".eidetic").mkdir(parents=True, exist_ok=True)
    # A couple of notes so keyword search has something to match.
    (vault / "kelly.md").write_text(
        "# Kelly Criterion\n\nOptimal bet sizing for the crypto trading bot.\n"
    )
    (vault / "uv.md").write_text(
        "# Tooling\n\nUse uv for Python package management, not pip.\n"
    )
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("RAG_DIR", str(vault / ".rag"))
    monkeypatch.setenv("EIDETIC_AUDIT_PATH", str(vault / ".eidetic" / "audit.jsonl"))
    monkeypatch.setenv("EIDETIC_FACTS_PATH", str(vault / ".eidetic" / "facts.db"))
    return vault


@pytest.fixture()
def client(plugin_env: Path):  # noqa: ANN201 - Flask test client
    """A Flask test client for the plugin API, wired to the temp vault."""
    from eidetic_os.plugin_server import create_plugin_app

    app = create_plugin_app()
    app.config.update(TESTING=True)
    return app.test_client()


def _seed_facts(vault: Path) -> None:
    """Insert a few facts straight into the conventional store (offline mode)."""
    with facts.open_store(with_embedder=False) as store:
        store.add_fact("Paul prefers uv over pip", category="preference")
        store.add_fact("The trading bot uses Kelly Criterion", category="technical")
        store.add_fact("Eidetic OS is local-first", category="project")


def _seed_vectors(vault: Path) -> None:
    """Build a tiny vector store so /api/stats and keyword search have content.

    ``keyword`` (BM25) mode ranks over the indexed ``chunk_text``, so the chunks
    carry real words; the embeddings are dummy 3-vectors (unused offline).
    """
    db = vectordb.default_db_path(vault / ".rag")
    with vectordb.VectorStore(db) as store:
        store.add_vectors([
            {
                "id": "kelly::0",
                "file": "kelly.md",
                "chunk_text": "Kelly Criterion optimal bet sizing for the crypto trading bot",
                "embedding": [0.1, 0.2, 0.3],
            },
            {
                "id": "uv::0",
                "file": "uv.md",
                "chunk_text": "Use uv for Python package management not pip",
                "embedding": [0.2, 0.3, 0.4],
            },
        ])
    (vault / ".rag" / "last_embed.txt").write_text("1000000000.0")


# ── health ───────────────────────────────────────────────────────────────────
def test_health_ok(client) -> None:  # noqa: ANN001
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["service"] == "eidetic-os-plugin"
    assert isinstance(body["version"], str) and body["version"]


def test_cors_headers_present(client) -> None:  # noqa: ANN001
    """Every response must carry the CORS headers the Obsidian renderer needs."""
    resp = client.get("/api/health")
    assert resp.headers["Access-Control-Allow-Origin"] == "*"
    assert "GET" in resp.headers["Access-Control-Allow-Methods"]
    assert "Content-Type" in resp.headers["Access-Control-Allow-Headers"]


# ── search ───────────────────────────────────────────────────────────────────
def test_search_empty_query_returns_empty(client) -> None:  # noqa: ANN001
    body = client.get("/api/search").get_json()
    assert body == {"ok": True, "query": "", "results": []}


def test_search_forwards_to_run_search(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:  # noqa: ANN001
    """The /api/search route passes q/limit/mode through to the RAG search layer
    and returns its result verbatim.

    The underlying search shells out to ``scripts/rag_search.py`` (covered by the
    dashboard/RAG suites); here we stub that one call so the route is tested
    deterministically — no embeddings backend, no subprocess, no flakiness.
    """
    from eidetic_os.dashboard import data

    captured: dict[str, object] = {}

    def fake_run_search(query: str, top_k: int = 5, mode: str = "hybrid") -> dict[str, object]:
        captured.update(query=query, top_k=top_k, mode=mode)
        return {
            "ok": True,
            "query": query,
            "mode": mode,
            "results": [
                {"file": "kelly.md", "heading": "Kelly", "score": 0.91, "snippet": "bet sizing"}
            ],
        }

    monkeypatch.setattr(data, "run_search", fake_run_search)
    body = client.get("/api/search?q=kelly&mode=keyword&limit=5").get_json()
    assert captured == {"query": "kelly", "top_k": 5, "mode": "keyword"}
    assert body["ok"] is True
    assert body["results"][0]["file"] == "kelly.md"
    assert set(body["results"][0]) >= {"file", "score", "snippet"}


# ── facts ────────────────────────────────────────────────────────────────────
def test_facts_list(client, plugin_env: Path) -> None:  # noqa: ANN001
    _seed_facts(plugin_env)
    body = client.get("/api/facts?limit=50").get_json()
    assert body["ok"] is True
    assert body["count"] == 3
    texts = {f["fact"] for f in body["facts"]}
    assert "Paul prefers uv over pip" in texts
    # Each fact carries its stored columns.
    sample = body["facts"][0]
    assert set(sample) >= {"id", "fact", "category", "confidence", "active"}


def test_facts_list_filter_by_category(client, plugin_env: Path) -> None:  # noqa: ANN001
    _seed_facts(plugin_env)
    body = client.get("/api/facts?category=preference").get_json()
    assert body["count"] == 1
    assert body["facts"][0]["category"] == "preference"


def test_facts_search(client, plugin_env: Path) -> None:  # noqa: ANN001
    _seed_facts(plugin_env)
    body = client.get("/api/facts/search?q=uv%20pip&limit=5").get_json()
    assert body["ok"] is True
    assert isinstance(body["results"], list)
    # Token-overlap search should surface the uv preference (shares "uv"/"pip").
    assert any("uv" in r["fact"].lower() for r in body["results"])
    for hit in body["results"]:
        assert "score" in hit


def test_facts_search_empty_query(client) -> None:  # noqa: ANN001
    body = client.get("/api/facts/search").get_json()
    assert body == {"ok": True, "query": "", "results": []}


# ── stats ────────────────────────────────────────────────────────────────────
def test_stats_shape(client, plugin_env: Path) -> None:  # noqa: ANN001
    _seed_facts(plugin_env)
    _seed_vectors(plugin_env)
    body = client.get("/api/stats").get_json()
    assert body["ok"] is True
    assert body["vectors"]["available"] is True
    assert body["vectors"]["chunk_count"] == 2
    assert body["facts"]["active"] == 3
    assert body["facts"]["by_category"]


def test_stats_without_index(client) -> None:  # noqa: ANN001
    """Stats must degrade (not 500) when there is no vector index yet."""
    body = client.get("/api/stats").get_json()
    assert body["ok"] is True
    assert body["vectors"]["available"] is False
    # Fact store opens lazily on an empty DB → zero active facts, still available.
    assert body["facts"]["active"] == 0


# ── extract ──────────────────────────────────────────────────────────────────
def test_extract_preview(client) -> None:  # noqa: ANN001
    """Posting text without ``store`` previews heuristic facts, stores nothing."""
    resp = client.post(
        "/api/facts/extract",
        json={"text": "We decided to use uv for package management.", "source": "n.md"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["stored"] is False
    assert body["source"] == "n.md"
    assert isinstance(body["facts"], list)


def test_extract_and_store(client, plugin_env: Path) -> None:  # noqa: ANN001
    resp = client.post(
        "/api/facts/extract",
        json={
            "text": "We decided to use uv for package management. "
            "The bot uses Kelly Criterion for sizing.",
            "source": "note.md",
            "store": True,
        },
    )
    body = resp.get_json()
    assert body["ok"] is True
    assert body["stored"] is True
    assert "tally" in body
    # The store should now hold the ingested facts.
    with facts.open_store(with_embedder=False) as store:
        assert store.count() >= 1


def test_extract_requires_text(client) -> None:  # noqa: ANN001
    resp = client.post("/api/facts/extract", json={"text": "   "})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False
