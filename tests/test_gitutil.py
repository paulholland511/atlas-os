"""Tests for atlas_os.gitutil — repo detection, lock cleanup, command running."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas_os import gitutil


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A throwaway initialised git repo."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


class TestIsGitRepo:
    def test_true_for_initialised_repo(self, repo: Path) -> None:
        assert gitutil.is_git_repo(repo) is True

    def test_false_for_plain_dir(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        assert gitutil.is_git_repo(plain) is False


class TestClearStaleLocks:
    def test_removes_index_and_head_locks(self, repo: Path) -> None:
        (repo / ".git" / "index.lock").write_text("", encoding="utf-8")
        (repo / ".git" / "HEAD.lock").write_text("", encoding="utf-8")

        removed = gitutil.clear_stale_locks(repo)

        assert not (repo / ".git" / "index.lock").exists()
        assert not (repo / ".git" / "HEAD.lock").exists()
        assert any("index.lock" in r for r in removed)
        assert any("HEAD.lock" in r for r in removed)

    def test_removes_ref_locks(self, repo: Path) -> None:
        refs_heads = repo / ".git" / "refs" / "heads"
        refs_heads.mkdir(parents=True, exist_ok=True)
        (refs_heads / "main.lock").write_text("", encoding="utf-8")

        removed = gitutil.clear_stale_locks(repo)
        assert not (refs_heads / "main.lock").exists()
        assert any("main.lock" in r for r in removed)

    def test_noop_when_no_locks(self, repo: Path) -> None:
        assert gitutil.clear_stale_locks(repo) == []

    def test_noop_for_non_repo(self, tmp_path: Path) -> None:
        assert gitutil.clear_stale_locks(tmp_path) == []


class TestRun:
    def test_successful_command(self, repo: Path) -> None:
        result = gitutil.run(["rev-parse", "--is-inside-work-tree"], repo)
        assert result.ok is True
        assert result.stdout.strip() == "true"

    def test_failure_without_check_returns_nonzero(self, tmp_path: Path) -> None:
        # Not a repo → git status fails, but no exception without check.
        plain = tmp_path / "plain"
        plain.mkdir()
        result = gitutil.run(["status"], plain, check=False)
        assert result.ok is False

    def test_failure_with_check_raises_giterror(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        with pytest.raises(gitutil.GitError):
            gitutil.run(["status"], plain, check=True)
