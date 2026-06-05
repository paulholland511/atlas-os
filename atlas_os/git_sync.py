"""Safe automated git sync — favour the human, never clobber their work.

Atlas runs git against your vault unattended: it commits notes, and (when the
vault has a remote) it pulls changes other devices pushed. The cardinal rule for
*automated* git is simple and absolute: **an automated operation must never
corrupt or lose work you did by hand.** This module is the merge half of that
guarantee (the commit half lives in :mod:`atlas_os.frontmatter`).

Strategy — "favour local user changes"
---------------------------------------
:func:`safe_sync` integrates remote changes with ``git merge -X ours``: where an
automated/remote change and a concurrent human edit touch the *same* hunk, the
**local (human) side wins**. Non-conflicting remote changes still merge in
normally, so you keep other devices' edits — you only ever lose the *automated*
side of a true conflict, never your own.

If a merge cannot be resolved even with ``-X ours`` (an add/add or rename/rename
structural conflict), Atlas **aborts the merge**, leaves your working tree
exactly as it was, records the conflict in the audit trail, and surfaces it so a
human can resolve it. It never force-resolves against you.

Every outcome — synced, already-up-to-date, conflict-aborted, skipped, error —
is written to the JSONL audit trail with the files and reason.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from atlas_os import audit, gitutil

# git's "favour our side on conflict" merge option, used for every automated pull.
_FAVOUR_LOCAL = "-X"
_FAVOUR_LOCAL_VALUE = "ours"


@dataclass(frozen=True)
class SyncResult:
    """The outcome of a :func:`safe_sync` call.

    ``status`` is one of:

    * ``"up_to_date"`` — nothing to pull.
    * ``"synced"`` — remote changes merged in cleanly (favouring local on conflict).
    * ``"conflict"`` — a true conflict could not be auto-resolved; the merge was
      aborted and the working tree left untouched. ``conflicts`` lists the files.
    * ``"skipped"`` — preconditions not met (not a repo, no remote/upstream).
    * ``"error"`` — git failed unexpectedly; ``message`` carries the detail.
    """

    status: str
    message: str
    conflicts: tuple[str, ...] = ()
    locks_cleared: tuple[str, ...] = ()
    merged_commit: str | None = None

    @property
    def ok(self) -> bool:
        """``True`` for the non-failure outcomes (synced / up-to-date)."""
        return self.status in {"synced", "up_to_date"}

    @property
    def aborted(self) -> bool:
        return self.status == "conflict"


@dataclass
class _Plan:
    """Internal: resolved remote/branch context for a sync."""

    remote: str
    branch: str
    ref: str = field(init=False)

    def __post_init__(self) -> None:
        self.ref = f"{self.remote}/{self.branch}"


def _current_branch(vault: Path) -> str | None:
    result = gitutil.run(["rev-parse", "--abbrev-ref", "HEAD"], vault, check=False)
    branch = result.stdout.strip()
    if not result.ok or not branch or branch == "HEAD":
        return None
    return branch


def _has_remote(vault: Path, remote: str) -> bool:
    result = gitutil.run(["remote"], vault, check=False)
    return remote in result.stdout.split()


def unmerged_files(vault: Path) -> tuple[str, ...]:
    """Files currently in a conflicted (unmerged) state in ``vault``."""
    result = gitutil.run(
        ["diff", "--name-only", "--diff-filter=U"], vault, check=False
    )
    if not result.ok:
        return ()
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())


def pending_conflicts(vault: Path) -> tuple[str, ...]:
    """Public alias for :func:`unmerged_files` — used by ``atlas doctor``."""
    return unmerged_files(vault)


def _log(status: str, *, changes: list[str], context: str, error: str | None,
         trigger: str) -> None:
    audit.log_action(
        action="sync", trigger=trigger,
        status="success" if status in {"synced", "up_to_date"}
        else "skipped" if status in {"skipped", "conflict"} else "error",
        changes=changes, context=context, error=error,
    )


def safe_sync(
    vault_path: Path | str,
    *,
    remote: str = "origin",
    branch: str | None = None,
    trigger: str | None = None,
) -> SyncResult:
    """Pull remote vault changes with a favour-local merge; never overwrite a human.

    Steps: clear genuinely-stale git locks → fetch ``remote`` → if the remote has
    no new commits, return ``up_to_date`` → otherwise ``git merge -X ours`` the
    remote branch. A clean merge returns ``synced``; an unresolvable conflict is
    **aborted** (working tree restored) and returned as ``conflict``. Missing repo
    or remote returns ``skipped``. Every path writes one audit entry.

    ``branch`` defaults to the vault's current branch. ``trigger`` defaults to the
    ``ATLAS_TRIGGER`` env var (``scheduled`` for unattended runs) else ``cli``.
    """
    vault = Path(os.path.expanduser(str(vault_path)))
    trig = trigger or os.environ.get("ATLAS_TRIGGER", "cli")
    context = f"safe_sync {vault}"

    if not gitutil.is_git_repo(vault):
        result = SyncResult("skipped", f"{vault} is not a git repository")
        _log(result.status, changes=[], context=context,
             error=result.message, trigger=trig)
        return result

    # Reclaim locks left by a crashed prior run before touching the index.
    locks = tuple(gitutil.clean_stale_locks(vault))

    if not _has_remote(vault, remote):
        result = SyncResult(
            "skipped", f"no remote named {remote!r}", locks_cleared=locks
        )
        _log(result.status, changes=list(locks), context=context,
             error=result.message, trigger=trig)
        return result

    resolved_branch = branch or _current_branch(vault)
    if resolved_branch is None:
        result = SyncResult(
            "skipped", "could not resolve current branch (detached HEAD?)",
            locks_cleared=locks,
        )
        _log(result.status, changes=list(locks), context=context,
             error=result.message, trigger=trig)
        return result

    plan = _Plan(remote, resolved_branch)

    fetch = gitutil.run(["fetch", remote, resolved_branch], vault, check=False)
    if not fetch.ok:
        detail = fetch.stderr.strip() or "git fetch failed"
        result = SyncResult("error", detail, locks_cleared=locks)
        _log(result.status, changes=list(locks), context=context,
             error=detail, trigger=trig)
        return result

    # Nothing upstream to merge? Then we're already current.
    ahead = gitutil.run(
        ["rev-list", "--count", f"HEAD..{plan.ref}"], vault, check=False
    )
    behind_count = ahead.stdout.strip() if ahead.ok else "0"
    if behind_count in ("", "0"):
        result = SyncResult(
            "up_to_date", "already up to date", locks_cleared=locks
        )
        _log(result.status, changes=list(locks), context=context,
             error=None, trigger=trig)
        return result

    # Favour-local merge. -X ours resolves *content* conflicts toward us; a
    # structural conflict (add/add, rename/rename) still fails and is aborted.
    merge = gitutil.run(
        ["merge", _FAVOUR_LOCAL, _FAVOUR_LOCAL_VALUE, "--no-edit", plan.ref],
        vault, check=False,
    )
    if not merge.ok:
        conflicts = unmerged_files(vault)
        gitutil.run(["merge", "--abort"], vault, check=False)
        message = (
            f"merge with {plan.ref} could not be auto-resolved; aborted to "
            f"protect local changes ({len(conflicts)} conflicting file(s))"
        )
        result = SyncResult(
            "conflict", message, conflicts=conflicts, locks_cleared=locks
        )
        _log(result.status, changes=list(conflicts), context=context,
             error=message, trigger=trig)
        return result

    head = gitutil.run(["rev-parse", "--short", "HEAD"], vault, check=False)
    commit = head.stdout.strip() if head.ok else None
    result = SyncResult(
        "synced", f"merged {plan.ref} (favouring local on conflict)",
        locks_cleared=locks, merged_commit=commit,
    )
    _log(result.status, changes=[f"merged {plan.ref}"], context=context,
         error=None, trigger=trig)
    return result
