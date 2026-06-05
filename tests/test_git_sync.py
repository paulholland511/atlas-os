"""Tests for atlas_os.git_sync and the iCloud fault-in helper.

The headline guarantee is that an *automated* sync never corrupts or loses the
user's work, so the suite races a simulated remote change against a concurrent
local (human) edit and asserts the human side always survives — either merged
cleanly under ``-X ours`` or, for an unresolvable conflict, left untouched by an
aborted merge.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas_os import fileio, git_sync


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture()
def repos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """A bare upstream with two clones: ``local`` (under test) and ``other``.

    ``other`` stands in for a second device that pushes changes the local
    automated sync must integrate. Audit writes go to a temp file and the git
    identity is pinned so commits succeed hermetically.
    """
    monkeypatch.setenv("ATLAS_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(var, "Atlas Test")
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(var, "atlas-test@example.com")

    upstream = tmp_path / "upstream.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(upstream)],
        check=True, capture_output=True,
    )
    local = tmp_path / "local"
    subprocess.run(
        ["git", "clone", str(upstream), str(local)], check=True, capture_output=True
    )
    (local / "note.md").write_text(
        "---\ntitle: Note\n---\nline one\nline two\n", encoding="utf-8"
    )
    _git(local, "add", "-A")
    _git(local, "commit", "-m", "init")
    _git(local, "push", "-u", "origin", "main")

    other = tmp_path / "other"
    subprocess.run(
        ["git", "clone", str(upstream), str(other)], check=True, capture_output=True
    )
    return SimpleNamespace(local=local, other=other, upstream=upstream, branch="main")


def _push_from_other(repos: SimpleNamespace, mutate) -> None:
    """Apply ``mutate(other_path)``, commit, and push from the ``other`` clone."""
    mutate(repos.other)
    _git(repos.other, "add", "-A")
    _git(repos.other, "commit", "-m", "remote change")
    _git(repos.other, "push", "origin", "main")


class TestSafeSync:
    def test_up_to_date_when_nothing_changed(self, repos: SimpleNamespace) -> None:
        result = git_sync.safe_sync(repos.local)
        assert result.status == "up_to_date"
        assert result.ok

    def test_merges_non_conflicting_remote_change(self, repos: SimpleNamespace) -> None:
        _push_from_other(
            repos,
            lambda p: (p / "new.md").write_text("---\ntitle: New\n---\nx\n", "utf-8"),
        )
        result = git_sync.safe_sync(repos.local)
        assert result.status == "synced"
        assert (repos.local / "new.md").exists()
        # The pre-existing local note is untouched.
        assert "line one" in (repos.local / "note.md").read_text(encoding="utf-8")

    def test_favours_local_on_content_conflict(self, repos: SimpleNamespace) -> None:
        # Remote rewrites line two…
        _push_from_other(
            repos,
            lambda p: (p / "note.md").write_text(
                "---\ntitle: Note\n---\nline one\nREMOTE EDIT\n", "utf-8"
            ),
        )
        # …while the human concurrently rewrites the same line locally and commits.
        (repos.local / "note.md").write_text(
            "---\ntitle: Note\n---\nline one\nHUMAN EDIT\n", encoding="utf-8"
        )
        _git(repos.local, "add", "-A")
        _git(repos.local, "commit", "-m", "human edit")

        result = git_sync.safe_sync(repos.local)

        assert result.status == "synced"
        body = (repos.local / "note.md").read_text(encoding="utf-8")
        # The human's edit wins; the remote's conflicting edit does not clobber it.
        assert "HUMAN EDIT" in body
        assert "REMOTE EDIT" not in body

    def test_aborts_on_unresolvable_conflict(self, repos: SimpleNamespace) -> None:
        # Remote deletes the note…
        _push_from_other(repos, lambda p: (p / "note.md").unlink())
        # …while the human edits it locally and commits → modify/delete conflict
        # that -X ours cannot auto-resolve.
        (repos.local / "note.md").write_text(
            "---\ntitle: Note\n---\nline one\nKEEP THIS\n", encoding="utf-8"
        )
        _git(repos.local, "add", "-A")
        _git(repos.local, "commit", "-m", "human edit")

        result = git_sync.safe_sync(repos.local)

        assert result.status == "conflict"
        assert result.aborted
        assert result.conflicts  # at least one conflicting file reported
        # The merge was aborted: the human's file and content are intact…
        assert (repos.local / "note.md").exists()
        assert "KEEP THIS" in (repos.local / "note.md").read_text(encoding="utf-8")
        # …and no merge is left in progress.
        assert not (repos.local / ".git" / "MERGE_HEAD").exists()

    def test_skips_non_git_directory(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        result = git_sync.safe_sync(plain)
        assert result.status == "skipped"
        assert not result.ok

    def test_skips_repo_without_remote(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        repo = tmp_path / "solo"
        repo.mkdir()
        subprocess.run(["git", "init", "-b", "main", str(repo)],
                       check=True, capture_output=True)
        result = git_sync.safe_sync(repo)
        assert result.status == "skipped"
        assert "remote" in result.message

    def test_clears_stale_lock_before_sync(self, repos: SimpleNamespace) -> None:
        import os
        import time

        lock = repos.local / ".git" / "index.lock"
        lock.write_text("", encoding="utf-8")
        old = time.time() - 600  # 10 minutes ago → stale
        os.utime(lock, (old, old))

        result = git_sync.safe_sync(repos.local)

        assert any("index.lock" in name for name in result.locks_cleared)
        assert not lock.exists()

    def test_logs_to_audit_trail(self, repos: SimpleNamespace) -> None:
        from atlas_os import audit

        git_sync.safe_sync(repos.local)
        entries = audit.read_audit(action="sync")
        assert entries
        assert entries[-1]["action"] == "sync"


class TestPendingConflicts:
    def test_empty_for_clean_repo(self, repos: SimpleNamespace) -> None:
        assert git_sync.pending_conflicts(repos.local) == ()


class TestEnsureMaterialized:
    def test_returns_true_for_local_file(self, tmp_path: Path) -> None:
        path = tmp_path / "f.md"
        path.write_text("hello", encoding="utf-8")
        assert fileio.ensure_materialized(path) is True

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(fileio.MissingFileError):
            fileio.ensure_materialized(tmp_path / "nope.md")

    def test_waits_then_succeeds_when_file_faults_in(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "f.md"
        path.write_text("hi", encoding="utf-8")
        # Dataless for the first two checks, materialised afterwards.
        states = iter([True, True, False, False, False])
        monkeypatch.setattr(fileio, "is_dataless", lambda _p: next(states))
        triggered: list[Path] = []
        result = fileio.ensure_materialized(
            path, timeout=5,
            trigger=triggered.append, sleep=lambda _s: None,
            clock=lambda: 0.0, poll=0.01,
        )
        assert result is True
        assert triggered == [path]

    def test_times_out_when_never_materialises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "f.md"
        path.write_text("hi", encoding="utf-8")
        monkeypatch.setattr(fileio, "is_dataless", lambda _p: True)
        clock = iter([0.0, 0.0, 10.0, 20.0, 30.0, 40.0])
        result = fileio.ensure_materialized(
            path, timeout=5,
            trigger=lambda _p: None, sleep=lambda _s: None,
            clock=lambda: next(clock), poll=0.01,
        )
        assert result is False
