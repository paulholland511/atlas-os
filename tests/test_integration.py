"""End-to-end integration tests for the ``atlas`` CLI.

Unlike the hermetic unit suites (which monkeypatch internals or stub the
network), these tests run *real* pipelines: a real temp vault on disk, real git
repositories, real subprocess invocations of the pipeline scripts, and a real
(local) HTTP server standing in for the LLM endpoint. Only genuinely external
side effects — the LLM backend and the SMTP server — are mocked, and even those
are mocked with real local sockets rather than in-process patches, because the
commands shell out to a child process that wouldn't see a monkeypatch.

The shared fixtures live in ``tests/conftest.py``:

* ``sample_vault``   — a temp vault of sample markdown files, env pointed at it.
* ``git_vault``      — the same, initialised as a git repo with one commit.
* ``llm_server``     — factory for local OpenAI-compatible mock endpoints.

Every test here is marked ``@pytest.mark.integration`` so the slower end-to-end
suite can be run (or skipped) on its own::

    pytest -m integration
    pytest -m "not integration"
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from atlas_os import audit, cli
from atlas_os.cli import app

pytestmark = pytest.mark.integration

runner = CliRunner()


# ──────────────────────────────────────────────────────────────────────────────
# Local helpers / fixtures specific to the integration suite
# ──────────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def wizard_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Run ``atlas init`` against a sandbox, never the developer's checkout.

    ``init`` writes ``.env`` to ``repo_root() or cwd`` and calls
    ``os.environ.update`` (which bypasses monkeypatch's tracking) to feed its
    doctor run — so we force ``repo_root`` to ``None``, chdir into the sandbox,
    and snapshot/restore the environment around the test.
    """
    monkeypatch.setattr(cli, "repo_root", lambda: None)
    monkeypatch.setattr(cli, "detect_endpoints", lambda *a, **k: [])
    monkeypatch.chdir(tmp_path)
    saved = os.environ.copy()
    try:
        yield tmp_path
    finally:
        os.environ.clear()
        os.environ.update(saved)


def _embed_env(monkeypatch: pytest.MonkeyPatch, base_url: str) -> None:
    """Point the embed pipeline at a mock LLM endpoint."""
    monkeypatch.setenv("EMBED_URL", f"{base_url}/v1/embeddings")
    monkeypatch.setenv("EMBED_MODEL", "fake-embed")


