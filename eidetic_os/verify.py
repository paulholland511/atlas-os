"""Structured verification gates — a GROUND-style pre-execution pipeline.

Before Eidetic OS runs autonomous code or deploys a freshly-written skill, it
puts the change through a fixed, ordered sequence of *gates*. Each gate answers
one narrow question — "does it parse?", "do its imports resolve and is it free
of dangerous patterns?", "do its tests pass?", "does it run cleanly under a
sandbox?", "did it touch only the files it was supposed to?" — and the pipeline
stops the moment a *blocking* gate fails, so a syntax error is never followed by
a pointless attempt to execute the file.

This is the orchestration layer that ties together the two security primitives
Eidetic already ships:

* :mod:`eidetic_os.security` — the static AST scanner — backs the IMPORTS gate.
* :mod:`eidetic_os.sandbox` — the resource-limited subprocess runner — backs the
  RUNTIME gate.

The five tiers, in execution order:

``SYNTAX``
    Parse every ``.py`` file with :func:`ast.parse`. A file that does not parse
    hides its behaviour from every later gate, so this is *blocking*.
``IMPORTS``
    Run the static security scanner and reject any ``BLOCK``-level finding
    (``eval``, ``os.system``, ``subprocess(..., shell=True)``, …); separately,
    resolve every third-party top-level import with :func:`importlib.util.find_spec`
    and flag any that is missing. Both failures are *blocking*.
``TESTS``
    Discover test files for the target and run them under ``pytest``, reporting
    pass / fail / skip counts. A failing test is reported but **not** blocking —
    the remaining gates still run so you get the full picture.
``RUNTIME``
    Execute the target's entry point in :func:`eidetic_os.sandbox.run_sandboxed`
    under a wall-clock / memory / CPU budget. A non-zero exit or a timeout is
    *blocking*.
``DIFF``
    If the target lives in a git repository, list the working-tree changes and
    flag any that fall outside the target's own path. Informational, never
    blocking (it is the last gate regardless).

Each gate returns a :class:`TierResult`; the whole run is summarised in a
:class:`VerificationReport`, which serialises to JSON for the audit trail. Every
``verify()`` call also appends one ``verify`` entry to
:mod:`eidetic_os.audit`.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from eidetic_os import audit, gitutil, sandbox, security

# Default wall-clock and memory budgets for the RUNTIME gate; mirror the sandbox
# defaults so the gate behaves like a plain `run_sandboxed` unless overridden.
DEFAULT_RUNTIME_TIMEOUT_SECONDS = 30
DEFAULT_RUNTIME_MEMORY_MB = 256

# How long the TESTS gate lets pytest run before giving up.
DEFAULT_TEST_TIMEOUT_SECONDS = 300

# Entry-point file names tried, in order, when the target is a directory/skill.
_ENTRYPOINT_NAMES: tuple[str, ...] = ("__main__.py", "main.py", "run.py", "app.py")


class Tier(str, Enum):
    """One verification gate. Iteration order is the canonical pipeline order."""

    SYNTAX = "syntax"
    IMPORTS = "imports"
    TESTS = "tests"
    RUNTIME = "runtime"
    DIFF = "diff"


# Canonical order the pipeline runs gates in (also the order JSON/CLI render).
TIER_ORDER: tuple[Tier, ...] = (
    Tier.SYNTAX,
    Tier.IMPORTS,
    Tier.TESTS,
    Tier.RUNTIME,
    Tier.DIFF,
)


@dataclass(frozen=True)
class TierResult:
    """The outcome of a single gate.

    ``passed`` is whether the gate's check succeeded. ``blocking`` is whether a
    *failure* of this gate halts the pipeline — a blocking gate that fails sets
    :attr:`VerificationReport.blocked_at` and no later gate runs. ``details`` is
    a one-line human summary; ``data`` carries gate-specific structured fields
    (test counts, changed files, sandbox output) for the JSON audit record.
    """

    tier: Tier
    passed: bool
    details: str
    duration_ms: int
    blocking: bool = False
    data: Mapping[str, object] = field(default_factory=dict[str, object])

    def to_dict(self) -> dict[str, object]:
        """JSON-ready mapping of this result."""
        return {
            "tier": self.tier.value,
            "passed": self.passed,
            "blocking": self.blocking,
            "details": self.details,
            "duration_ms": self.duration_ms,
            "data": dict(self.data),
        }


@dataclass(frozen=True)
class VerificationReport:
    """The full result of running the pipeline over one target."""

    target: str
    tiers: tuple[TierResult, ...]
    passed: bool
    blocked_at: str | None
    total_duration_ms: int
    timestamp: str

    def to_dict(self) -> dict[str, object]:
        """JSON-ready mapping of the whole report (for the audit trail)."""
        return {
            "target": self.target,
            "passed": self.passed,
            "blocked_at": self.blocked_at,
            "total_duration_ms": self.total_duration_ms,
            "timestamp": self.timestamp,
            "tiers": [result.to_dict() for result in self.tiers],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialise the report to a JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


# ─────────────────────────────────────────────────────────────────────────────
# Tier selection
# ─────────────────────────────────────────────────────────────────────────────
def parse_tiers(spec: str) -> tuple[Tier, ...]:
    """Parse a ``"syntax,imports"`` style spec into ordered, de-duplicated tiers.

    Whitespace and case are ignored. Raises :class:`ValueError` naming the
    offending token (and the valid set) if any entry is unknown.
    """
    names = [part.strip().lower() for part in spec.split(",") if part.strip()]
    if not names:
        raise ValueError("no tiers given")
    valid = {tier.value: tier for tier in Tier}
    selected: list[Tier] = []
    for name in names:
        tier = valid.get(name)
        if tier is None:
            allowed = ", ".join(t.value for t in Tier)
            raise ValueError(f"unknown tier {name!r}; choose from: {allowed}")
        if tier not in selected:
            selected.append(tier)
    return _in_canonical_order(selected)


def _in_canonical_order(tiers: Iterable[Tier]) -> tuple[Tier, ...]:
    """Return ``tiers`` filtered and reordered to the canonical pipeline order."""
    chosen = set(tiers)
    return tuple(tier for tier in TIER_ORDER if tier in chosen)


def _normalise_tiers(tiers: Iterable[Tier | str] | None) -> tuple[Tier, ...]:
    """Coerce the public ``tiers`` argument into an ordered tuple of :class:`Tier`.

    ``None`` means "all tiers". Strings are accepted and resolved the same way
    :func:`parse_tiers` resolves them.
    """
    if tiers is None:
        return TIER_ORDER
    resolved: list[Tier] = []
    valid = {tier.value: tier for tier in Tier}
    for entry in tiers:
        if isinstance(entry, Tier):
            resolved.append(entry)
            continue
        tier = valid.get(entry.strip().lower())
        if tier is None:
            allowed = ", ".join(t.value for t in Tier)
            raise ValueError(f"unknown tier {entry!r}; choose from: {allowed}")
        resolved.append(tier)
    return _in_canonical_order(resolved)


# ─────────────────────────────────────────────────────────────────────────────
# Shared file helpers
# ─────────────────────────────────────────────────────────────────────────────
def _python_files(path: Path) -> list[Path]:
    """Every ``.py`` file the target covers (the file itself, or all under a dir)."""
    if path.is_file():
        return [path] if path.suffix == ".py" else []
    return sorted(p for p in path.rglob("*.py") if p.is_file())


def _relative(file: Path, base: Path) -> str:
    """``file`` shown relative to ``base`` when possible, else its plain string."""
    try:
        return str(file.relative_to(base if base.is_dir() else base.parent))
    except ValueError:
        return str(file)


# ─────────────────────────────────────────────────────────────────────────────
# Tier 1 — SYNTAX
# ─────────────────────────────────────────────────────────────────────────────
def _tier_syntax(path: Path, _ctx: _RunContext) -> _GateOutcome:
    files = _python_files(path)
    if not files:
        return _GateOutcome(True, "no Python files to parse", False, {"files": 0})

    errors: list[str] = []
    for file in files:
        try:
            source = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"{_relative(file, path)}: unreadable ({exc})")
            continue
        try:
            _ = ast.parse(source, filename=str(file))
        except SyntaxError as exc:
            where = f"{_relative(file, path)}:{exc.lineno or 1}"
            errors.append(f"{where}: {exc.msg}")

    if errors:
        return _GateOutcome(
            False,
            "; ".join(errors),
            True,
            {"files": len(files), "errors": errors},
        )
    return _GateOutcome(
        True, f"{len(files)} file(s) parsed cleanly", False, {"files": len(files)}
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tier 2 — IMPORTS
# ─────────────────────────────────────────────────────────────────────────────
def _local_module_names(path: Path) -> set[str]:
    """Module/package names defined alongside the target, to skip when resolving.

    A skill that does ``import helpers`` for its own sibling module must not be
    reported as a missing dependency. For a directory we walk it; for a single
    file we only look at its immediate siblings (walking the whole parent repo
    would be both slow and wrong).
    """
    names: set[str] = set()
    if path.is_dir():
        for file in path.rglob("*.py"):
            names.add(file.stem)
        for child in path.rglob("*"):
            if child.is_dir() and (child / "__init__.py").is_file():
                names.add(child.name)
        names.add(path.name)
    else:
        for sibling in path.parent.glob("*.py"):
            names.add(sibling.stem)
        names.add(path.parent.name)
    return names


def _imported_roots(files: Sequence[Path]) -> set[str]:
    """Top-level module names imported anywhere in ``files`` (absolute imports only).

    Relative imports (``from . import x``) are intra-package and skipped; only the
    leftmost component of each dotted name is kept (``a.b.c`` → ``a``).
    """
    roots: set[str] = set()
    for file in files:
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue  # SYNTAX gate already owns reporting unparseable files.
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue
                if node.module:
                    roots.add(node.module.split(".")[0])
    return roots


def _missing_imports(path: Path) -> list[str]:
    """Third-party top-level imports that do not resolve on this interpreter."""
    local = _local_module_names(path)
    stdlib = sys.stdlib_module_names
    missing: set[str] = set()
    for root in _imported_roots(_python_files(path)):
        if root in stdlib or root in local or root == "__future__":
            continue
        try:
            spec = importlib.util.find_spec(root)
        except (ImportError, ValueError):
            spec = None
        if spec is None:
            missing.add(root)
    return sorted(missing)


def _tier_imports(path: Path, _ctx: _RunContext) -> _GateOutcome:
    report = security.scan_skill(path)
    blocks = report.blocks
    missing = _missing_imports(path)

    problems: list[str] = []
    if blocks:
        problems.extend(f"{b.location(relative_to=path)}: {b.message}" for b in blocks)
    if missing:
        problems.append("unresolved import(s): " + ", ".join(missing))

    data: dict[str, object] = {
        "scanned_files": len(report.scanned_files),
        "blocks": [
            {"code": b.code, "message": b.message, "location": b.location(relative_to=path)}
            for b in blocks
        ],
        "warnings": [
            {"code": w.code, "message": w.message, "location": w.location(relative_to=path)}
            for w in report.warnings
        ],
        "missing_imports": missing,
    }

    if problems:
        # Any BLOCK finding or unresolved import means the code is unsafe or cannot
        # run — both halt the pipeline.
        return _GateOutcome(False, "; ".join(problems), True, data)

    detail = f"imports resolve, no dangerous patterns ({len(report.scanned_files)} file(s) scanned)"
    if report.warnings:
        detail += f"; {len(report.warnings)} warning(s)"
    return _GateOutcome(True, detail, False, data)


# ─────────────────────────────────────────────────────────────────────────────
# Tier 3 — TESTS
# ─────────────────────────────────────────────────────────────────────────────
def _find_tests(path: Path) -> list[Path]:
    """Locate test files for the target.

    For a directory: every ``test_*.py`` / ``*_test.py`` beneath it. For a single
    file ``foo.py``: the file itself if it *is* a test, otherwise the conventional
    ``test_foo.py`` / ``foo_test.py`` next to it or in a sibling ``tests/`` dir.
    """
    if path.is_dir():
        found = {p for p in path.rglob("test_*.py")} | {p for p in path.rglob("*_test.py")}
        return sorted(found)

    stem = path.stem
    if stem.startswith("test_") or stem.endswith("_test"):
        return [path]
    candidates = [
        path.parent / f"test_{stem}.py",
        path.parent / f"{stem}_test.py",
        path.parent / "tests" / f"test_{stem}.py",
    ]
    return [candidate for candidate in candidates if candidate.is_file()]


_PYTEST_COUNT = re.compile(r"(\d+)\s+(passed|failed|skipped|error|errors|xfailed|xpassed)")


def _parse_pytest_counts(output: str) -> dict[str, int]:
    """Pull pass/fail/skip/error counts from pytest's summary line."""
    counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    for match in _PYTEST_COUNT.finditer(output):
        number = int(match.group(1))
        label = match.group(2)
        if label in ("error", "errors"):
            counts["error"] += number
        elif label in counts:
            counts[label] += number
    return counts


