"""Tests for the lightweight web dashboard (``atlas_os.dashboard``).

Two layers are covered:

* The **data layer** (``atlas_os.dashboard.data``) — pure functions that read
  live Atlas OS state and shape it for templates. These import without Flask and
  are tested directly against temp vaults / audit logs / vector stores.
* The **Flask routes** (``atlas_os.dashboard.app``) — exercised through Flask's
  test client. Skipped automatically if Flask isn't installed, so the suite
  still passes on a core install without the ``dashboard`` extra.

Everything is hermetic: each test points ``VAULT_PATH`` / ``RAG_DIR`` /
``ATLAS_AUDIT_PATH`` at temp paths, so nothing touches the real vault.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas_os import audit, vectordb
from atlas_os.dashboard import data

# The route tests need Flask (the optional `dashboard` extra). Skip them cleanly
# when it isn't installed rather than erroring the whole module.
flask = pytest.importorskip("flask", reason="dashboard extra (flask) not installed")


@pytest.fixture()
def dash_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the whole stack at a temp vault and return its root."""
    vault = tmp_path / "vault"
    (vault / ".rag").mkdir(parents=True, exist_ok=True)
    (vault / ".atlas").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("RAG_DIR", str(vault / ".rag"))
    monkeypatch.setenv("ATLAS_AUDIT_PATH", str(vault / ".atlas" / "audit.jsonl"))
    return vault


@pytest.fixture()
def client(dash_env: Path):  # noqa: ANN201 - Flask test client
    """A Flask test client wired to the temp-vault environment."""
    from atlas_os.dashboard.app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def _seed_audit() -> None:
    """Write a handful of audit entries across actions, triggers, and statuses."""
    audit.log_action("embed", "scheduled", "success", changes=["3 new"], duration=1.2)
    audit.log_action("commit", "cli", "success", changes=["commit abc123"])
    audit.log_action("health", "scheduled", "error", error="LLM unreachable")
    audit.log_action("session", "manual", "skipped")


def _seed_vectors(rag_dir: Path) -> None:
    """Build a tiny SQLite vector store with two files / three chunks."""
    db = vectordb.default_db_path(rag_dir)
    with vectordb.VectorStore(db) as store:
        store.add_vectors([
            {"id": "a::0", "file": "notes/a.md", "chunk_text": "alpha", "embedding": [0.1, 0.2, 0.3]},
            {"id": "a::1", "file": "notes/a.md", "chunk_text": "beta", "embedding": [0.2, 0.3, 0.4]},
            {"id": "b::0", "file": "notes/b.md", "chunk_text": "gamma", "embedding": [0.3, 0.4, 0.5]},
        ])
    (rag_dir / "last_embed.txt").write_text("1000000000.0")


# ── data layer: health ──────────────────────────────────────────────────────
def test_health_report_shape(dash_env: Path) -> None:
    report = data.health_report()
    assert set(report) == {"categories", "summary", "overall"}
    assert report["overall"] in {"ok", "warn", "fail"}
    assert report["summary"]["total"] == sum(
        report["summary"][k] for k in ("ok", "warn", "fail")
    )
    # Every check carries a CSS state class for the indicator dots.
    for category in report["categories"]:
        for check in category["checks"]:
            assert check["state"] in {"ok", "warn", "fail"}


# ── data layer: audit ───────────────────────────────────────────────────────
def test_audit_page_newest_first_and_actions(dash_env: Path) -> None:
    _seed_audit()
    page = data.audit_page()
    assert page.total == 4
    # Newest first: the last-written entry (session) leads.
    assert page.entries[0]["action"] == "session"
    # The dropdown offers every distinct action.
    assert set(page.actions) == {"embed", "commit", "health", "session"}


def test_audit_page_action_filter(dash_env: Path) -> None:
    _seed_audit()
    page = data.audit_page(action="embed")
    assert page.total == 1
    assert page.entries[0]["action"] == "embed"


def test_audit_page_pagination(dash_env: Path) -> None:
    for i in range(30):
        audit.log_action("embed", "cli", "success", context=f"run {i}")
    page1 = data.audit_page(per_page=25, page=1)
    assert len(page1.entries) == 25
    assert page1.pages == 2
    page2 = data.audit_page(per_page=25, page=2)
    assert len(page2.entries) == 5
    # Out-of-range pages clamp to the last page rather than erroring.
    assert data.audit_page(per_page=25, page=99).page == 2


def test_audit_page_bad_since_does_not_raise(dash_env: Path) -> None:
    _seed_audit()
    page = data.audit_page(since="not-a-date")
    assert page.total == 4  # invalid filter is ignored, not fatal