# ──────────────────────────────────────────────────────────────────────────────
# 1. Full init → doctor cycle
# ──────────────────────────────────────────────────────────────────────────────
def test_init_then_doctor_cycle(
    wizard_sandbox: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`atlas init --yes` scaffolds a working setup; `atlas doctor` confirms it."""
    vault = tmp_path / "vault"

    init = runner.invoke(app, ["init", "--yes", "--vault", str(vault)])
    assert init.exit_code == 0, init.output

    # .env written into the sandbox, pointing at the chosen vault.
    env_path = wizard_sandbox / ".env"
    assert env_path.is_file()
    assert f"VAULT_PATH={vault}" in env_path.read_text(encoding="utf-8")

    # Vault scaffolded: the standard directory tree plus the seeded wiki notes.
    for sub in (".atlas", ".rag", "wiki"):
        assert (vault / sub).is_dir(), f"missing {sub}/"
    assert (vault / "wiki" / "index.md").is_file()
    assert (vault / ".git").is_dir()  # init also git-inits the vault

    # init ran the doctor itself and declared the setup ready.
    assert "Verifying your setup" in init.output
    assert "You're ready" in init.output

    # Now run the doctor as a standalone command against the freshly built vault.
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.delenv("EMBED_URL", raising=False)
    doctor = runner.invoke(app, ["doctor"])

    # No FAILs (vault exists + is a git repo), so doctor exits 0.
    assert doctor.exit_code == 0, doctor.output
    assert "Vault path" in doctor.output
    assert str(vault) in doctor.output
    assert "Vault git" in doctor.output
    # The embeddings endpoint isn't running, so RAG/embeddings are WARN not FAIL.
    assert "0 FAIL" in doctor.output


# ──────────────────────────────────────────────────────────────────────────────
# 2. Embed pipeline (mocked LLM endpoint)
# ──────────────────────────────────────────────────────────────────────────────
def test_embed_pipeline_writes_vectors(
    sample_vault: Path,
    llm_server: Callable[..., str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`atlas embed --full` embeds the sample vault into a vectors.json store."""
    _embed_env(monkeypatch, llm_server())

    result = runner.invoke(app, ["embed", "--full"])
    assert result.exit_code == 0, result.output

    vectors_file = sample_vault / ".rag" / "vectors.json"
    assert vectors_file.is_file()
    vectors = json.loads(vectors_file.read_text(encoding="utf-8"))

    # One short file → one chunk → one vector, so the count matches the md files.
    md_files = list(sample_vault.rglob("*.md"))
    assert len(vectors) == len(md_files)
    for entry in vectors:
        assert entry["file"]
        assert isinstance(entry["embedding"], list) and entry["embedding"]


# ──────────────────────────────────────────────────────────────────────────────
# 3. Commit cycle
# ──────────────────────────────────────────────────────────────────────────────
def test_commit_cycle_creates_commit(git_vault: Path) -> None:
    """`atlas commit` stages new files and writes a categorised commit."""
    import subprocess

    # Add a fresh note so there is something to commit.
    (git_vault / "research" / "new-note.md").write_text(
        "---\ntags: [research]\n---\n# New Note\n\nFresh content.\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["commit"])
    assert result.exit_code == 0, result.output
    assert "Committed" in result.output

    # The latest commit exists with the expected "Vault update: …" subject.
    log = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=git_vault,
        capture_output=True,
        text=True,
        check=True,
    )
    subject = log.stdout.strip()
    assert subject.startswith("Vault update:")
    assert "new" in subject  # one new file was added

    # The note we added is now tracked — it no longer shows in the porcelain
    # status. (The only thing left untracked is the audit log the commit command
    # itself writes to .atlas/ *after* committing, which is expected.)
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=git_vault,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "new-note.md" not in status.stdout
    # The new note is reachable in the committed tree.
    tree = subprocess.run(
        ["git", "ls-files", "research/new-note.md"],
        cwd=git_vault,
        capture_output=True,
        text=True,
        check=True,
    )
    assert tree.stdout.strip() == "research/new-note.md"


# ──────────────────────────────────────────────────────────────────────────────
# 4. Changelog generation
# ──────────────────────────────────────────────────────────────────────────────
def test_changelog_generates_markdown(git_vault: Path) -> None:
    """`atlas changelog --markdown` summarises recent commits as markdown."""
    import subprocess

    # Create a second commit so the changelog window has content to report.
    (git_vault / "projects" / "second.md").write_text(
        "# Second\n\nAnother note.\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=git_vault, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "Add second note"], cwd=git_vault, check=True
    )

    result = runner.invoke(app, ["changelog", "--since", "1 day ago", "--markdown"])
    assert result.exit_code == 0, result.output
    assert "## Vault changelog since" in result.output
    assert "### Commits" in result.output
    assert "Add second note" in result.output


# ──────────────────────────────────────────────────────────────────────────────
# 5. Skill install flow
# ──────────────────────────────────────────────────────────────────────────────
def test_skills_list_then_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`atlas skills list` loads skills; `atlas skills install` copies + fills one."""
    listing = runner.invoke(app, ["skills", "list"])
    assert listing.exit_code == 0, listing.output
    assert "vault-lint-report" in listing.output
    assert "atlas-daily-report-email" in listing.output

    install_dir = tmp_path / "installed-skills"
    monkeypatch.setenv("ATLAS_SKILLS_DIR", str(install_dir))
    monkeypatch.setenv("USER_EMAIL", "paul@example.com")

    install = runner.invoke(app, ["skills", "install", "atlas-daily-report-email"])
    assert install.exit_code == 0, install.output

    installed = install_dir / "atlas-daily-report-email" / "SKILL.md"
    assert installed.is_file()
    body = installed.read_text(encoding="utf-8")
    # The {{USER_EMAIL}} placeholder was substituted from the environment.
    assert "paul@example.com" in body
    assert "{{USER_EMAIL}}" not in body
    assert "installed" in install.output


# ──────────────────────────────────────────────────────────────────────────────
# 6. Audit trail round-trip
# ──────────────────────────────────────────────────────────────────────────────
def test_audit_round_trip(git_vault: Path) -> None:
    """An audited command appears in `atlas audit tail` and on disk with detail."""
    # `atlas changelog` is an audited pipeline command and succeeds on a git vault.
    changelog = runner.invoke(app, ["changelog", "--since", "1 day ago"])
    assert changelog.exit_code == 0, changelog.output

    tail = runner.invoke(app, ["audit", "tail"])
    assert tail.exit_code == 0, tail.output
    assert "changelog" in tail.output
    assert "success" in tail.output

    # Verify the on-disk entry carries the correct action / trigger / status.
    entries = audit.read_audit(limit=10)
    changelog_entries = [e for e in entries if e["action"] == "changelog"]
    assert changelog_entries, "no changelog audit entry was written"
    entry = changelog_entries[-1]
    assert entry["trigger"] == "cli"
    assert entry["status"] == "success"
    assert entry["context"].startswith("atlas changelog")


# ──────────────────────────────────────────────────────────────────────────────
# 7. Health check (JSON output)
# ──────────────────────────────────────────────────────────────────────────────
def test_health_json_structure(git_vault: Path) -> None:
    """`atlas health --json` emits a parseable report of per-subsystem results."""
    result = runner.invoke(app, ["health", "--json"])
    # Subsystems like the dashboard aren't running, so the overall exit code may
    # be non-zero; the JSON report is still printed and must be well-formed.
    payload = json.loads(result.output)

    assert isinstance(payload, list) and payload
    names = {item["name"] for item in payload}
    assert {"Vault", "RAG Pipeline", "Git"} <= names

    for item in payload:
        assert item["status"] in {"up", "degraded", "down"}
        assert "detail" in item
        assert isinstance(item["checks"], list)
        for check in item["checks"]:
            assert "name" in check
            assert "ok" in check
            assert "detail" in check


# ──────────────────────────────────────────────────────────────────────────────
# 8. Backend detection (multiple mock endpoints)
# ──────────────────────────────────────────────────────────────────────────────
def test_backends_detect_multiple_endpoints(
    llm_server: Callable[..., str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`atlas backends` probes and reports every configured, reachable backend."""
    lmstudio_url = llm_server(models=("local-chat-model",))
    ollama_url = llm_server(models=("llama3", "nomic-embed-text"))
    monkeypatch.setenv("LM_STUDIO_URL", lmstudio_url)
    monkeypatch.setenv("OLLAMA_URL", ollama_url)
    # Don't let a stray force-env short-circuit the probe.
    monkeypatch.delenv("ATLAS_LLM_BACKEND", raising=False)

    result = runner.invoke(app, ["backends"])
    assert result.exit_code == 0, result.output

    out = result.output
    assert "LM Studio" in out
    assert "Ollama" in out
    # Models advertised by each mock endpoint surface in the report.
    assert "local-chat-model" in out
    assert "llama3" in out
    # The first reachable backend (LM Studio, by precedence) becomes active.
    assert "active backend: lmstudio" in out


# ──────────────────────────────────────────────────────────────────────────────
# 9. Email — graceful failure paths
# ──────────────────────────────────────────────────────────────────────────────
def test_email_requires_smtp_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """`atlas email` refuses to run (exit 2) when SMTP isn't configured."""
    monkeypatch.delenv("SENDER_EMAIL", raising=False)
    monkeypatch.delenv("SMTP_APP_PASSWORD", raising=False)

    result = runner.invoke(
        app, ["email", "--to", "a@b.c", "--subject", "Hi", "--body", "x"]
    )
    assert result.exit_code == 2
    assert "SENDER_EMAIL" in result.output or "SMTP_APP_PASSWORD" in result.output


def test_email_reports_unreachable_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    """With creds set but no SMTP server, the send fails gracefully with a message."""
    monkeypatch.setenv("SENDER_EMAIL", "atlas@example.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "not-a-real-password")
    # Point at a port nothing is listening on so the connection is refused fast.
    monkeypatch.setenv("SMTP_SERVER", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", "1")

    result = runner.invoke(
        app, ["email", "--to", "you@example.com", "--subject", "Hi", "--body", "x"]
    )
    # The script catches the connection error and prints a diagnostic rather than
    # crashing with a traceback.
    assert "ERROR sending email" in result.output


# ──────────────────────────────────────────────────────────────────────────────
# 10. Full lifecycle: init → embed → commit → changelog → audit
# ──────────────────────────────────────────────────────────────────────────────
def test_full_lifecycle(
    wizard_sandbox: Path,
    tmp_path: Path,
    llm_server: Callable[..., str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole pipeline in sequence, exercising the real commands together."""
    import subprocess

    vault = tmp_path / "vault"

    # 1. init — scaffold the vault and git-init it.
    init = runner.invoke(app, ["init", "--yes", "--vault", str(vault)])
    assert init.exit_code == 0, init.output
    assert (vault / ".git").is_dir()

    # The wizard's os.environ.update set VAULT_PATH; re-pin the whole sandbox env
    # explicitly so each subsequent command resolves the same vault, RAG store,
    # audit log, and git identity.
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("RAG_DIR", str(vault / ".rag"))
    monkeypatch.setenv("ATLAS_AUDIT_PATH", str(vault / ".atlas" / "audit.jsonl"))
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(var, "Atlas Test")
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(var, "atlas-test@example.com")
    _embed_env(monkeypatch, llm_server())

    # 2. embed — build the RAG store (mocked endpoint).
    embed = runner.invoke(app, ["embed", "--full"])
    assert embed.exit_code == 0, embed.output
    assert (vault / ".rag" / "vectors.json").is_file()

    # 3. commit — the embed produced new untracked files in the vault.
    (vault / "research").mkdir(parents=True, exist_ok=True)
    (vault / "research" / "lifecycle.md").write_text(
        "# Lifecycle\n\nEnd-to-end note.\n", encoding="utf-8"
    )
    commit = runner.invoke(app, ["commit"])
    assert commit.exit_code == 0, commit.output
    assert "Committed" in commit.output
    head = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=vault,
        capture_output=True,
        text=True,
        check=True,
    )
    assert head.stdout.strip().startswith("Vault update:")

    # 4. changelog — summarise what just changed.
    changelog = runner.invoke(app, ["changelog", "--since", "1 day ago", "--markdown"])
    assert changelog.exit_code == 0, changelog.output
    assert "## Vault changelog since" in changelog.output

    # 5. audit tail — the embed, commit, and changelog runs are all recorded.
    tail = runner.invoke(app, ["audit", "tail"])
    assert tail.exit_code == 0, tail.output
    actions = {e["action"] for e in audit.read_audit(limit=20)}
    assert {"embed", "commit", "changelog"} <= actions
