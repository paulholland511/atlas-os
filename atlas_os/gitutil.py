"""Resilient git helpers for the vault automation scripts.

The nightly ``vault_commit`` / ``vault_changelog`` jobs run unattended against a
git repo that other processes (Obsidian Git, manual commits, a previous crashed
run) may have touched. The recurring failure modes are:

* a stale ``.git/index.lock`` / ``.git/HEAD.lock`` left by an interrupted git
  process, which makes every subsequent git command fail with
  *"Another git process seems to be running"*;
* the path simply not being a git repository;
* a git command failing and dumping a traceback on the caller.

This module centralises lock cleanup and command execution so the scripts get a
clean, structured result instead of a traceback.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

# Lock files git leaves in ``.git/`` (and ``.git/refs`` via the glob below) when
# a process is interrupted mid-operation.
_TOP_LEVEL_LOCKS = ("index.lock", "HEAD.lock", "config.lock", "packed-refs.lock")


class GitError(RuntimeError):
    """A git command failed; carries a clean, human-readable message."""


@dataclass(frozen=True)
class GitResult:
    """The outcome of a git invocation."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def git_dir(repo: Path) -> Path:
    """Path to the repo's ``.git`` directory (not resolved through worktrees)."""
    return repo / ".git"


def is_git_repo(repo: Path) -> bool:
    """Return ``True`` if ``repo`` is the top of a git working tree."""
    if (repo / ".git").exists():
        return True
    result = run(["rev-parse", "--is-inside-work-tree"], repo, check=False)
    return result.ok and result.stdout.strip() == "true"


def clear_stale_locks(repo: Path) -> list[str]:
    """Remove stale git lock files and prune worktrees; return what was removed.

    Safe to call before any write operation: lock files are ephemeral by design,
    so deleting one left by a dead process simply unblocks the next command. We
    also ``git worktree prune`` to clear references to worktrees that no longer
    exist (another common source of "cannot lock ref" errors).
    """
    removed: list[str] = []
    gd = git_dir(repo)
    if not gd.is_dir():
        return removed

    candidates = [gd / name for name in _TOP_LEVEL_LOCKS]
    refs = gd / "refs"
    if refs.is_dir():
        candidates.extend(refs.rglob("*.lock"))

    for lock in candidates:
        if lock.exists():
            try:
                lock.unlink()
                removed.append(str(lock.relative_to(repo)))
            except OSError:
                pass  # best-effort; the git command will surface a clear error

    # Prune dangling worktree administrative files (ignored if it fails).
    run(["worktree", "prune"], repo, check=False)
    return removed


def run(
    args: list[str],
    repo: Path,
    *,
    check: bool = False,
    timeout: float = 30.0,
) -> GitResult:
    """Run ``git <args>`` in ``repo`` and return a :class:`GitResult`.

    Never raises for a non-zero exit unless ``check=True`` (then
    :class:`GitError`). Missing ``git`` binary and timeouts are also converted to
    :class:`GitError` so callers never see a raw traceback.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {' '.join(args)} timed out after {timeout}s.") from exc

    result = GitResult(proc.returncode, proc.stdout, proc.stderr)
    if check and not result.ok:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise GitError(f"git {' '.join(args)} failed: {detail}")
    return result