# ── data layer: scheduled tasks ──────────────────────────────────────────────
def test_scheduled_tasks_reports_last_run(dash_env: Path) -> None:
    audit.log_action("embed", "scheduled", "success", changes=["1 new"])
    tasks = data.scheduled_tasks()
    assert tasks  # the install ships schedulable skills
    by_slug = {t["slug"]: t for t in tasks}
    # nightly-rag-incremental maps to the "embed" audit action.
    incremental = by_slug.get("nightly-rag-incremental")
    assert incremental is not None
    assert incremental["last_run"] is not None
    assert incremental["last_run"]["state"] == "ok"
    # Nothing is installed in a fresh temp vault.
    assert incremental["installed"] is False


# ── data layer: skills ───────────────────────────────────────────────────────
def test_skills_overview_and_detail(dash_env: Path) -> None:
    overview = data.skills_overview()
    assert overview["skills"]
    assert overview["packs"]
    slug = overview["skills"][0]["slug"]

    detail = data.skill_detail(slug)
    assert detail is not None
    assert detail["slug"] == slug
    assert detail["body"]  # SKILL.md content is loaded

    assert data.skill_detail("definitely-not-a-real-skill") is None


# ── data layer: vector stats ─────────────────────────────────────────────────
def test_vector_stats_absent(dash_env: Path) -> None:
    stats = data.vector_stats()
    assert stats["available"] is False
    assert "embed" in stats["reason"]


def test_vector_stats_present(dash_env: Path) -> None:
    _seed_vectors(dash_env / ".rag")
    stats = data.vector_stats()
    assert stats["available"] is True
    assert stats["chunk_count"] == 3
    assert stats["file_count"] == 2
    assert stats["last_embed"] is not None
    assert stats["last_embed"]["stale"] is True  # year-2001 timestamp is old


# ── data layer: search (no embeddings endpoint) ──────────────────────────────
def test_run_search_empty_query(dash_env: Path) -> None:
    result = data.run_search("")
    assert result["ok"] is True
    assert result["results"] == []


def test_run_search_keyword_mode_offline(dash_env: Path) -> None:
    # Keyword mode is pure BM25 (no endpoint). Against an empty store it should
    # return cleanly with no results, not error.
    _seed_vectors(dash_env / ".rag")
    result = data.run_search("alpha", mode="keyword")
    assert result["ok"] is True
    assert isinstance(result["results"], list)


# ── routes ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "path",
    ["/health", "/audit", "/scheduled", "/skills", "/vectors", "/search"],
)
def test_routes_render(client, dash_env: Path, path: str) -> None:  # noqa: ANN001
    resp = client.get(path)
    assert resp.status_code == 200
    assert b"Atlas OS" in resp.data


def test_index_redirects_to_health(client) -> None:  # noqa: ANN001
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/health" in resp.headers["Location"]


def test_audit_route_with_filters(client, dash_env: Path) -> None:  # noqa: ANN001
    _seed_audit()
    resp = client.get("/audit?action=embed")
    assert resp.status_code == 200
    assert b"embed" in resp.data


def test_skill_detail_route(client, dash_env: Path) -> None:  # noqa: ANN001
    overview = data.skills_overview()
    slug = overview["skills"][0]["slug"]
    resp = client.get(f"/skills/{slug}")
    assert resp.status_code == 200
    assert slug.encode() in resp.data


def test_unknown_skill_404(client, dash_env: Path) -> None:  # noqa: ANN001
    resp = client.get("/skills/nope-not-real")
    assert resp.status_code == 404


def test_install_pack_route_no_target(client, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    # With no VAULT_PATH / ATLAS_SKILLS_DIR there's no install target; the route
    # should flash an error and redirect, not crash.
    monkeypatch.delenv("VAULT_PATH", raising=False)
    monkeypatch.delenv("ATLAS_SKILLS_DIR", raising=False)
    monkeypatch.delenv("RAG_DIR", raising=False)
    resp = client.post("/skills/install-pack/knowledge")
    assert resp.status_code == 302
    assert "/skills" in resp.headers["Location"]


def test_install_pack_unknown(client, dash_env: Path) -> None:  # noqa: ANN001
    resp = client.post("/skills/install-pack/no-such-pack", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Unknown pack" in resp.data


def test_install_pack_succeeds(client, dash_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    skills_dir = dash_env / ".claude" / "skills"
    monkeypatch.setenv("ATLAS_SKILLS_DIR", str(skills_dir))
    resp = client.post("/skills/install-pack/knowledge", follow_redirects=True)
    assert resp.status_code == 200
    assert b"installed" in resp.data
    # At least one skill from the pack landed on disk.
    assert any(skills_dir.glob("*/SKILL.md"))
