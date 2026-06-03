#!/usr/bin/env python3
"""
Show what changed in the vault over a given time window, from git history.

Aggregates added/modified/deleted markdown (and config) files across all
commits in the window. Useful for a morning briefing of "what changed
overnight" or a weekly review.

Configuration is read from the environment — no hardcoded paths.

Environment variables:
    VAULT_PATH   Absolute path to the git-tracked vault (required)

Usage:
    python vault_changelog.py                    # Last 24 hours
    python vault_changelog.py --since "7 days ago"
    python vault_changelog.py --markdown         # Markdown-formatted output
    python vault_changelog.py --json             # JSON output
"""

import argparse
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from _bootstrap import ensure_atlas_os

ensure_atlas_os()
from atlas_os import gitutil, scriptkit  # noqa: E402

VAULT = Path(os.path.expanduser(os.environ.get("VAULT_PATH", "."))).resolve()


def run(cmd: list[str]) -> str:
    """Run a git command in the vault, returning stdout.

    Converts a missing ``git`` binary, a timeout, or a non-zero exit into a
    :class:`atlas_os.gitutil.GitError` so the caller surfaces a clean message
    instead of a raw ``CalledProcessError`` traceback.
    """
    try:
        result = subprocess.run(
            cmd, cwd=VAULT, capture_output=True, text=True, check=True, timeout=30
        )
    except FileNotFoundError as exc:
        raise gitutil.GitError("git is not installed or not on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise gitutil.GitError(f"git command timed out: {' '.join(cmd)}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() or f"exit {exc.returncode}"
        raise gitutil.GitError(f"git command failed: {detail}") from exc
    return result.stdout.strip()


@dataclass
class CommitEntry:
    hash: str
    date: str
    subject: str
    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)


def get_commits(since: str) -> list[CommitEntry]:
    log_out = run([
        "git", "log",
        f"--since={since}",
        "--format=%H|%ai|%s",
        "--name-status",
        "--diff-filter=ADM",
        "--",
        "*.md", "scripts/*.py", ".schemas/*", "*.json", "*.yaml", "*.yml",
    ])
    if not log_out:
        return []

    entries: list[CommitEntry] = []
    current: CommitEntry | None = None

    for line in log_out.splitlines():
        if "|" in line and len(line.split("|")) >= 3 and len(line.split("|")[0]) == 40:
            parts = line.split("|", 2)
            current = CommitEntry(hash=parts[0][:8], date=parts[1][:19], subject=parts[2])
            entries.append(current)
        elif line.startswith(("A\t", "M\t", "D\t")) and current is not None:
            code, path = line[0], line[2:]
            if code == "A":
                current.added.append(path)
            elif code == "M":
                current.modified.append(path)
            elif code == "D":
                current.deleted.append(path)
        elif line.startswith("R") and current is not None:
            parts = line.split("\t")
            if len(parts) == 3:
                current.modified.append(parts[2])

    return entries


def aggregate(entries: list[CommitEntry]) -> dict[str, list[str]]:
    added: set[str] = set()
    modified: set[str] = set()
    deleted: set[str] = set()
    for e in entries:
        added.update(e.added)
        modified.update(e.modified)
        deleted.update(e.deleted)
    modified -= added | deleted
    added -= deleted
    return {
        "added": sorted(added),
        "modified": sorted(modified),
        "deleted": sorted(deleted),
    }


def format_markdown(since: str, entries: list[CommitEntry], agg: dict[str, list[str]]) -> str:
    lines: list[str] = []
    total_commits = len(entries)
    total_files = len(agg["added"]) + len(agg["modified"]) + len(agg["deleted"])

    lines.append(f"## Vault changelog since {since}")
    lines.append(f"**{total_commits} commit(s), {total_files} file(s) affected**\n")

    if agg["added"]:
        lines.append(f"### Added ({len(agg['added'])})")
        for f in agg["added"]:
            lines.append(f"- `{f}`")
        lines.append("")

    if agg["modified"]:
        lines.append(f"### Modified ({len(agg['modified'])})")
        for f in agg["modified"]:
            lines.append(f"- `{f}`")
        lines.append("")

    if agg["deleted"]:
        lines.append(f"### Deleted ({len(agg['deleted'])})")
        for f in agg["deleted"]:
            lines.append(f"- `{f}`")
        lines.append("")

    if total_files == 0:
        lines.append("_No changes in this window._\n")

    lines.append("### Commits")
    for e in entries:
        lines.append(f"- `{e.hash}` {e.date[:10]}  {e.subject}")

    return "\n".join(lines)


def format_plain(since: str, entries: list[CommitEntry], agg: dict[str, list[str]]) -> str:
    lines: list[str] = []
    total_commits = len(entries)
    total_files = len(agg["added"]) + len(agg["modified"]) + len(agg["deleted"])

    lines.append(f"Vault changelog since {since}")
    lines.append(f"{total_commits} commit(s), {total_files} file(s) affected\n")

    if agg["added"]:
        lines.append(f"Added ({len(agg['added'])}):")
        for f in agg["added"]:
            lines.append(f"  + {f}")
    if agg["modified"]:
        lines.append(f"\nModified ({len(agg['modified'])}):")
        for f in agg["modified"]:
            lines.append(f"  ~ {f}")
    if agg["deleted"]:
        lines.append(f"\nDeleted ({len(agg['deleted'])}):")
        for f in agg["deleted"]:
            lines.append(f"  - {f}")
    if total_files == 0:
        lines.append("No changes in this window.")

    lines.append("\nCommits:")
    for e in entries:
        lines.append(f"  {e.hash} {e.date[:10]}  {e.subject}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Show vault change history")
    parser.add_argument("--since", default="24 hours ago", help="Time window (git date format)")
    parser.add_argument("--markdown", action="store_true", help="Markdown output")
    parser.add_argument("--json", action="store_true", dest="json_out", help="JSON output")
    args = parser.parse_args()

    if not gitutil.is_git_repo(VAULT):
        scriptkit.fail(
            f"{VAULT} is not a git repository. Run `git init` there first.",
            code=scriptkit.EXIT_CONFIG,
            json_mode=args.json_out,
        )

    entries = get_commits(args.since)
    agg = aggregate(entries)

    if args.json_out:
        print(json.dumps({
            "since": args.since,
            "commits": len(entries),
            "added": agg["added"],
            "modified": agg["modified"],
            "deleted": agg["deleted"],
            "commit_list": [
                {"hash": e.hash, "date": e.date, "subject": e.subject}
                for e in entries
            ],
        }, indent=2))
    elif args.markdown:
        print(format_markdown(args.since, entries, agg))
    else:
        print(format_plain(args.since, entries, agg))


if __name__ == "__main__":
    if not os.environ.get("VAULT_PATH"):
        scriptkit.fail(
            "VAULT_PATH environment variable is not set. See .env.example.",
            code=scriptkit.EXIT_CONFIG,
            json_mode=scriptkit.json_mode_requested(),
        )
    with scriptkit.error_boundary(json_mode=scriptkit.json_mode_requested()):
        main()
