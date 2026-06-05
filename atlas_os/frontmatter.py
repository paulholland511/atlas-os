"""YAML frontmatter validation — the gate before any automated commit.

Atlas commits to your vault unattended (the nightly auto-commit, session capture,
indexer touch-ups). A single malformed automated edit — a broken YAML block, a
date written in the wrong shape, a dropped required key — would propagate into
the vault and break every downstream consumer (RAG chunking strips frontmatter,
the dashboard reads tags, Obsidian renders properties). This module is the hard
precondition: **no automated commit proceeds with frontmatter it would break.**

What it checks
--------------
For each Markdown file:

* the frontmatter block (``---`` … ``---`` at the top) is **well-formed YAML**
  that parses to a mapping (not a list or scalar);
* every **required key** is present (configurable; empty by default so existing
  notes are not retroactively rejected);
* every **date field** (``date``/``created``/``updated`` by default) holds a real
  date — either a YAML date or an ISO-8601 string — not ``"yestrday"``.

A file with *no* frontmatter is **valid** (plenty of notes are plain Markdown);
only a frontmatter block that is *present but broken* fails.

Entry points
------------
* :func:`validate_frontmatter` — one file → :class:`ValidationResult`.
* :func:`validate_before_commit` — every **git-staged** Markdown file in a vault
  → :class:`ValidationReport`; ``report.ok`` is the commit gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

from atlas_os import gitutil

# Keys whose values must parse as a real date unless they are empty/absent.
DEFAULT_DATE_FIELDS: tuple[str, ...] = ("date", "created", "updated", "modified")

_FENCE = "---"


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of validating one file's frontmatter."""

    file_path: Path
    ok: bool
    errors: tuple[str, ...]
    had_frontmatter: bool

    def __bool__(self) -> bool:
        return self.ok


@dataclass(frozen=True)
class ValidationReport:
    """Aggregate result over a set of files (e.g. everything staged to commit)."""

    results: tuple[ValidationResult, ...]

    @property
    def ok(self) -> bool:
        """``True`` only if every file validated — the commit gate."""
        return all(r.ok for r in self.results)

    @property
    def failures(self) -> tuple[ValidationResult, ...]:
        return tuple(r for r in self.results if not r.ok)

    def __bool__(self) -> bool:
        return self.ok


def split_frontmatter(text: str) -> tuple[str | None, int]:
    """Return ``(raw_yaml_block, body_start_line)`` or ``(None, 0)`` if absent.

    The block must start on the very first line with a ``---`` fence and end at
    the next ``---`` fence. ``raw_yaml_block`` excludes the fences; it is
    ``None`` when the file has no frontmatter at all (a valid state).
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FENCE:
        return None, 0
    for index in range(1, len(lines)):
        if lines[index].strip() == _FENCE:
            return "\n".join(lines[1:index]), index + 1
    # Opening fence with no closing fence — an unterminated block.
    return "\n".join(lines[1:]), len(lines)


def _is_valid_date(value: object) -> bool:
    """True if ``value`` is a date/datetime or an ISO-8601 date string."""
    if isinstance(value, (date, datetime)):
        return True
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return True  # empty value — treated as "unset", not malformed.
        try:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False
    return False


def validate_text(
    text: str,
    *,
    required: tuple[str, ...] = (),
    date_fields: tuple[str, ...] = DEFAULT_DATE_FIELDS,
    label: Path | str = "<text>",
) -> ValidationResult:
    """Validate the frontmatter of an in-memory document.

    Pure — no file I/O — so it is trivial to unit-test and is reused by
    :func:`validate_frontmatter`. ``label`` is only used for the result's
    ``file_path``.
    """
    path = label if isinstance(label, Path) else Path(str(label))
    raw, end = split_frontmatter(text)
    if raw is None:
        return ValidationResult(path, ok=True, errors=(), had_frontmatter=False)

    # An opening fence with no closing fence is malformed.
    lines = text.splitlines()
    closed = any(line.strip() == _FENCE for line in lines[1:end])
    if not closed:
        return ValidationResult(
            path, ok=False,
            errors=("unterminated frontmatter block (missing closing '---')",),
            had_frontmatter=True,
        )

    errors: list[str] = []
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        detail = str(exc).splitlines()[0] if str(exc) else "invalid YAML"
        return ValidationResult(
            path, ok=False, errors=(f"broken YAML: {detail}",), had_frontmatter=True
        )

    if data is None:
        data = {}
    if not isinstance(data, dict):
        return ValidationResult(
            path, ok=False,
            errors=(f"frontmatter must be a mapping, got {type(data).__name__}",),
            had_frontmatter=True,
        )

    for key in required:
        if key not in data or data[key] in (None, ""):
            errors.append(f"missing required key: {key!r}")

    for key in date_fields:
        if key in data and data[key] not in (None, "") and not _is_valid_date(data[key]):
            errors.append(f"invalid date in {key!r}: {data[key]!r}")

    return ValidationResult(
        path, ok=not errors, errors=tuple(errors), had_frontmatter=True
    )


def validate_frontmatter(
    file_path: Path,
    *,
    required: tuple[str, ...] = (),
    date_fields: tuple[str, ...] = DEFAULT_DATE_FIELDS,
) -> ValidationResult:
    """Validate one Markdown file's frontmatter on disk.

    A missing or unreadable file is reported as a failure (the automation should
    not commit something it cannot read). Files with no frontmatter pass.
    """
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        return ValidationResult(
            file_path, ok=False, errors=(f"could not read file: {exc}",),
            had_frontmatter=False,
        )
    return validate_text(
        text, required=required, date_fields=date_fields, label=file_path
    )


def _staged_markdown(vault_path: Path) -> list[Path]:
    """Markdown files currently staged in ``vault_path`` (added/copied/modified)."""
    result = gitutil.run(
        ["diff", "--cached", "--name-only", "--diff-filter=ACM"], vault_path,
        check=False,
    )
    if not result.ok:
        return []
    files: list[Path] = []
    for rel in result.stdout.splitlines():
        rel = rel.strip()
        if rel.endswith(".md"):
            files.append(vault_path / rel)
    return files


def validate_before_commit(
    vault_path: Path,
    *,
    files: list[Path] | None = None,
    required: tuple[str, ...] = (),
    date_fields: tuple[str, ...] = DEFAULT_DATE_FIELDS,
) -> ValidationReport:
    """Validate every staged Markdown file before an automated commit.

    Pass an explicit ``files`` list to validate an arbitrary set; otherwise the
    git index of ``vault_path`` is consulted. ``report.ok`` is ``False`` if any
    file's frontmatter is broken, which the caller uses to **abort the commit**.
    """
    targets = files if files is not None else _staged_markdown(vault_path)
    results = tuple(
        validate_frontmatter(path, required=required, date_fields=date_fields)
        for path in targets
    )
    return ValidationReport(results)