def _tier_tests(path: Path, _ctx: _RunContext) -> _GateOutcome:
    test_files = _find_tests(path)
    if not test_files:
        return _GateOutcome(True, "no test files found — skipped", False, {"found": False})

    command = [
        sys.executable,
        "-m",
        "pytest",
        *(str(f) for f in test_files),
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TEST_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return _GateOutcome(
            True, "pytest not available — tests skipped", False, {"found": True, "ran": False}
        )
    except subprocess.TimeoutExpired:
        return _GateOutcome(
            False,
            f"tests timed out after {DEFAULT_TEST_TIMEOUT_SECONDS}s",
            False,
            {"found": True, "ran": True, "timed_out": True},
        )

    combined = proc.stdout + proc.stderr
    # pytest exit code 5 == "no tests were collected": not a failure for our gate.
    if proc.returncode == 5:
        return _GateOutcome(
            True,
            "no tests collected — skipped",
            False,
            {"found": True, "ran": True, "exit_code": 5},
        )

    counts = _parse_pytest_counts(combined)
    passed = proc.returncode == 0
    detail = (
        f"{counts['passed']} passed, {counts['failed']} failed, "
        f"{counts['skipped']} skipped, {counts['error']} error(s)"
    )
    data: dict[str, object] = {
        "found": True,
        "ran": True,
        "exit_code": proc.returncode,
        "counts": counts,
        "files": [str(f) for f in test_files],
    }
    # Test failures are reported but do not halt the pipeline (non-blocking).
    return _GateOutcome(passed, detail, False, data)


# ─────────────────────────────────────────────────────────────────────────────
# Tier 4 — RUNTIME
# ─────────────────────────────────────────────────────────────────────────────
def _entrypoint(path: Path) -> Path | None:
    """The ``.py`` file to execute for the RUNTIME gate, or None if there isn't one."""
    if path.is_file():
        return path if path.suffix == ".py" else None
    for name in _ENTRYPOINT_NAMES:
        candidate = path / name
        if candidate.is_file():
            return candidate
    return None


def _tier_runtime(path: Path, ctx: _RunContext) -> _GateOutcome:
    entry = _entrypoint(path)
    if entry is None:
        return _GateOutcome(
            True, "no runnable entry point — runtime skipped", False, {"ran": False}
        )

    result = sandbox.run_sandboxed(
        entry,
        timeout=ctx.runtime_timeout,
        memory_mb=ctx.runtime_memory_mb,
        allow_network=ctx.allow_network,
    )
    data: dict[str, object] = {
        "ran": True,
        "entry": str(entry),
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "duration_seconds": result.duration_seconds,
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:],
    }

    if result.timed_out:
        return _GateOutcome(
            False, f"timed out after {ctx.runtime_timeout}s", True, data
        )
    if result.exit_code != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()
        reason = tail[-1] if tail else "no output"
        return _GateOutcome(
            False, f"exited with code {result.exit_code}: {reason}", True, data
        )
    return _GateOutcome(
        True, f"clean exit (code 0) in {result.duration_seconds}s", False, data
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tier 5 — DIFF
# ─────────────────────────────────────────────────────────────────────────────
def _git_repo_root(path: Path) -> Path | None:
    """Top of the git working tree containing ``path``, or None if untracked."""
    start = path if path.is_dir() else path.parent
    try:
        result = gitutil.run(["rev-parse", "--show-toplevel"], start, check=False)
    except gitutil.GitError:
        return None
    if result.ok and result.stdout.strip():
        return Path(result.stdout.strip())
    return None


def _parse_porcelain(output: str) -> list[str]:
    """Repo-relative paths from ``git status --porcelain`` output.

    Handles renamed entries (``R  old -> new``) by keeping the new path.
    """
    paths: list[str] = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        entry = line[3:]
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1]
        paths.append(entry.strip().strip('"'))
    return paths


def _tier_diff(path: Path, _ctx: _RunContext) -> _GateOutcome:
    repo = _git_repo_root(path)
    if repo is None:
        return _GateOutcome(
            True, "not in a git repository — diff skipped", False, {"git": False}
        )

    try:
        result = gitutil.run(["status", "--porcelain"], repo, check=False)
    except gitutil.GitError as exc:
        return _GateOutcome(
            True, f"git status unavailable — diff skipped ({exc})", False, {"git": False}
        )
    if not result.ok:
        return _GateOutcome(
            True, "git status unavailable — diff skipped", False, {"git": False}
        )

    changed = _parse_porcelain(result.stdout)
    try:
        scope = str(path.resolve().relative_to(repo.resolve()))
    except ValueError:
        scope = ""  # target is the repo root itself — everything is in scope.

    def _within_scope(rel_path: str) -> bool:
        if not scope or scope == ".":
            return True
        return rel_path == scope or rel_path.startswith(scope + "/")

    unexpected = [c for c in changed if not _within_scope(c)]
    data: dict[str, object] = {
        "git": True,
        "scope": scope or "<repo root>",
        "changed": changed,
        "unexpected": unexpected,
    }

    if unexpected:
        shown = ", ".join(unexpected[:10])
        if len(unexpected) > 10:
            shown += f", … (+{len(unexpected) - 10} more)"
        # Informational: surfaced loudly but never halts the pipeline.
        return _GateOutcome(
            False, f"{len(unexpected)} change(s) outside '{scope}': {shown}", False, data
        )
    return _GateOutcome(
        True, f"{len(changed)} changed file(s), all within scope", False, data
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline driver
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _RunContext:
    """Per-run settings threaded into each gate."""

    runtime_timeout: int
    runtime_memory_mb: int
    allow_network: bool


@dataclass(frozen=True)
class _GateOutcome:
    """A gate's raw verdict before it is timed and wrapped in a :class:`TierResult`."""

    passed: bool
    details: str
    blocking: bool
    data: Mapping[str, object]


# Dispatch table: each gate is a pure ``(path, ctx) -> _GateOutcome``.
_GATES = {
    Tier.SYNTAX: _tier_syntax,
    Tier.IMPORTS: _tier_imports,
    Tier.TESTS: _tier_tests,
    Tier.RUNTIME: _tier_runtime,
    Tier.DIFF: _tier_diff,
}


def _run_gate(tier: Tier, path: Path, ctx: _RunContext) -> TierResult:
    """Run one gate, timing it and converting any crash into a blocking failure."""
    start = time.monotonic()
    try:
        outcome = _GATES[tier](path, ctx)
    except Exception as exc:  # noqa: BLE001 - a crashing gate must fail closed, not propagate
        outcome = _GateOutcome(False, f"gate crashed: {exc}", True, {"error": str(exc)})
    duration_ms = int((time.monotonic() - start) * 1000)
    return TierResult(
        tier=tier,
        passed=outcome.passed,
        details=outcome.details,
        duration_ms=duration_ms,
        blocking=outcome.blocking,
        data=outcome.data,
    )


def verify(
    code_path: str | Path,
    tiers: Iterable[Tier | str] | None = None,
    *,
    runtime_timeout: int = DEFAULT_RUNTIME_TIMEOUT_SECONDS,
    runtime_memory_mb: int = DEFAULT_RUNTIME_MEMORY_MB,
    allow_network: bool = False,
    log: bool = True,
    trigger: str | None = None,
) -> VerificationReport:
    """Run the verification pipeline over ``code_path`` and return its report.

    Gates run in canonical order (:data:`TIER_ORDER`), restricted to ``tiers`` if
    given. The pipeline stops at the first *blocking* gate that fails — its name
    is recorded in :attr:`VerificationReport.blocked_at` and no later gate runs.
    The overall report passes only when every gate that ran passed.

    Parameters
    ----------
    code_path:
        File or skill directory to verify.
    tiers:
        Subset of tiers to run (``Tier`` values or their string names). ``None``
        runs all five.
    runtime_timeout, runtime_memory_mb, allow_network:
        Budgets handed to the sandbox for the RUNTIME gate.
    log:
        Append a ``verify`` entry to the audit trail (default on).
    trigger:
        Audit trigger label; defaults to ``$EIDETIC_TRIGGER`` or ``"cli"``.

    Raises :class:`FileNotFoundError` if ``code_path`` does not exist and
    :class:`ValueError` if ``tiers`` names an unknown gate.
    """
    path = Path(code_path)
    if not path.exists():
        raise FileNotFoundError(f"no such path: {path}")

    selected = _normalise_tiers(tiers)
    ctx = _RunContext(
        runtime_timeout=runtime_timeout,
        runtime_memory_mb=runtime_memory_mb,
        allow_network=allow_network,
    )

    results: list[TierResult] = []
    blocked_at: str | None = None
    start = time.monotonic()
    for tier in selected:
        result = _run_gate(tier, path, ctx)
        results.append(result)
        if not result.passed and result.blocking:
            blocked_at = tier.value
            break
    total_duration_ms = int((time.monotonic() - start) * 1000)

    report = VerificationReport(
        target=str(path),
        tiers=tuple(results),
        passed=all(r.passed for r in results) and blocked_at is None,
        blocked_at=blocked_at,
        total_duration_ms=total_duration_ms,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    if log:
        _log_report(report, trigger)
    return report


def _log_report(report: VerificationReport, trigger: str | None) -> None:
    """Append one ``verify`` entry to the audit trail summarising the run."""
    changes = [
        f"{r.tier.value}: {'pass' if r.passed else 'fail'}" for r in report.tiers
    ]
    if report.passed:
        error: str | None = None
    elif report.blocked_at is not None:
        error = f"blocked at {report.blocked_at} tier"
    else:
        failed = [r.tier.value for r in report.tiers if not r.passed]
        error = f"gate failure: {', '.join(failed)}"
    _ = audit.log_action(
        action="verify",
        trigger=trigger or os.environ.get("EIDETIC_TRIGGER", "cli"),
        status="success" if report.passed else "error",
        changes=changes,
        context=f"verify {report.target}",
        error=error,
        duration=report.total_duration_ms / 1000,
    )
