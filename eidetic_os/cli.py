"""The unified ``eidetic`` command-line interface.

Subcommands:

* ``eidetic init``     — interactive onboarding: detect your LLM, write .env,
                       scaffold the vault, install templates.
* ``eidetic doctor``   — validate the whole setup and report OK / WARN / FAIL.
* ``eidetic backends`` — show detected LLM backends; ``test`` runs an inference.
* ``eidetic skills``   — list/show/install agent skills; ``--sync`` writes the
                       catalog; ``packs``/``install-pack`` for curated bundles
* ``eidetic embed``    — RAG pipeline           (wraps scripts/embed_vault.py)
* ``eidetic graph``    — knowledge graph        (wraps scripts/build_graph.py)
* ``eidetic commit``   — auto-commit the vault  (wraps scripts/vault_commit.py)
* ``eidetic changelog``— vault changelog        (wraps scripts/vault_changelog.py)
* ``eidetic health``   — full health probe      (wraps scripts/health_check.py)
* ``eidetic email``    — send an email          (wraps scripts/send_email.py)
* ``eidetic schemas``  — enforce frontmatter     (wraps schemas/enforce_schemas.py)
* ``eidetic session``  — save Cowork transcripts (wraps scripts/save_sessions.py)
* ``eidetic consolidate``— sleeptime memory consolidation of recent session logs
* ``eidetic audit``    — inspect the append-only audit trail (show | tail | export)
* ``eidetic dashboard``— launch the local web dashboard (needs the dashboard extra)
* ``eidetic serve``    — start the Obsidian-plugin REST API (needs the dashboard extra)
* ``eidetic extensions``— list/inspect optional extensions (trading, voice, jobs)
* ``eidetic mcp``      — run Eidetic OS as an MCP server; ``list-tools`` to inspect.
                       ``eidetic skills run <name>`` serves one skill over MCP.

Domain-specific functionality (trading briefings, voice/TTS, the job tracker)
lives in **extensions** (``eidetic_os.extensions``), discovered and loaded onto
this app at startup so the core stays decoupled from every domain module. See
``eidetic extensions list``. The ``eidetic trading`` command, for instance, is now
provided by the bundled trading extension rather than the core.

Every script-wrapping command appends an entry to the audit trail (see
``eidetic_os.audit``) recording what ran, how it was triggered, the outcome,
duration, and what changed.

Configuration is read from the environment; a ``.env`` in the current directory
or the repo root is auto-loaded on startup.
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import requests
import typer
from dotenv import load_dotenv

from eidetic_os import __version__, audit
from eidetic_os import backends as llm_backends
from eidetic_os import facts as facts_engine
from eidetic_os import fileio, frontmatter, git_sync, gitutil
from eidetic_os import _skills, marketplace, packs, security
from eidetic_os._paths import repo_root, schemas_dir, scripts_dir, templates_dir
from eidetic_os._probe import Endpoint, detect_endpoints
from eidetic_os._skills import default_catalog_path, load_skills, render_catalog
from eidetic_os.security import Severity

# ── Auto-load .env (repo root first, then cwd, which wins) ────────────────────
_root = repo_root()
if _root is not None:
    load_dotenv(_root / ".env")
load_dotenv(Path.cwd() / ".env", override=True)

app = typer.Typer(
    add_completion=True,
    no_args_is_help=True,
    help="Eidetic OS — your local-first personal AI operating system.",
)

# Context settings that let a wrapper command forward arbitrary flags to the
# underlying script (e.g. `eidetic embed --full --batch-size 16`).
_PASSTHROUGH = {"allow_extra_args": True, "ignore_unknown_options": True}


def _echo_ok(msg: str) -> None:
    typer.secho(f"  ✓ {msg}", fg=typer.colors.GREEN)


def _echo_warn(msg: str) -> None:
    typer.secho(f"  ! {msg}", fg=typer.colors.YELLOW)


def _echo_fail(msg: str) -> None:
    typer.secho(f"  ✗ {msg}", fg=typer.colors.RED)


_SEVERITY_COLOR: dict[Severity, str] = {
    Severity.BLOCK: typer.colors.RED,
    Severity.WARN: typer.colors.YELLOW,
    Severity.INFO: typer.colors.BLUE,
}


def _print_security_report(report: security.SecurityReport, label: str) -> None:
    """Render a :class:`SecurityReport` grouped by severity, most-severe first."""
    counts = report.counts
    typer.secho(
        f"\nSecurity scan of {label} — "
        f"{counts['BLOCK']} block · {counts['WARN']} warn · {counts['INFO']} info "
        f"({len(report.scanned_files)} file(s) scanned)\n",
        bold=True,
    )
    if not report.findings:
        _echo_ok("no dangerous patterns found")
        return
    for severity in Severity:
        findings = report.with_severity(severity)
        if not findings:
            continue
        colour = _SEVERITY_COLOR[severity]
        for finding in findings:
            badge = typer.style(f"{severity.value:<5}", fg=colour, bold=True)
            loc = finding.location(relative_to=report.skill_path)
            typer.echo(f"  {badge} {loc}  {finding.message}")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"eidetic-os {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    _version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Show the Eidetic OS version and exit.",
    ),
) -> None:
    """Eidetic OS command-line interface."""


# ─────────────────────────────────────────────────────────────────────────────
# Script wrappers
# ─────────────────────────────────────────────────────────────────────────────
def _require_env(*names: str) -> None:
    """Exit with a clear error if any required environment variable is unset.

    `.env` is auto-loaded at import time, so by the time a command runs the
    values should already be present. This catches the common "forgot to set
    VAULT_PATH" case *before* shelling out to the underlying script.
    """
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        _echo_fail(f"Missing required env var(s): {', '.join(missing)}")
        typer.echo("  Set them in .env (see .env.example) or run `eidetic init`.")
        raise typer.Exit(code=2)


def _run(path: Path, args: list[str]) -> None:
    if not path.exists():
        _echo_fail(f"Script not found: {path}")
        raise typer.Exit(code=2)
    raise typer.Exit(code=subprocess.call([sys.executable, str(path), *args]))


def _extract_changes(output: str) -> list[str]:
    """Best-effort summary of what an action changed, from its stdout.

    Most pipeline scripts print a final JSON object (with ``--json``) or a
    human summary. We try to parse the last non-empty line as JSON and pull out
    well-known fields; on anything unexpected we return an empty list rather
    than guess. The audit entry is still written with status + duration.
    """
    for raw in reversed(output.splitlines()):
        raw = raw.strip()
        if not raw:
            continue
        if not (raw.startswith("{") and raw.endswith("}")):
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, dict):
            return []
        changes: list[str] = []
        for key in ("new", "modified", "deleted", "added", "skipped", "embedded"):
            value = data.get(key)
            if isinstance(value, int) and value > 0:
                changes.append(f"{value} {key}")
        if data.get("committed") and data.get("commit"):
            changes.append(f"commit {data['commit']}")
        if data.get("sent") or data.get("delivered"):
            recipient = data.get("to") or data.get("recipient")
            changes.append(f"email sent to {recipient}" if recipient else "email sent")
        return changes
    return []


def _run_audited(
    action: str, path: Path, args: list[str], context: str
) -> None:
    """Run a pipeline script, stream its output, and append an audit entry.

    Output is passed through to the terminal unchanged (so progress and errors
    look exactly as before) while being captured for the audit ``changes``
    summary. ``trigger`` defaults to ``cli`` but a scheduler can set
    ``EIDETIC_TRIGGER=scheduled`` to mark unattended runs.
    """
    if not path.exists():
        _echo_fail(f"Script not found: {path}")
        audit.log_action(
            action, os.environ.get("EIDETIC_TRIGGER", "cli"), "error",
            context=context, error=f"script not found: {path}",
        )
        raise typer.Exit(code=2)

    trigger = os.environ.get("EIDETIC_TRIGGER", "cli")
    start = time.monotonic()
    captured: list[str] = []
    proc = subprocess.Popen(
        [sys.executable, str(path), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdout is not None
    while True:
        chunk = proc.stdout.read(4096)
        if not chunk:
            break
        sys.stdout.write(chunk)
        sys.stdout.flush()
        captured.append(chunk)
    code = proc.wait()
    duration = time.monotonic() - start
    output = "".join(captured)

    status = "success" if code == 0 else "error"
    error = None if code == 0 else (output[-2000:].strip() or f"exit code {code}")
    audit.log_action(
        action=action,
        trigger=trigger,
        status=status,
        changes=_extract_changes(output) if code == 0 else [],
        context=context,
        error=error,
        duration=duration,
    )
    raise typer.Exit(code=code)


def _context_for(action: str, args: list[str]) -> str:
    """Human-readable 'why it ran' string for the audit entry."""
    extra = " " + " ".join(args) if args else ""
    return f"eidetic {action}{extra}".strip()


@app.command(context_settings=_PASSTHROUGH)
def embed(ctx: typer.Context) -> None:
    """Build/refresh the RAG vector store (--full | --incremental | --test N | …)."""
    _require_env("VAULT_PATH")
    _run_audited("embed", scripts_dir() / "embed_vault.py", ctx.args,
                 _context_for("embed", ctx.args))


@app.command(context_settings=_PASSTHROUGH)
def search(ctx: typer.Context) -> None:
    """Query the RAG store: hybrid (BM25 + vector) search with reranking.

    Wraps scripts/rag_search.py. Pass a query plus optional filters, e.g.
    `eidetic search "kelly criterion" --folder research --tag trading --top-k 10`.
    Modes: --mode hybrid|vector|keyword. See `eidetic search --help` via the script
    for the full flag list (--file-type, --since, --until, --no-rerank, --json).
    """
    _require_env("VAULT_PATH")
    _run(scripts_dir() / "rag_search.py", ctx.args)


@app.command(name="migrate-vectors")
def migrate_vectors(
    rag_dir: Path = typer.Option(
        None, "--rag-dir",
        help="RAG directory holding the vector store(s) (defaults to $RAG_DIR or $VAULT_PATH/.rag).",
    ),
    to: str = typer.Option(
        None, "--to",
        help="Target vector backend (sqlite|lancedb|chroma). Copies the current "
             "store into that engine. Omit to import a legacy vectors.json into SQLite.",
    ),
    from_backend: str = typer.Option(
        None, "--from",
        help="Source backend for --to (defaults to $VECTOR_BACKEND, else sqlite).",
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite the target if it already holds vectors."
    ),
) -> None:
    """Migrate the vector store — between backends (``--to``) or from legacy JSON.

    With ``--to lancedb`` (or ``chroma`` / ``sqlite``) this copies every chunk
    from your current backend into the target engine, shows progress, and verifies
    the counts match — then you set ``VECTOR_BACKEND`` in ``.env`` to switch over.
    Without ``--to`` it imports a legacy ``vectors.json`` into the SQLite store, as
    before (embeds also auto-migrate on first run).
    """
    rag = rag_dir or _resolve_rag_dir()
    if rag is None:
        _echo_fail("No RAG directory: pass --rag-dir, or set RAG_DIR / VAULT_PATH.")
        raise typer.Exit(code=2)

    if to is not None:
        _migrate_between_backends(rag, to=to, from_backend=from_backend, force=force)
        return

    _migrate_legacy_json(rag, force=force)


def _migrate_between_backends(
    rag: Path, *, to: str, from_backend: str | None, force: bool
) -> None:
    """Copy the current vector store into another backend engine (``--to``)."""
    from eidetic_os import vector_backend

    try:
        target_name = vector_backend.resolve_backend_name(to)
        source_name = vector_backend.resolve_backend_name(from_backend)
    except ValueError as exc:
        _echo_fail(str(exc))
        raise typer.Exit(code=2) from exc

    if source_name == target_name:
        _echo_warn(
            f"source and target are both '{source_name}' — nothing to migrate "
            "(pass --from to copy between two different engines)."
        )
        raise typer.Exit(code=0)

    try:
        source = vector_backend.get_backend(rag, name=source_name)
    except RuntimeError as exc:  # optional dependency missing
        _echo_fail(str(exc))
        raise typer.Exit(code=1) from exc

    expected = source.count()
    if expected == 0:
        _echo_warn(f"the '{source_name}' store at {rag} is empty — nothing to migrate.")
        source.close()
        raise typer.Exit(code=0)

    try:
        target = vector_backend.get_backend(rag, name=target_name)
    except RuntimeError as exc:
        _echo_fail(str(exc))
        source.close()
        raise typer.Exit(code=1) from exc

    try:
        existing = target.count()
        if existing and not force:
            _echo_warn(
                f"the '{target_name}' store already has {existing} vector(s) — skipping "
                "(pass --force to overwrite)."
            )
            raise typer.Exit(code=0)
        if existing:
            target.clear()

        typer.echo(f"  migrating {expected} vector(s): {source_name} → {target_name}…")

        def _progress(done: int) -> None:
            typer.echo(f"\r    {done}/{expected} copied", nl=False)

        copied = vector_backend.migrate(source, target, on_progress=_progress)
        typer.echo("")
        final = target.count()
    finally:
        source.close()
        target.close()

    if final != expected:
        _echo_fail(
            f"count mismatch after migration: copied {copied}, target now holds "
            f"{final}, expected {expected}."
        )
        raise typer.Exit(code=1)

    _echo_ok(f"migrated {copied} vector(s): {source_name} → {target_name} (verified {final}).")
    typer.echo(f"  set VECTOR_BACKEND={target_name} in your .env to use the new store.")


def _migrate_legacy_json(rag: Path, *, force: bool) -> None:
    """Import a legacy ``vectors.json`` into the SQLite store (the original behaviour)."""
    from eidetic_os import vectordb

    legacy = rag / "vectors.json"
    if not legacy.exists():
        _echo_fail(f"No legacy store found at {legacy}")
        raise typer.Exit(code=1)

    entries = vectordb.VectorStore.read_from_json(legacy)
    if not entries:
        _echo_warn(f"{legacy} is empty or unreadable — nothing to migrate")
        raise typer.Exit(code=0)

    db_path = vectordb.default_db_path(rag)
    with vectordb.VectorStore(db_path) as store:
        existing = store.count()
        if existing and not force:
            _echo_warn(
                f"{db_path} already has {existing} vector(s) — skipping "
                "(pass --force to re-import)."
            )
            raise typer.Exit(code=0)
        if force:
            store.clear()
        added = store.add_vectors(entries)
        backend = "sqlite-vec" if store.vec_enabled else "brute-force cosine"

    _echo_ok(f"migrated {added} vector(s) → {db_path}")
    typer.echo(f"  backend: {backend}")
    typer.echo(f"  the legacy {legacy.name} is left in place; delete it once you've verified search.")


def _resolve_rag_dir() -> Path | None:
    """The RAG directory from $RAG_DIR, else $VAULT_PATH/.rag, else None."""
    rag_env = os.environ.get("RAG_DIR")
    if rag_env:
        return Path(os.path.expanduser(rag_env))
    vault_env = os.environ.get("VAULT_PATH")
    if vault_env:
        return Path(os.path.expanduser(vault_env)) / ".rag"
    return None


@app.command()
def graph(
    open_browser: bool = typer.Option(
        False, "--open",
        help="Build the graph, then open the interactive viewer in your browser.",
    ),
    host: str = typer.Option(
        "127.0.0.1", "--host", help="Interface to bind when serving the viewer (--open)."
    ),
    port: int = typer.Option(
        8501, "--port", "-p", help="Port to serve the viewer on (--open)."
    ),
    no_build: bool = typer.Option(
        False, "--no-build", help="With --open, skip rebuilding graph.json before serving."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit the build summary as JSON (ignored with --open)."
    ),
) -> None:
    """Rebuild the wikilink knowledge graph — or ``--open`` the interactive viewer.

    With no flags this rebuilds ``graph.json`` from your vault's ``[[wikilinks]]``
    and appends an audit entry (as before). With ``--open`` it (re)builds the
    graph and launches the local dashboard at ``/graph`` — a D3 force-directed map
    of how your notes connect: zoom, pan, click a node for its links, search and
    filter by type. Serving needs the dashboard extra (``eidetic-os[dashboard]``).
    """
    _require_env("VAULT_PATH")

    if open_browser:
        if not no_build:
            typer.echo("  Building knowledge graph…")
            rc = subprocess.call([sys.executable, str(scripts_dir() / "build_graph.py")])
            if rc != 0:
                # The viewer scans the vault live, so a stale/failed build is not
                # fatal — warn and serve what we can rather than bailing out.
                _echo_warn("graph build failed; serving the live vault scan instead.")
        _serve_dashboard(host, port, open_browser=True, open_path="/graph")
        return

    args = ["--json"] if json_output else []
    _run_audited("graph", scripts_dir() / "build_graph.py", args,
                 _context_for("graph", args))


@app.command(context_settings=_PASSTHROUGH)
def commit(ctx: typer.Context) -> None:
    """Auto-commit the vault with a categorised message (--dry-run | --json)."""
    _require_env("VAULT_PATH")
    _run_audited("commit", scripts_dir() / "vault_commit.py", ctx.args,
                 _context_for("commit", ctx.args))


@app.command(context_settings=_PASSTHROUGH)
def changelog(ctx: typer.Context) -> None:
    """Summarise vault changes over a window (--since | --markdown | --json)."""
    _require_env("VAULT_PATH")
    _run_audited("changelog", scripts_dir() / "vault_changelog.py", ctx.args,
                 _context_for("changelog", ctx.args))


@app.command()
def sync(
    remote: str = typer.Option("origin", "--remote", help="Remote to pull from."),
    branch: str = typer.Option(
        None, "--branch", help="Branch to sync (defaults to the current branch)."
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit the sync result as JSON."
    ),
) -> None:
    """Safely pull remote vault changes with a favour-local merge.

    Uses ``git merge -X ours`` so an automated or remote change never silently
    overwrites a concurrent human edit. A true conflict that cannot be
    auto-resolved aborts the merge — your working tree is left exactly as it was
    — and is reported for you to resolve. Stale git locks left by a crashed run
    are cleared first, and every outcome is written to the audit trail.
    """
    _require_env("VAULT_PATH")
    vault = _resolve_vault()
    assert vault is not None  # _require_env guarantees VAULT_PATH is set
    result = git_sync.safe_sync(vault, remote=remote, branch=branch)

    if as_json:
        typer.echo(json.dumps({
            "status": result.status,
            "message": result.message,
            "conflicts": list(result.conflicts),
            "locks_cleared": list(result.locks_cleared),
            "merged_commit": result.merged_commit,
        }, indent=2))
        raise typer.Exit(code=0 if result.ok else 1)

    if result.locks_cleared:
        _echo_warn(f"cleared stale git lock(s): {', '.join(result.locks_cleared)}")
    if result.status == "synced":
        _echo_ok(result.message)
    elif result.status == "up_to_date":
        _echo_ok(result.message)
    elif result.status == "conflict":
        _echo_fail(result.message)
        for path in result.conflicts:
            typer.echo(f"      conflict: {path}")
        typer.secho(
            "      → resolve by hand, then re-run `eidetic sync`.",
            fg=typer.colors.CYAN,
        )
    elif result.status == "skipped":
        _echo_warn(result.message)
    else:
        _echo_fail(result.message)
    raise typer.Exit(code=0 if result.ok or result.status == "skipped" else 1)


def _vault_markdown(vault: Path) -> list[Path]:
    """All Markdown notes in ``vault``, skipping dotted dirs (``.git``, ``.rag``…)."""
    out: list[Path] = []
    for path in sorted(vault.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(vault).parts):
            continue
        out.append(path)
    return out


@app.command()
def validate(
    staged: bool = typer.Option(
        False, "--staged",
        help="Only validate git-staged files (the pre-commit gate).",
    ),
    require: str = typer.Option(
        None, "--require",
        help="Comma-separated frontmatter keys that must be present.",
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit the validation report as JSON."
    ),
) -> None:
    """Validate YAML frontmatter across the vault (or just staged files).

    Flags broken YAML, unterminated frontmatter blocks, missing required keys,
    and malformed dates — the same checks that gate every automated commit. With
    ``--staged`` it validates only what is staged in git (use it as a pre-commit
    hook); otherwise it scans every note. Exits non-zero if any file is invalid.
    """
    _require_env("VAULT_PATH")
    vault = _resolve_vault()
    assert vault is not None  # _require_env guarantees VAULT_PATH is set
    required_keys = (
        tuple(k.strip() for k in require.split(",") if k.strip()) if require else ()
    )
    files = None if staged else _vault_markdown(vault)
    report = frontmatter.validate_before_commit(
        vault, files=files, required=required_keys
    )

    if as_json:
        typer.echo(json.dumps({
            "ok": report.ok,
            "checked": len(report.results),
            "failures": [
                {"file": str(r.file_path), "errors": list(r.errors)}
                for r in report.failures
            ],
        }, indent=2))
        raise typer.Exit(code=0 if report.ok else 1)

    if report.ok:
        _echo_ok(f"frontmatter valid in all {len(report.results)} file(s)")
        raise typer.Exit(code=0)
    for failure in report.failures:
        _echo_fail(str(failure.file_path))
        for err in failure.errors:
            typer.echo(f"      → {err}")
    _echo_fail(f"{len(report.failures)} file(s) with invalid frontmatter")
    raise typer.Exit(code=1)


@app.command()
def consolidate(
    daemon: bool = typer.Option(
        False, "--daemon", help="Run continuously, consolidating every --interval hours."
    ),
    status: bool = typer.Option(
        False, "--status", help="Show last run, pending sessions, and stats (no writes)."
    ),
    interval: float = typer.Option(
        6.0, "--interval", help="Hours between passes in --daemon mode."
    ),
    no_llm: bool = typer.Option(
        False, "--no-llm", help="Force heuristic extraction even if a backend is up."
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit a machine-readable summary."
    ),
) -> None:
    """Consolidate recent session logs into a single merged memory note.

    The sleeptime daemon scans ``$VAULT_PATH/sessions/`` for logs written since the
    last pass, distils each to its decisions/actions/topics/files, merges them
    (resolving contradictions in favour of the most recent), and writes
    ``wiki/consolidated/YYYY-MM-DD.md``. With no flags it runs a single pass;
    ``--daemon`` loops every ``--interval`` hours; ``--status`` just reports state.
    """
    from eidetic_os import sleeptime

    _require_env("VAULT_PATH")
    vault = _resolve_vault()
    assert vault is not None  # _require_env guarantees VAULT_PATH is set

    if status:
        info = sleeptime.consolidation_status(vault)
        if as_json:
            typer.echo(json.dumps(info, indent=2))
            raise typer.Exit(code=0)
        typer.secho("\nConsolidation status\n", bold=True)
        last = info["last_consolidation"] or "never"
        _echo_ok(f"vault: {info['vault_path']}")
        typer.echo(f"      last consolidation : {last}")
        typer.echo(f"      sessions pending   : {info['sessions_pending']}")
        typer.echo(f"      consolidated notes : {info['consolidated_notes']}")
        if info["latest_note"]:
            typer.echo(f"      latest note        : {info['latest_note']}")
        typer.echo(
            f"      facts integration  : "
            f"{'enabled' if info['facts_integration'] else 'unavailable'}"
        )
        raise typer.Exit(code=0)

    engine = sleeptime.ConsolidationDaemon(
        vault, interval_hours=interval, use_llm=not no_llm
    )

    if daemon:
        _echo_ok(f"sleeptime daemon started — consolidating every {interval:g}h")
        typer.echo("      press Ctrl-C to stop.")
        engine.start()
        try:
            while engine.is_running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            typer.echo("")
            _echo_warn("stopping daemon…")
            engine.stop()
            _echo_ok("daemon stopped")
        raise typer.Exit(code=0)

    note = engine.run_once()
    if as_json:
        payload = (
            {
                "consolidated": True,
                "date": note.date,
                "sessions_processed": note.sessions_processed,
                "decisions": len(note.decisions),
                "actions": len(note.actions),
                "topics": len(note.topics),
                "files_touched": len(note.files_touched),
                "contradictions": note.contradictions,
            }
            if note is not None
            else {"consolidated": False, "reason": "nothing new to consolidate"}
        )
        typer.echo(json.dumps(payload, indent=2))
        raise typer.Exit(code=0)

    if note is None:
        _echo_warn("nothing new to consolidate")
        raise typer.Exit(code=0)
    _echo_ok(
        f"consolidated {len(note.sessions_processed)} session(s) → "
        f"wiki/consolidated/{note.date}.md"
    )
    typer.echo(
        f"      {len(note.decisions)} decision(s), {len(note.actions)} action(s), "
        f"{len(note.contradictions)} contradiction(s) resolved"
    )
    raise typer.Exit(code=0)


@app.command(context_settings=_PASSTHROUGH)
def health(ctx: typer.Context) -> None:
    """Full subsystem health probe (--json | --quiet)."""
    _run_audited("health", scripts_dir() / "health_check.py", ctx.args,
                 _context_for("health", ctx.args))


@app.command()
def email(
    to: str = typer.Option(None, "--to", help="Recipient address (defaults to USER_EMAIL)."),
    subject: str = typer.Option(None, "--subject", "-s", help="Email subject line."),
    body: str = typer.Option(None, "--body", "-b", help="Email body (HTML or plain text)."),
    text: bool = typer.Option(
        False, "--text", help="Send --body as plain text instead of HTML."
    ),
    attach: list[str] = typer.Option(
        None, "--attach", "-a", help="File to attach (repeatable)."
    ),
    payload: str = typer.Option(
        None, "--json", help="Raw JSON payload (overrides the flags above)."
    ),
) -> None:
    """Send an email via SMTP, from --subject/--body flags or a raw --json payload."""
    _require_env("SENDER_EMAIL", "SMTP_APP_PASSWORD")
    if payload is None:
        recipient = to or os.environ.get("USER_EMAIL")
        if not recipient:
            _echo_fail("No recipient: pass --to, or set USER_EMAIL in .env.")
            raise typer.Exit(code=2)
        if not subject or not body:
            _echo_fail("Both --subject and --body are required (or use --json).")
            raise typer.Exit(code=2)
        data: dict[str, object] = {"to": recipient, "subject": subject}
        data["body_text" if text else "body_html"] = body
        if attach:
            data["attachments"] = list(attach)
        payload = json.dumps(data)
    _run_audited("email", scripts_dir() / "send_email.py", [payload],
                 _context_for("email", []))


@app.command(context_settings=_PASSTHROUGH)
def schemas(ctx: typer.Context) -> None:
    """Enforce per-folder frontmatter schemas (--dry-run | --folder | --verbose)."""
    _require_env("VAULT_PATH")
    _run(schemas_dir() / "enforce_schemas.py", ctx.args)


# ─────────────────────────────────────────────────────────────────────────────
# skills — the agent skills catalog
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_vault() -> Path | None:
    vault_env = os.environ.get("VAULT_PATH")
    if not vault_env:
        return None
    return Path(os.path.expanduser(vault_env))


def _write_catalog(vault: Path, output: Path | None) -> Path:
    """Generate the Skills Catalog note into the vault. Returns the path."""
    path = output or default_catalog_path(vault)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_catalog(load_skills()), encoding="utf-8")
    return path


skills_app = typer.Typer(
    invoke_without_command=True,
    help="List, show, and install the agent skills shipped with Eidetic OS.",
)
app.add_typer(skills_app, name="skills")


def _print_skill_list(items: list[_skills.Skill]) -> None:
    """Render the skills catalog to the terminal (slug · cadence · description)."""
    typer.secho(f"\nAgent skills ({len(items)} skill(s)):\n", bold=True)
    for s in items:
        typer.secho(f"  {s.slug}", fg=typer.colors.CYAN, nl=False)
        typer.echo(f"  [{s.cadence}]")
        typer.echo(f"    {s.description}")


@skills_app.callback()
def skills_main(
    ctx: typer.Context,
    sync: bool = typer.Option(
        False, "--sync", help="Write/refresh the catalog note in the vault."
    ),
    output: Path = typer.Option(
        None, "--output", help="Override the catalog note path (with --sync)."
    ),
) -> None:
    """List the agent skills catalog; ``--sync`` writes it into the vault.

    Run with no subcommand to list every skill. See ``list``, ``show``, and
    ``install`` for the per-skill operations.
    """
    if ctx.invoked_subcommand is not None:
        return

    items = load_skills()
    if not items:
        _echo_warn("no skills found")
        raise typer.Exit()

    _print_skill_list(items)

    if sync:
        vault = _resolve_vault()
        if vault is None or not vault.is_dir():
            _echo_fail("VAULT_PATH is not set or does not exist — run `eidetic init`")
            raise typer.Exit(code=1)
        path = _write_catalog(vault, output)
        _echo_ok(f"wrote catalog → {path}")
    else:
        typer.echo(
            "\nRun `eidetic skills install <name>` to install one, "
            "or `eidetic skills --sync` to write the catalog into your vault."
        )


@skills_app.command("list")
def skills_list() -> None:
    """List every available skill from the skills/ directory."""
    items = load_skills()
    if not items:
        _echo_warn("no skills found")
        raise typer.Exit()
    _print_skill_list(items)
    typer.echo("\nRun `eidetic skills install <name>` to install one.")


@skills_app.command("show")
def skills_show(name: str = typer.Argument(..., help="Skill slug to display.")) -> None:
    """Print a skill's SKILL.md content to stdout."""
    skill = _skills.find_skill(name)
    if skill is None:
        _echo_fail(f"unknown skill {name!r} — run `eidetic skills list`")
        raise typer.Exit(code=2)
    source = _skills.skill_source(skill.slug)
    if not source.is_file():
        _echo_fail(f"SKILL.md not found for {skill.slug!r}")
        raise typer.Exit(code=2)
    typer.echo(source.read_text(encoding="utf-8"))


@skills_app.command("install")
def skills_install(
    name: str = typer.Argument(..., help="Skill slug to install."),
    force: bool = typer.Option(
        False, "--force", help="Overwrite an already-installed skill."
    ),
) -> None:
    """Install a skill into your scheduled-tasks dir, filling in placeholders.

    The skill's SKILL.md is copied to ``$EIDETIC_SKILLS_DIR/<name>/`` (or
    ``$VAULT_PATH/.claude/skills/<name>/`` by default) with its
    ``{{PLACEHOLDER}}`` tokens substituted from your environment / .env.

    Before installing, the skill's source is scanned for dangerous code. A
    ``BLOCK`` finding refuses the install outright; ``WARN`` findings require
    ``--force``. Every attempt is recorded in the audit trail.
    """
    trigger = os.environ.get("EIDETIC_TRIGGER", "cli")
    try:
        result = _skills.install_skill(name, force=force)
    except _skills.SkillNotFoundError:
        _echo_fail(f"unknown skill {name!r} — run `eidetic skills list`")
        raise typer.Exit(code=2) from None
    except _skills.SkillBlockedError as exc:
        _print_security_report(exc.report, name)
        audit.log_action(
            "skill_install", trigger, "error",
            changes=[f"{len(exc.report.blocks)} blocking finding(s)"],
            context=name, error="blocked by security scan",
        )
        _echo_fail(
            f"refused to install {name!r} — {len(exc.report.blocks)} blocking "
            "security finding(s). This skill is not installable."
        )
        raise typer.Exit(code=1) from exc
    except _skills.SkillWarningError as exc:
        _print_security_report(exc.report, name)
        audit.log_action(
            "skill_install", trigger, "skipped",
            changes=[f"{len(exc.report.warnings)} warning(s)"],
            context=name, error="security warnings; --force required",
        )
        _echo_warn(
            f"{len(exc.report.warnings)} security warning(s) — re-run with "
            "--force to install anyway."
        )
        raise typer.Exit(code=1) from exc
    except _skills.SkillInstallError as exc:
        _echo_fail(str(exc))
        audit.log_action(
            "skill_install", trigger, "error", context=name, error=str(exc)
        )
        raise typer.Exit(code=1) from exc

    accepted = len(result.report.warnings) if result.report else 0
    audit.log_action(
        "skill_install", trigger, "success",
        changes=[f"installed {result.slug}"]
        + ([f"{accepted} accepted warning(s)"] if accepted else []),
        context=str(result.dest),
    )

    verb = "reinstalled" if result.overwrote else "installed"
    _echo_ok(f"{verb} {result.slug} → {result.dest}")
    if accepted:
        _echo_warn(f"installed with {accepted} accepted security warning(s) (--force)")
    if result.resolved:
        filled = ", ".join(sorted(result.resolved))
        typer.echo(f"  filled {len(result.resolved)} placeholder(s): {filled}")
    if result.unresolved:
        left = ", ".join(result.unresolved)
        _echo_warn(
            f"{len(result.unresolved)} placeholder(s) left to fill by hand: {left}"
        )
        typer.echo(f"  edit them in {result.dest}")

    # MCP-server skills carry an ``mcp_server`` transport block; surface it so the
    # user knows the skill is driven over MCP rather than run as a plain prompt.
    from eidetic_os.mcp_skill import mcp_server_config

    config = mcp_server_config(result.slug)
    if config is not None:
        transport = config.get("transport", "stdio")
        _echo_ok(f"MCP skill detected — transport: {transport}")
        if transport == "stdio":
            typer.echo(f"  command: {' '.join(str(c) for c in config.get('command', []))}")
        else:
            typer.echo(f"  url: {config.get('url', '')}")
        typer.echo(f"  run it with `eidetic skills run {result.slug}` or any MCP host")


@skills_app.command("packs")
def skills_packs() -> None:
    """List the pre-built skill packs (curated bundles for common workflows)."""
    items = packs.load_packs()
    if not items:
        _echo_warn("no packs defined")
        raise typer.Exit()
    typer.secho(f"\nSkill packs ({len(items)} pack(s)):\n", bold=True)
    for pack in items:
        typer.secho(f"  {pack.name}", fg=typer.colors.CYAN, nl=False)
        typer.echo(f"  ({len(pack.skills)} skill(s))")
        typer.echo(f"    {pack.description}")
        typer.echo(f"    skills: {', '.join(pack.skills)}")
    typer.echo("\nRun `eidetic skills install-pack <name>` to install a pack.")


@skills_app.command("install-pack")
def skills_install_pack(
    name: str = typer.Argument(..., help="Pack name to install."),
    force: bool = typer.Option(
        False, "--force", help="Overwrite already-installed skills in the pack."
    ),
) -> None:
    """Install every skill in a pack at once, filling in placeholders.

    Each skill is installed exactly as ``eidetic skills install`` would — copied
    to ``$EIDETIC_SKILLS_DIR/<slug>/`` (or ``$VAULT_PATH/.claude/skills/<slug>/``)
    with its ``{{PLACEHOLDER}}`` tokens substituted from your environment / .env.
    A skill that's already installed is skipped unless you pass ``--force``.
    """
    try:
        result = packs.install_pack(name, force=force)
    except packs.PackNotFoundError:
        _echo_fail(f"unknown pack {name!r} — run `eidetic skills packs`")
        raise typer.Exit(code=2) from None
    except _skills.SkillInstallError as exc:
        _echo_fail(str(exc))
        raise typer.Exit(code=1) from exc

    typer.secho(
        f"\nPack {result.pack!r}: {len(result.installed)} installed, "
        f"{len(result.skipped)} skipped.\n",
        bold=True,
    )
    unresolved: set[str] = set()
    for installed in result.installed:
        verb = "reinstalled" if installed.overwrote else "installed"
        _echo_ok(f"{verb} {installed.slug} → {installed.dest}")
        unresolved.update(installed.unresolved)
    for slug, reason in result.skipped:
        _echo_warn(f"skipped {slug} — {reason}")

    if unresolved:
        left = ", ".join(sorted(unresolved))
        _echo_warn(
            f"{len(unresolved)} placeholder(s) left to fill by hand across the pack: {left}"
        )
        typer.echo("  edit each skill's SKILL.md to fill them in")


# ─────────────────────────────────────────────────────────────────────────────
# skills marketplace — search, publish, registries
# ─────────────────────────────────────────────────────────────────────────────
@skills_app.command("search")
def skills_search(
    query: str = typer.Argument("", help="Keyword or tag to match (empty = list all)."),
) -> None:
    """Search the configured registries for community skills by keyword or tag.

    Matches the skill name, description, and tags across every registry you've
    added (the built-in registry is always searched). See ``registry add``.
    """
    try:
        hits, loads = marketplace.search_registries(query)
    except marketplace.RegistryError as exc:
        _echo_fail(str(exc))
        raise typer.Exit(code=1) from exc

    for load in loads:
        if load.error is not None:
            _echo_warn(f"registry {load.source!r} unavailable — {load.error}")

    if not hits:
        _echo_warn(f"no skills match {query!r}" if query else "no skills found")
        raise typer.Exit()

    typer.secho(f"\nFound {len(hits)} skill(s):\n", bold=True)
    for hit in hits:
        entry = hit.entry
        typer.secho(f"  {entry.name}", fg=typer.colors.CYAN, nl=False)
        typer.echo(f"  v{entry.version}  ·  {entry.author}  ·  [{hit.registry_name}]")
        typer.echo(f"    {entry.description}")
        if entry.tags:
            typer.echo(f"    tags: {', '.join(entry.tags)}")
        if entry.dependencies:
            typer.echo(f"    depends on: {', '.join(entry.dependencies)}")
    typer.echo("\nRun `eidetic skills install <name>` to install a built-in skill.")


@skills_app.command("publish")
def skills_publish(
    path: Path = typer.Argument(..., help="Path to the skill folder to package."),
    output: Path = typer.Option(
        Path("dist/skills"),
        "--output",
        "-o",
        help="Directory to write the .tar.gz package into.",
    ),
) -> None:
    """Validate a skill folder and package it into a shareable ``.tar.gz``.

    The skill's ``SKILL.md`` is checked against the schema (required fields,
    valid name/version, well-formed tags & dependencies); on success a
    ``<name>-<version>.tar.gz`` containing a generated ``manifest.json`` plus the
    skill's files is written, ready to attach to a registry's download URL.
    """
    try:
        result = marketplace.package_skill(path, output)
    except marketplace.SkillValidationError as exc:
        _echo_fail(f"validation failed for {exc.target}:")
        for problem in exc.problems:
            typer.echo(f"  • {problem}")
        raise typer.Exit(code=1) from exc

    manifest = result.manifest
    _echo_ok(f"packaged {manifest.name} v{manifest.version} → {result.archive}")
    typer.echo(f"  {len(result.files)} file(s): {', '.join(result.files)}")
    if manifest.dependencies:
        typer.echo(f"  declares dependencies: {', '.join(manifest.dependencies)}")


registry_app = typer.Typer(
    no_args_is_help=True,
    help="Manage the skill registries that `eidetic skills search` queries.",
)
skills_app.add_typer(registry_app, name="registry")


@registry_app.command("add")
def registry_add(
    url: str = typer.Argument(..., help="Registry URL or local registry.json path."),
) -> None:
    """Add a custom registry (URL or local path) to search alongside the built-in one."""
    try:
        sources = marketplace.add_registry(url)
    except marketplace.RegistryError as exc:
        _echo_fail(str(exc))
        raise typer.Exit(code=1) from exc
    _echo_ok(f"added registry {url!r}")
    typer.echo(f"  {len(sources)} registr(y/ies) configured (built-in always included)")


@registry_app.command("list")
def registry_list() -> None:
    """Show the configured registries and how many skills each currently lists."""
    loads = marketplace.load_all_registries()
    typer.secho(f"\nConfigured registries ({len(loads)}):\n", bold=True)
    for load in loads:
        label = "built-in" if load.source == marketplace.DEFAULT_REGISTRY else load.source
        typer.secho(f"  {label}", fg=typer.colors.CYAN)
        if load.registry is not None:
            typer.echo(
                f"    {load.registry.name} — {len(load.registry.entries)} skill(s)"
            )
        else:
            _echo_warn(f"    unavailable — {load.error}")


# ─────────────────────────────────────────────────────────────────────────────
# skills run — serve a skill as an MCP server
# ─────────────────────────────────────────────────────────────────────────────
@skills_app.command("run")
def skills_run(
    name: str = typer.Argument(..., help="Skill slug to serve as an MCP server."),
) -> None:
    """Run a skill as an MCP server over stdio (launches, serves, exits on EOF).

    The skill's ``SKILL.md`` is exposed as an MCP tool: an MCP host calls the
    tool and receives the skill's rendered instructions. This makes any bundled
    skill usable from Claude Code, Cowork, or any other MCP client. Blocks,
    reading JSON-RPC from stdin and writing to stdout, until the stream closes.
    """
    from eidetic_os.mcp_skill import serve_skill

    if _skills.find_skill(name) is None:
        _echo_fail(f"unknown skill {name!r} — run `eidetic skills list`")
        raise typer.Exit(code=2)
    serve_skill(name)


# ─────────────────────────────────────────────────────────────────────────────
# mcp — Eidetic OS as a Model Context Protocol server
# ─────────────────────────────────────────────────────────────────────────────
mcp_app = typer.Typer(
    no_args_is_help=True,
    help="Run Eidetic OS as an MCP server, or inspect its MCP tools.",
)
app.add_typer(mcp_app, name="mcp")


@mcp_app.command("serve")
def mcp_serve() -> None:
    """Start Eidetic OS as an MCP server over stdio.

    Exposes Eidetic capabilities as MCP tools (search, embed, doctor, skills_list,
    audit_query) so any MCP host can drive Eidetic OS directly. Blocks, speaking
    JSON-RPC over stdin/stdout, until the input stream closes. Point a host at
    it with the command ``eidetic mcp serve``.
    """
    from eidetic_os.mcp_server import serve_stdio

    serve_stdio()


@mcp_app.command("list-tools")
def mcp_list_tools(
    as_json: bool = typer.Option(False, "--json", help="Emit the tool list as JSON."),
) -> None:
    """Show the MCP tools the Eidetic OS server exposes (name, description, schema)."""
    from eidetic_os.mcp_server import build_eidetic_server

    tools = build_eidetic_server().tools
    if as_json:
        typer.echo(json.dumps([t.definition() for t in tools], indent=2))
        return

    typer.secho(f"\nEidetic OS MCP tools ({len(tools)}):\n", bold=True)
    for tool in tools:
        typer.secho(f"  {tool.name}", fg=typer.colors.CYAN)
        typer.echo(f"    {tool.description}")
        required = tool.input_schema.get("required") or []
        props = tool.input_schema.get("properties") or {}
        if props:
            shown = ", ".join(
                f"{k}{'*' if k in required else ''}" for k in props
            )
            typer.echo(f"    args: {shown}   (* = required)")
    typer.echo("\nStart the server with `eidetic mcp serve` and point any MCP host at it.")


# ─────────────────────────────────────────────────────────────────────────────
# init
# ─────────────────────────────────────────────────────────────────────────────
def _render_env(values: dict[str, str]) -> str:
    """Produce a commented .env from collected values.

    Only the values onboarding collects are written explicitly; everything else
    is documented in docs/CONFIGURATION.md.
    """
    g = values.get
    return f"""\
# Eidetic OS configuration — generated by `eidetic init`.
# Full reference: docs/CONFIGURATION.md . NEVER commit real secrets.

# ── Vault ─────────────────────────────────────────────────────────────────
VAULT_PATH={g("VAULT_PATH", "~/Documents/Obsidian/MyVault")}

# ── Local LLM: embeddings (OpenAI-compatible) ──────────────────────────────
EMBED_HOST={g("EMBED_HOST", "localhost")}
EMBED_PORT={g("EMBED_PORT", "5555")}
EMBED_MODEL={g("EMBED_MODEL", "text-embedding-nomic-embed-text-v1.5")}

# ── Local LLM: chat completions (trading module) ───────────────────────────
LM_STUDIO_HOST={g("LM_STUDIO_HOST", "localhost")}
LM_STUDIO_PORT={g("LM_STUDIO_PORT", "5555")}
LM_STUDIO_MODEL={g("LM_STUDIO_MODEL", "local-model")}

# ── Email (SMTP) — required only to send reports ───────────────────────────
SENDER_EMAIL={g("SENDER_EMAIL", "")}
SENDER_NAME={g("SENDER_NAME", "Eidetic")}
SMTP_SERVER={g("SMTP_SERVER", "smtp.gmail.com")}
SMTP_PORT={g("SMTP_PORT", "587")}
SMTP_APP_PASSWORD={g("SMTP_APP_PASSWORD", "")}
USER_EMAIL={g("USER_EMAIL", "")}
"""


# Directories every Eidetic OS vault needs, created up front by the wizard so the
# RAG store, audit trail, and wiki all have a home before anything writes to them.
_VAULT_DIRS: tuple[str, ...] = (".eidetic", ".rag", "wiki")


def _detect_default_vault() -> str:
    """Best guess at where the user's vault lives, for the wizard's default.

    Resolution order:

    1. ``VAULT_PATH`` from the environment / an existing ``.env`` (explicit wins).
    2. The first sub-folder of ``~/Documents/Obsidian`` (the standard Obsidian
       home — most people have exactly one vault there).
    3. ``~/vault`` if it exists.
    4. The current directory, if it already looks like a vault (contains
       markdown files) and isn't the Eidetic OS source checkout.
    5. A sensible placeholder under the Obsidian directory.
    """
    env = os.environ.get("VAULT_PATH")
    if env:
        return os.path.expanduser(env)

    home = Path.home()
    obsidian = home / "Documents" / "Obsidian"
    if obsidian.is_dir():
        subdirs = sorted(
            p for p in obsidian.iterdir() if p.is_dir() and not p.name.startswith(".")
        )
        if subdirs:
            return str(subdirs[0])

    vault = home / "vault"
    if vault.is_dir():
        return str(vault)

    cwd = Path.cwd()
    if cwd != repo_root() and any(cwd.glob("*.md")):
        return str(cwd)

    return str(obsidian / "MyVault")


def _backend_env_from_endpoint(endpoint: Endpoint) -> dict[str, str]:
    """Map a detected :class:`_probe.Endpoint` to the .env keys it configures."""
    values: dict[str, str] = {
        "EMBED_HOST": endpoint.host,
        "EMBED_PORT": str(endpoint.port),
        "LM_STUDIO_HOST": endpoint.host,
        "LM_STUDIO_PORT": str(endpoint.port),
    }
    embed_models = [m for m in endpoint.models if "embed" in m.lower()]
    if embed_models:
        values["EMBED_MODEL"] = embed_models[0]
    return values


def _scaffold_vault(vault: Path) -> None:
    """Create the vault directory tree and copy the skeleton (stripping .template)."""
    for name in _VAULT_DIRS:
        directory = vault / name
        created = not directory.exists()
        directory.mkdir(parents=True, exist_ok=True)
        if created:
            _echo_ok(f"created {name}/")
    skel = templates_dir() / "vault-skeleton"
    for src in skel.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(skel)
        dest = vault / str(rel).removesuffix(".template")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            _echo_warn(f"exists, skipped: {dest.relative_to(vault)}")
            continue
        shutil.copyfile(src, dest)
        _echo_ok(f"created {dest.relative_to(vault)}")


def _git_init(vault: Path) -> None:
    if (vault / ".git").is_dir():
        _echo_ok("vault is already a git repo")
        return
    try:
        subprocess.run(["git", "init", "-q"], cwd=vault, check=True)
        subprocess.run(["git", "add", "-A"], cwd=vault, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "Initialise vault"], cwd=vault, check=True
        )
        _echo_ok("initialised vault git repo")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        _echo_warn(f"could not init git in vault ({exc}); do it manually")


def _print_welcome() -> None:
    """Friendly banner explaining what `eidetic init` is about to do."""
    from eidetic_os import setup_wizard

    setup_wizard.make_ui().banner(__version__)
    typer.secho("\n  ⛰  Eidetic OS — setup wizard\n", fg=typer.colors.CYAN, bold=True)
    typer.echo(
        "  Eidetic OS is your local-first personal AI operating system: a"
        " searchable\n  markdown vault with git history, RAG semantic search over"
        " your notes,\n  and a library of automated agent skills — all running"
        " on your machine.\n"
    )
    typer.echo("  This wizard will:")
    typer.echo("    • find your vault and any local LLM you're running")
    typer.echo("    • write a .env you can tweak later")
    typer.echo("    • scaffold the vault structure (.eidetic/, .rag/, wiki/)")
    typer.echo("    • run `eidetic doctor` to confirm everything works\n")


def _prompt_vault_path(vault: Path | None, yes: bool) -> Path:
    """Resolve the vault path from the flag, a prompt, or the smart default."""
    default_vault = _detect_default_vault()
    if vault is not None:
        return vault.expanduser().resolve()
    if yes:
        return Path(default_vault).expanduser().resolve()
    return (
        Path(typer.prompt("  Vault path", default=default_vault))
        .expanduser()
        .resolve()
    )


def _detect_backend(values: dict[str, str]) -> Endpoint | None:
    """Probe for a local LLM and fold any match's host/port/model into ``values``.

    Returns the chosen :class:`Endpoint` (the first that responded), or ``None``
    if nothing was found — the wizard uses it for embedding-model selection.
    """
    typer.echo("\n  Probing for a local LLM endpoint…")
    typer.secho(
        "    (LM Studio :5555 · Ollama :11434 · llama.cpp :8080)",
        fg=typer.colors.BRIGHT_BLACK,
    )
    endpoints = detect_endpoints()
    if not endpoints:
        _echo_warn("no local LLM found — RAG/trading stay off until you set one up")
        return None
    for ep in endpoints:
        models = ", ".join(ep.models[:3]) or "no models reported"
        _echo_ok(f"{ep.label} at {ep.base_url} ({models})")
    chosen = endpoints[0]
    values.update(_backend_env_from_endpoint(chosen))
    _echo_ok(f"using {chosen.base_url} for embeddings + chat")
    return chosen


def _prompt_email(values: dict[str, str], yes: bool) -> None:
    """Optionally collect SMTP settings for email reports (interactive only)."""
    if yes or not typer.confirm("\n  Configure email reports now?", default=False):
        return
    values["SENDER_EMAIL"] = typer.prompt("  Sender email")
    values["SMTP_SERVER"] = typer.prompt("  SMTP server", default="smtp.gmail.com")
    values["SMTP_PORT"] = typer.prompt("  SMTP port", default="587")
    values["SMTP_APP_PASSWORD"] = typer.prompt(
        "  SMTP app password", hide_input=True, default=""
    )
    values["USER_EMAIL"] = typer.prompt(
        "  Send reports to", default=values.get("SENDER_EMAIL", "")
    )


@app.command()
def init(
    vault: Path | None = typer.Option(
        None, "--vault", help="Vault path (skips the prompt)."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Non-interactive: accept all defaults."
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite an existing .env."
    ),
) -> None:
    """Interactive onboarding: detect your LLM, write .env, scaffold the vault.

    Walks a fresh machine from nothing to a working setup — finds your vault and
    local LLM, generates a ``.env``, builds the vault directory tree, and runs
    ``eidetic doctor`` to confirm it all works. ``--yes`` accepts every default for
    a fully non-interactive run.
    """
    from eidetic_os import setup_wizard

    _print_welcome()

    # 1. Vault path
    vault_path = _prompt_vault_path(vault, yes)
    values: dict[str, str] = {"VAULT_PATH": str(vault_path)}

    # 2. Detect a local LLM backend
    endpoint = _detect_backend(values)

    # 3. Embedding-model selection (interactive only; auto-picks otherwise)
    wizard_ui = setup_wizard.make_ui()
    embed_model: str | None = None
    if endpoint is not None:
        embed_model = setup_wizard.select_embedding_model(
            wizard_ui, endpoint, interactive=not yes
        )
        if embed_model:
            values["EMBED_MODEL"] = embed_model

    # 4. Profile (optional, interactive only)
    profile = setup_wizard.collect_profile(wizard_ui, interactive=not yes)

    # 5. Email (optional, interactive only)
    _prompt_email(values, yes)

    # 6. Write .env
    env_dir = repo_root() or Path.cwd()
    env_path = env_dir / ".env"
    if env_path.exists() and not force:
        _echo_warn(f".env already exists at {env_path} — not overwriting (use --force)")
    else:
        env_path.write_text(_render_env(values), encoding="utf-8")
        _echo_ok(f"wrote {env_path}")
    # Reflect the collected config in this process so the doctor run below (and
    # any same-session command) sees it without re-reading the freshly written file.
    os.environ.update(values)

    # 7. Scaffold the vault
    typer.echo("\n  Scaffolding the vault…")
    _scaffold_vault(vault_path)
    try:
        catalog = _write_catalog(vault_path, None)
        _echo_ok(f"generated {catalog.relative_to(vault_path)}")
    except (FileNotFoundError, OSError) as exc:
        _echo_warn(f"could not generate the skills catalog ({exc})")
    _git_init(vault_path)

    # 8. Write .eidetic/config.yaml (detected backend + profile + memory defaults)
    try:
        document = setup_wizard.build_config(
            vault_path=vault_path,
            endpoint=endpoint,
            embed_model=embed_model or values.get("EMBED_MODEL"),
            profile=profile,
        )
        cfg_path = setup_wizard.write_config(
            document, vault_path / ".eidetic" / "config.yaml"
        )
        _echo_ok(f"wrote {cfg_path.relative_to(vault_path)}")
    except OSError as exc:
        _echo_warn(f"could not write config.yaml ({exc})")

    # 9. CLAUDE.md (opt-in, interactive only)
    home_claude = Path.home() / "CLAUDE.md"
    if not yes and not home_claude.exists() and typer.confirm(
        f"\n  Install the CLAUDE.md template to {home_claude}?", default=False
    ):
        shutil.copyfile(templates_dir() / "CLAUDE.md.template", home_claude)
        _echo_ok(f"wrote {home_claude} (edit the placeholders)")

    # 10. Verify the setup with the doctor
    typer.secho("\n  Verifying your setup…", bold=True)
    results = _doctor_results()
    _render_doctor(results)
    fails = sum(1 for c in results if c.status == "FAIL")

    # 11. You're ready
    if fails:
        typer.secho(
            "\n  ⚠  Setup finished with issues — fix the FAILs above, "
            "then re-run `eidetic doctor`.\n",
            fg=typer.colors.YELLOW,
            bold=True,
        )
    else:
        typer.secho("\n  ✓ You're ready!\n", fg=typer.colors.GREEN, bold=True)
    typer.echo("  Next steps:")
    typer.echo("    1. Review your .env             (docs/CONFIGURATION.md)")
    typer.echo("    2. eidetic embed --full           # build the RAG index (needs an LLM)")
    typer.echo("    3. eidetic skills list            # browse the agent skills")
    typer.echo("    4. eidetic health                 # full subsystem report\n")


# ─────────────────────────────────────────────────────────────────────────────
# audit — the append-only action trail
# ─────────────────────────────────────────────────────────────────────────────
audit_app = typer.Typer(
    no_args_is_help=True,
    help="Inspect the append-only audit trail of autonomous actions.",
)
app.add_typer(audit_app, name="audit")

_STATUS_COLOR = {
    "success": typer.colors.GREEN,
    "error": typer.colors.RED,
    "skipped": typer.colors.YELLOW,
}

_AUDIT_FIELDS: tuple[str, ...] = (
    "timestamp", "action", "trigger", "status",
    "duration_seconds", "changes", "context", "error",
)


def _fmt_entry(entry: dict[str, object]) -> str:
    """One-line coloured rendering of an audit entry for `audit show`."""
    status = str(entry.get("status", ""))
    colour = _STATUS_COLOR.get(status, typer.colors.WHITE)
    badge = typer.style(f"{status:<7}", fg=colour, bold=True)
    ts = str(entry.get("timestamp", ""))[:19]
    action = str(entry.get("action", "?"))
    trigger = str(entry.get("trigger", "?"))
    dur = entry.get("duration_seconds")
    dur_str = f"{dur:.2f}s" if isinstance(dur, (int, float)) else "—"
    changes = entry.get("changes") or []
    detail = ", ".join(str(c) for c in changes) if isinstance(changes, list) else ""
    line = f"{ts}  {badge} {action:<10} [{trigger}] {dur_str:>7}"
    if detail:
        line += f"  · {detail}"
    return line


@audit_app.command("show")
def audit_show(
    limit: int = typer.Option(20, "--limit", "-n", help="Max entries to show."),
    action: str = typer.Option(None, "--action", help="Filter by action name."),
    since: str = typer.Option(
        None, "--since", help="Only entries since e.g. 24h, 7d, or 2026-06-01."
    ),
) -> None:
    """Show recent audit entries (newest last), with optional filters."""
    try:
        entries = audit.read_audit(since=since, action=action, limit=limit)
    except ValueError as exc:
        _echo_fail(f"bad --since value: {exc}")
        raise typer.Exit(code=2) from exc

    if not entries:
        typer.echo("No audit entries match.")
        return

    typer.secho(f"\nAudit trail — {len(entries)} entr(y/ies):\n", bold=True)
    for entry in entries:
        typer.echo(_fmt_entry(entry))
        if entry.get("status") == "error" and entry.get("error"):
            first = str(entry["error"]).splitlines()[0]
            typer.secho(f"           ↳ {first}", fg=typer.colors.RED)


@audit_app.command("tail")
def audit_tail() -> None:
    """Show the last 5 entries in a compact format."""
    entries = audit.read_audit(limit=5)
    if not entries:
        typer.echo("No audit entries yet.")
        return
    for entry in entries:
        ts = str(entry.get("timestamp", ""))[:19]
        status = str(entry.get("status", ""))
        colour = _STATUS_COLOR.get(status, typer.colors.WHITE)
        mark = typer.style("●", fg=colour)
        typer.echo(f"{mark} {ts}  {entry.get('action', '?')}  {status}")


@audit_app.command("export")
def audit_export(
    fmt: str = typer.Option("csv", "--format", "-f", help="Export format: csv or json."),
    output: Path = typer.Option(None, "--output", "-o", help="Write to a file instead of stdout."),
    action: str = typer.Option(None, "--action", help="Filter by action name."),
    since: str = typer.Option(None, "--since", help="Only entries since e.g. 30d."),
) -> None:
    """Export the audit log for compliance reporting (CSV or JSON)."""
    fmt = fmt.lower()
    if fmt not in ("csv", "json"):
        _echo_fail("--format must be 'csv' or 'json'")
        raise typer.Exit(code=2)

    try:
        entries = audit.read_audit(since=since, action=action, limit=-1)
    except ValueError as exc:
        _echo_fail(f"bad --since value: {exc}")
        raise typer.Exit(code=2) from exc

    if fmt == "json":
        text = json.dumps(entries, ensure_ascii=False, indent=2)
    else:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(_AUDIT_FIELDS))
        writer.writeheader()
        for entry in entries:
            row: dict[str, str] = {}
            for key in _AUDIT_FIELDS:
                value = entry.get(key)
                if isinstance(value, list):
                    row[key] = "; ".join(str(item) for item in value)  # type: ignore[reportUnknownVariableType]
                elif value is None:
                    row[key] = ""
                else:
                    row[key] = str(value)
            writer.writerow(row)
        text = buffer.getvalue()

    if output is not None:
        output.write_text(text, encoding="utf-8")
        _echo_ok(f"exported {len(entries)} entr(y/ies) → {output}")
    else:
        typer.echo(text)


# ─────────────────────────────────────────────────────────────────────────────
# security — scan skills for dangerous code and review the install audit
# ─────────────────────────────────────────────────────────────────────────────
security_app = typer.Typer(
    no_args_is_help=True,
    help="Scan community skills for dangerous code and review the security audit.",
)
app.add_typer(security_app, name="security")


@security_app.command("scan")
def security_scan(
    path: Path = typer.Argument(
        ..., help="Skill directory or .py file to scan."
    ),
) -> None:
    """Statically scan a skill for dangerous code patterns (AST analysis).

    Parses every ``.py`` file under ``path`` and reports findings by severity.
    Exits non-zero if any ``BLOCK``-level finding is present, so it doubles as a
    CI gate for a skill repository.
    """
    if not path.exists():
        _echo_fail(f"no such path: {path}")
        raise typer.Exit(code=2)

    report = security.scan_skill(path)
    _print_security_report(report, str(path))

    if not security.is_safe(report):
        typer.echo()
        _echo_fail("BLOCK-level findings present — this skill is not safe to install")
        raise typer.Exit(code=1)


@security_app.command("report")
def security_report(
    since: str = typer.Option(
        None, "--since", help="Only attempts since e.g. 24h, 7d, or 2026-06-01."
    ),
    limit: int = typer.Option(
        10, "--limit", "-n", help="How many recent attempts to list."
    ),
) -> None:
    """Summarise the skill-install security audit: allowed, blocked, flagged.

    Reads the ``skill_install`` entries from the audit trail and shows how many
    installs succeeded, were blocked by a BLOCK finding, or were skipped pending
    ``--force``, plus the most recent attempts.
    """
    try:
        entries = audit.read_audit(action="skill_install", since=since, limit=-1)
    except ValueError as exc:
        _echo_fail(f"bad --since value: {exc}")
        raise typer.Exit(code=2) from exc

    if not entries:
        typer.echo("No skill-install attempts recorded yet.")
        return

    installed = sum(1 for e in entries if e.get("status") == "success")
    blocked = sum(
        1
        for e in entries
        if e.get("status") == "error" and e.get("error") == "blocked by security scan"
    )
    flagged = sum(1 for e in entries if e.get("status") == "skipped")
    errored = sum(1 for e in entries if e.get("status") == "error") - blocked

    typer.secho("\nSkill-install security report\n", bold=True)
    _echo_ok(f"installed:  {installed}")
    _echo_fail(f"blocked:    {blocked}  (BLOCK-level findings)")
    _echo_warn(f"flagged:    {flagged}  (WARN-level; needed --force)")
    if errored:
        _echo_fail(f"other errs: {errored}")
    typer.echo(f"  total attempts: {len(entries)}")

    recent = entries[-limit:]
    typer.secho(f"\nMost recent {len(recent)} attempt(s):\n", bold=True)
    for entry in recent:
        status = str(entry.get("status", ""))
        colour = _STATUS_COLOR.get(status, typer.colors.WHITE)
        mark = typer.style(f"{status:<7}", fg=colour, bold=True)
        ts = str(entry.get("timestamp", ""))[:19]
        context = str(entry.get("context", ""))
        typer.echo(f"  {ts}  {mark} {context}")


# ─────────────────────────────────────────────────────────────────────────────
# session — capture Cowork chat transcripts to the vault
# ─────────────────────────────────────────────────────────────────────────────
session_app = typer.Typer(
    no_args_is_help=True,
    help="Capture Cowork chat transcripts to the vault as session-log notes.",
)
app.add_typer(session_app, name="session")


@session_app.command("save")
def session_save(
    since: str = typer.Option(
        None, "--since", help="Capture sessions active since e.g. 24h, 7d, 2026-06-01."
    ),
    capture_all: bool = typer.Option(
        False, "--all", help="Capture every session ever (ignores the watermark)."
    ),
    sessions_dir_opt: str = typer.Option(
        None, "--sessions-dir", help="Override the Cowork session store path."
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit a machine-readable summary."
    ),
) -> None:
    """Save new/changed Cowork sessions to ``$VAULT_PATH/sessions/``.

    With no flags it captures everything new since the last run (tracked in
    ``.eidetic/last_session_save.txt``); ``--since`` captures a time window and
    ``--all`` captures every session. Runs through the audit trail, so a
    scheduled run (``EIDETIC_TRIGGER=scheduled``) is recorded as unattended.
    """
    _require_env("VAULT_PATH")
    args: list[str] = []
    if capture_all:
        args.append("--all")
    elif since:
        args += ["--since", since]
    if sessions_dir_opt:
        args += ["--sessions-dir", sessions_dir_opt]
    if as_json:
        args.append("--json")
    _run_audited(
        "session", scripts_dir() / "save_sessions.py", args,
        _context_for("session save", args),
    )


@session_app.command("list")
def session_list(
    limit: int = typer.Option(20, "--limit", "-n", help="Max sessions to show."),
    sessions_dir_opt: str = typer.Option(
        None, "--sessions-dir", help="Override the Cowork session store path."
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit the session list as JSON."
    ),
) -> None:
    """List recent Cowork sessions with their dates and titles (no writes)."""
    args = ["--list", "--limit", str(limit)]
    if sessions_dir_opt:
        args += ["--sessions-dir", sessions_dir_opt]
    if as_json:
        args.append("--json")
    _run(scripts_dir() / "save_sessions.py", args)


# ─────────────────────────────────────────────────────────────────────────────
# facts — Mem0-style fact extraction and a deduplicated fact store
# ─────────────────────────────────────────────────────────────────────────────
facts_app = typer.Typer(
    no_args_is_help=True,
    help="Extract, store, and search discrete facts (Mem0-style memory).",
)
app.add_typer(facts_app, name="facts")


def _fmt_fact(fact: facts_engine.StoredFact, *, score: float | None = None) -> str:
    """One-line coloured rendering of a stored fact for `facts list`/`search`."""
    cat = typer.style(f"{fact.category:<10}", fg=typer.colors.CYAN)
    conf = typer.style(f"{fact.confidence:.2f}", fg=typer.colors.BRIGHT_BLACK)
    line = f"  [{fact.id}] {cat} {conf}"
    if score is not None:
        line += typer.style(f" ·{score:.2f}", fg=typer.colors.GREEN)
    line += f"  {fact.fact}"
    if fact.source:
        line += typer.style(f"  ({fact.source})", fg=typer.colors.BRIGHT_BLACK)
    return line


@facts_app.command("extract")
def facts_extract(
    file: Path = typer.Argument(..., help="Markdown/text file to extract facts from."),
    no_llm: bool = typer.Option(
        False, "--no-llm", help="Skip the LLM extractor; use the heuristic only."
    ),
    threshold: float = typer.Option(
        facts_engine.DEFAULT_DEDUP_THRESHOLD, "--threshold",
        help="Dedup similarity threshold (0-1). Higher keeps more near-duplicates.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit the tally as JSON."),
) -> None:
    """Extract facts from a file and store them, deduplicating against memory.

    Prefers the detected local LLM for extraction (and embeddings for semantic
    dedup); falls back to a heuristic extractor and token-overlap dedup when no
    backend is reachable. Pass ``--no-llm`` to force the offline path.
    """
    if not file.is_file():
        _echo_fail(f"not a file: {file}")
        raise typer.Exit(code=1)
    text = file.read_text(encoding="utf-8", errors="replace")
    source = file.name

    with facts_engine.open_store(with_embedder=not no_llm) as store:
        tally = store.extract_and_ingest(
            text, source, use_llm=not no_llm, threshold=threshold
        )
        total_active = store.count()

    if as_json:
        typer.echo(json.dumps({**tally, "active_total": total_active}))
        return
    typer.secho(f"\nExtracted facts from {source}\n", bold=True)
    _echo_ok(f"{tally['inserted']} new")
    if tally["merged"]:
        _echo_ok(f"{tally['merged']} merged into existing facts")
    if tally["superseded"]:
        _echo_warn(f"{tally['superseded']} superseded a contradicting fact")
    if tally["duplicate"]:
        typer.echo(f"  · {tally['duplicate']} already known (skipped)")
    typer.echo(f"\n{total_active} active facts in the store.")


@facts_app.command("list")
def facts_list(
    category: str = typer.Option(
        None, "--category", "-c", help=f"Filter by category ({', '.join(facts_engine.CATEGORIES)})."
    ),
    limit: int = typer.Option(50, "--limit", "-n", help="Max facts to show."),
    include_inactive: bool = typer.Option(
        False, "--all", help="Include superseded (inactive) facts."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit facts as JSON."),
) -> None:
    """List stored facts, newest first, optionally filtered by category."""
    with facts_engine.open_store(with_embedder=False) as store:
        rows = store.list_facts(
            category=category, limit=limit, active_only=not include_inactive
        )
    if as_json:
        typer.echo(json.dumps([f.__dict__ for f in rows], indent=2))
        return
    if not rows:
        _echo_warn("no facts stored yet — run `eidetic facts extract <file>`")
        return
    typer.secho(f"\n{len(rows)} fact(s)\n", bold=True)
    for fact in rows:
        typer.echo(_fmt_fact(fact))


@facts_app.command("search")
def facts_search(
    query: str = typer.Argument(..., help="Search query."),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results."),
    as_json: bool = typer.Option(False, "--json", help="Emit results as JSON."),
) -> None:
    """Semantic search over active facts (cosine if a backend is up, else tokens)."""
    with facts_engine.open_store() as store:
        results = store.query_facts(query, limit=limit)
    if as_json:
        typer.echo(json.dumps(
            [{"score": s, **f.__dict__} for f, s in results], indent=2
        ))
        return
    if not results:
        _echo_warn("no matching facts")
        return
    typer.secho(f"\n{len(results)} result(s) for {query!r}\n", bold=True)
    for fact, score in results:
        typer.echo(_fmt_fact(fact, score=score))


@facts_app.command("stats")
def facts_stats(
    as_json: bool = typer.Option(False, "--json", help="Emit stats as JSON."),
) -> None:
    """Show fact-store statistics: totals, per-category, top sources."""
    with facts_engine.open_store(with_embedder=False) as store:
        stats = store.stats()
    if as_json:
        typer.echo(json.dumps(stats, indent=2))
        return
    typer.secho("\nFact store\n", bold=True)
    typer.echo(f"  active:     {stats['active']}")
    typer.echo(f"  superseded: {stats['superseded']}")
    typer.echo(f"  avg conf:   {stats['avg_confidence']:.2f}")
    typer.echo(f"  embeddings: {'on' if stats['has_embeddings'] else 'off (offline)'}")
    if stats["by_category"]:
        typer.secho("\n  by category", bold=True)
        for cat, n in stats["by_category"].items():
            typer.echo(f"    {cat:<12} {n}")
    if stats["by_source"]:
        typer.secho("\n  top sources", bold=True)
        for src, n in stats["by_source"].items():
            typer.echo(f"    {src:<24} {n}")


# ─────────────────────────────────────────────────────────────────────────────
# backends — pluggable LLM backend detection
# ─────────────────────────────────────────────────────────────────────────────
def _backends_list() -> None:
    """Probe every configured backend and print a status report."""
    try:
        forced = llm_backends.forced_backend_name()
    except llm_backends.BackendError as exc:
        _echo_fail(str(exc))
        raise typer.Exit(code=2) from exc

    statuses = llm_backends.backend_statuses()
    typer.secho("\nLLM backends\n", bold=True)
    if forced is not None:
        typer.echo(f"  forced via {llm_backends.FORCE_BACKEND_ENV}={forced}\n")

    active: str | None = forced
    if active is None:
        active = next((s.backend.name for s in statuses if s.reachable), None)

    for status in statuses:
        be = status.backend
        marker = "→" if be.name == active else " "
        if status.reachable:
            models = ", ".join(status.models[:4]) or "no models reported"
            _echo_ok(f"{marker} {be.label:<18} {be.base_url}  ({models})")
        else:
            _echo_warn(f"{marker} {be.label:<18} {be.base_url}  unreachable: {status.error}")

    typer.echo("")
    if active is None:
        _echo_warn("no backend reachable — start one, or set EIDETIC_LLM_BACKEND + *_URL")
        typer.echo("Run `eidetic backends test` once one is up to verify inference.")
    else:
        typer.secho(f"active backend: {active}", bold=True)
        typer.echo("Run `eidetic backends test` to verify inference end-to-end.")


def _backends_test() -> None:
    """Run a one-shot inference against the active (or forced) backend."""
    try:
        client = llm_backends.get_client()
    except llm_backends.BackendUnavailable as exc:
        _echo_fail(str(exc))
        raise typer.Exit(code=1) from exc
    except llm_backends.BackendError as exc:
        _echo_fail(str(exc))
        raise typer.Exit(code=2) from exc

    be = client.backend
    typer.secho(f"\nTesting {be.label} at {be.base_url}", bold=True)
    typer.echo(f"  model: {client.model}")
    typer.echo("  sending a one-line chat completion…\n")

    result = llm_backends.run_inference(client)
    if result.ok:
        _echo_ok(f"inference OK — model replied: {result.content!r}")
    else:
        _echo_fail(f"inference failed: {result.error}")
        raise typer.Exit(code=1)


@app.command()
def backends(
    action: str = typer.Argument(
        None, help="Omit to list backends; pass 'test' to run an inference test."
    ),
) -> None:
    """Show detected LLM backends; ``eidetic backends test`` runs an inference."""
    if action is None or action == "list":
        _backends_list()
    elif action == "test":
        _backends_test()
    else:
        _echo_fail(f"unknown action {action!r} — use nothing (list) or 'test'")
        raise typer.Exit(code=2)


# ─────────────────────────────────────────────────────────────────────────────
# doctor — diagnose the setup, then offer (or apply) fixes
# ─────────────────────────────────────────────────────────────────────────────
# Display order for the grouped report; any check whose category is missing here
# is appended after the known ones.
_DOCTOR_CATEGORIES: tuple[str, ...] = ("Config", "Git", "Sync", "LLM", "RAG", "SMTP")

# Re-embed once the index is older than this (point 4 of the doctor spec).
_RAG_STALE_AFTER = 24 * 3600.0


@dataclass(frozen=True)
class Fix:
    """A remediation a check can offer.

    A *safe* fix only touches state the user can trivially recreate — deleting a
    stale git lock left by a dead process, for instance — so ``eidetic doctor
    --fix`` applies it without asking. An *unsafe* fix (running the init wizard,
    creating the vault's first git commit) always prompts first, even under
    ``--fix``. ``apply`` does the work and returns ``(succeeded, message)``.
    """

    description: str
    safe: bool
    apply: Callable[[], tuple[bool, str]]


@dataclass(frozen=True)
class Check:
    """One health-check row, grouped under a :data:`_DOCTOR_CATEGORIES` heading."""

    category: str
    name: str
    status: str  # "OK" | "WARN" | "FAIL"
    detail: str
    next_step: str | None = None
    fix: Fix | None = field(default=None, compare=False)

    def as_dict(self) -> dict[str, object]:
        """JSON-serialisable view (the callable on ``fix`` is dropped)."""
        out: dict[str, object] = {
            "category": self.category,
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "next_step": self.next_step,
        }
        if self.fix is not None:
            out["fix"] = {"description": self.fix.description, "safe": self.fix.safe}
        return out


def _check_embeddings() -> tuple[str, str]:
    host = os.environ.get("EMBED_HOST", "localhost")
    port = os.environ.get("EMBED_PORT", "5555")
    url = os.environ.get("EMBED_URL")
    probe = url.rsplit("/v1/", 1)[0] + "/v1/models" if url else f"http://{host}:{port}/v1/models"
    try:
        resp = requests.get(probe, timeout=2)
    except requests.RequestException:
        return "WARN", f"unreachable at {probe} (RAG disabled until it's up)"
    if resp.status_code < 400:
        return "OK", f"reachable at {probe}"
    return "WARN", f"{probe} returned HTTP {resp.status_code}"


def _format_age(seconds: float) -> str:
    """Human-readable age for the RAG-freshness diagnosis."""
    if seconds < 3600:
        return f"{max(0, int(seconds // 60))}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def _is_offloaded(path: Path) -> bool:
    """True if ``path`` is iCloud-offloaded — dataless stub or ``.icloud`` placeholder."""
    if fileio.is_dataless(path):
        return True
    # A fully evicted file is replaced by a dot-prefixed `.<name>.icloud` stub.
    return path.with_name(f".{path.name}.icloud").exists()


# ── Fix implementations ───────────────────────────────────────────────────────
def _fix_run_init() -> tuple[bool, str]:
    """Run the interactive init wizard (unsafe fix for missing config)."""
    try:
        init(vault=None, yes=False, force=False)
    except typer.Exit as exc:
        if exc.exit_code:
            return False, f"init exited with code {exc.exit_code}"
    return True, "ran `eidetic init` — re-run `eidetic doctor` to confirm"


def _fix_clear_locks(vault: Path) -> Callable[[], tuple[bool, str]]:
    def apply() -> tuple[bool, str]:
        removed = gitutil.clear_stale_locks(vault)
        if removed:
            return True, f"removed {', '.join(removed)}"
        return True, "no locks remained to remove"
    return apply


def _git_init_result(vault: Path) -> tuple[bool, str]:
    """Initialise a git repo in ``vault`` with a first commit (unsafe fix)."""
    try:
        subprocess.run(["git", "init", "-q"], cwd=vault, check=True)
        subprocess.run(["git", "add", "-A"], cwd=vault, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "Initialise vault"], cwd=vault, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        return False, f"git init failed: {exc}"
    return True, "initialised the vault git repo with a first commit"


# ── Per-category check builders ───────────────────────────────────────────────
def _config_checks() -> list[Check]:
    checks: list[Check] = []

    py_ok = sys.version_info >= (3, 11)
    checks.append(Check(
        "Config", "Python", "OK" if py_ok else "FAIL",
        f"{sys.version_info.major}.{sys.version_info.minor} (need ≥ 3.11)",
        next_step=None if py_ok else "install Python 3.11+ and re-create the venv",
    ))

    vault_env = os.environ.get("VAULT_PATH")
    init_fix = Fix("run the `eidetic init` wizard", safe=False, apply=_fix_run_init)
    if not vault_env:
        checks.append(Check(
            "Config", "Vault path", "FAIL", "VAULT_PATH not set",
            next_step="run `eidetic init` to create a vault and write .env",
            fix=init_fix,
        ))
    elif not Path(os.path.expanduser(vault_env)).is_dir():
        vault = Path(os.path.expanduser(vault_env))
        checks.append(Check(
            "Config", "Vault path", "FAIL", f"{vault} does not exist",
            next_step="create the directory or run `eidetic init`",
            fix=init_fix,
        ))
    else:
        checks.append(Check(
            "Config", "Vault path", "OK", str(Path(os.path.expanduser(vault_env)))
        ))
    return checks


def _git_checks() -> list[Check]:
    """Vault git state: tracked-or-not, plus stale lock detection. Empty if no vault."""
    vault_env = os.environ.get("VAULT_PATH")
    if not vault_env:
        return []
    vault = Path(os.path.expanduser(vault_env))
    if not vault.is_dir():
        return []

    checks: list[Check] = []
    if (vault / ".git").is_dir():
        checks.append(Check("Git", "Repository", "OK", "vault is a git repo (tracked)"))
        locks = gitutil.find_stale_locks(vault)
        if locks:
            names = ", ".join(p.name for p in locks)
            checks.append(Check(
                "Git", "Locks", "WARN",
                f"stale git lock(s): {names} — blocks every git command",
                next_step="safe to delete (left by an interrupted git process)",
                fix=Fix(
                    f"delete {len(locks)} stale git lock file(s)",
                    safe=True, apply=_fix_clear_locks(vault),
                ),
            ))
        else:
            checks.append(Check("Git", "Locks", "OK", "no stale lock files"))
    else:
        checks.append(Check(
            "Git", "Repository", "WARN",
            "not a git repo (commit/changelog disabled)",
            next_step="initialise one to enable auto-commit and changelogs",
            fix=Fix(
                "initialise a git repo in the vault (creates a first commit)",
                safe=False, apply=lambda: _git_init_result(vault),
            ),
        ))
    return checks


def _sync_checks() -> list[Check]:
    """Vault sync health: last successful sync and any unresolved merge conflicts.

    Empty unless the vault is a git repo. Reads the last successful ``sync``
    action from the audit trail and inspects the working tree for conflict
    markers left by a merge that needs a human.
    """
    vault_env = os.environ.get("VAULT_PATH")
    if not vault_env:
        return []
    vault = Path(os.path.expanduser(vault_env))
    if not vault.is_dir() or not (vault / ".git").is_dir():
        return []

    checks: list[Check] = []
    successful = [
        e for e in audit.read_audit(action="sync", limit=100)
        if e.get("status") == "success"
    ]
    if successful:
        stamp = str(successful[-1].get("timestamp", "?"))
        checks.append(Check("Sync", "Last sync", "OK", f"last succeeded {stamp}"))
    else:
        checks.append(Check(
            "Sync", "Last sync", "WARN", "no successful sync recorded yet",
            next_step="run `eidetic sync` to pull remote changes safely",
        ))

    conflicts = git_sync.pending_conflicts(vault)
    if conflicts:
        shown = ", ".join(conflicts[:3]) + ("…" if len(conflicts) > 3 else "")
        checks.append(Check(
            "Sync", "Conflicts", "FAIL",
            f"{len(conflicts)} unresolved conflict(s): {shown}",
            next_step="resolve the conflict markers by hand, then commit",
        ))
    else:
        checks.append(Check("Sync", "Conflicts", "OK", "no pending conflicts"))
    return checks


def _llm_checks() -> list[Check]:
    """Probe the active LLM backend, diagnose if it's down, list alternatives."""
    try:
        forced = llm_backends.forced_backend_name()
    except llm_backends.BackendError as exc:
        return [Check(
            "LLM", "Backend", "FAIL", str(exc),
            next_step="set EIDETIC_LLM_BACKEND to a known backend (docs/CONFIGURATION.md)",
        )]

    statuses = llm_backends.backend_statuses()
    reachable = [s for s in statuses if s.reachable]
    checks: list[Check] = []

    if forced is not None:
        try:
            backend = llm_backends.get_backend(forced)
        except llm_backends.BackendError as exc:
            return [Check(
                "LLM", "Backend", "FAIL", str(exc),
                next_step=f"set the matching *_URL env var for {forced}",
            )]
        status = llm_backends.probe_backend(backend)
        if status.reachable:
            models = ", ".join(status.models[:3]) or "no models reported"
            checks.append(Check(
                "LLM", "Backend", "OK",
                f"{backend.label} at {backend.base_url} (forced; {models})",
            ))
        else:
            others = [s for s in reachable if s.backend.name != forced]
            alt = (
                "reachable alternatives: "
                + ", ".join(f"{s.backend.label} ({s.backend.base_url})" for s in others)
                if others else "no other backend is reachable either"
            )
            checks.append(Check(
                "LLM", "Backend", "WARN",
                f"{backend.label} at {backend.base_url} is not responding. Is it running?",
                next_step=f"Try: eidetic backends test — {alt}",
            ))
    else:
        active = reachable[0] if reachable else None
        if active is not None:
            models = ", ".join(active.models[:3]) or "no models reported"
            checks.append(Check(
                "LLM", "Backend", "OK",
                f"{active.backend.label} at {active.backend.base_url} ({models})",
            ))
        else:
            tried = ", ".join(s.backend.label for s in statuses) or "none configured"
            checks.append(Check(
                "LLM", "Backend", "WARN",
                "no LLM backend reachable (RAG, graph and trading all need one)",
                next_step=(
                    f"start LM Studio / Ollama / llama.cpp, then `eidetic backends test` "
                    f"(tried: {tried})"
                ),
            ))

    emb_status, emb_detail = _check_embeddings()
    checks.append(Check(
        "LLM", "Embeddings", emb_status, emb_detail,
        next_step=None if emb_status == "OK"
        else "start the embeddings server, then `eidetic embed --incremental`",
    ))
    return checks


def _rag_checks(now: float) -> list[Check]:
    """RAG index presence, freshness, and iCloud-offload detection. Empty if no vault."""
    vault_env = os.environ.get("VAULT_PATH")
    if not vault_env:
        return []
    vault = Path(os.path.expanduser(vault_env))
    if not vault.is_dir():
        return []

    rag_dir = Path(os.path.expanduser(os.environ.get("RAG_DIR", str(vault / ".rag"))))
    # The current store is SQLite (vectors.db); fall back to the legacy
    # vectors.json so a not-yet-migrated install still reports an index.
    vectors_db = rag_dir / "vectors.db"
    vectors = vectors_db if vectors_db.exists() else rag_dir / "vectors.json"
    last_embed = rag_dir / "last_embed.txt"
    checks: list[Check] = []

    # Active vector backend (VECTOR_BACKEND): sqlite (default), lancedb, or chroma.
    from eidetic_os.vector_backend import DEFAULT_BACKEND, active_backend_name
    backend = active_backend_name()
    if backend.endswith("(invalid)"):
        checks.append(Check(
            "RAG", "Backend", "WARN", f"VECTOR_BACKEND={backend}",
            next_step="set VECTOR_BACKEND to sqlite, lancedb, or chroma in .env",
        ))
    else:
        suffix = " (default)" if backend == DEFAULT_BACKEND else ""
        checks.append(Check("RAG", "Backend", "OK", f"{backend}{suffix}"))

    # Index presence.
    if vectors.exists():
        checks.append(Check("RAG", "Index", "OK", str(vectors)))
    else:
        checks.append(Check(
            "RAG", "Index", "WARN", "no vectors yet",
            next_step="run `eidetic embed --full` to build the index",
        ))

    # Freshness (only meaningful once an index exists).
    if vectors.exists():
        ts = 0.0
        if last_embed.exists():
            try:
                ts = float(last_embed.read_text().strip())
            except (ValueError, OSError):
                ts = 0.0
        if ts <= 0:
            checks.append(Check(
                "RAG", "Freshness", "WARN", "embed timestamp missing",
                next_step="run `eidetic embed --incremental` to refresh",
            ))
        else:
            age = max(0.0, now - ts)
            if age > _RAG_STALE_AFTER:
                checks.append(Check(
                    "RAG", "Freshness", "WARN",
                    f"vectors are {_format_age(age)} old (> 24h)",
                    next_step="run `eidetic embed --incremental` to refresh",
                ))
            else:
                checks.append(Check(
                    "RAG", "Freshness", "OK", f"embedded {_format_age(age)} ago"
                ))

    # iCloud offload on the key files (the recurring dataless-file problem).
    offloaded = [p for p in (vectors, last_embed) if p.exists() and _is_offloaded(p)]
    if offloaded:
        names = ", ".join(p.name for p in offloaded)
        checks.append(Check(
            "RAG", "iCloud", "WARN",
            f"offloaded to iCloud (dataless): {names}",
            next_step="download with `brctl download <file>` or open it in Finder",
        ))
    return checks


def _smtp_checks() -> list[Check]:
    has_email = bool(os.environ.get("SENDER_EMAIL")) and bool(
        os.environ.get("SMTP_APP_PASSWORD")
    )
    return [Check(
        "SMTP", "Email", "OK" if has_email else "WARN",
        "configured" if has_email else "not configured (reports won't send)",
        next_step=None if has_email
        else "set SENDER_EMAIL + SMTP_APP_PASSWORD in .env — see docs/TUTORIAL.md (Hour 4)",
    )]


def _doctor_results(now: float | None = None) -> list[Check]:
    """Run every health check and return the grouped :class:`Check` rows.

    Pure inspection — no printing, no process exit, no fixes applied — so both
    ``eidetic doctor`` and the ``eidetic init`` verification step can share it.
    ``now`` (a unix timestamp) is injectable so the RAG-freshness check is
    deterministic under test; it defaults to the wall clock.
    """
    when = time.time() if now is None else now
    results: list[Check] = []
    results.extend(_config_checks())
    results.extend(_git_checks())
    results.extend(_sync_checks())
    results.extend(_llm_checks())
    results.extend(_rag_checks(when))
    results.extend(_smtp_checks())
    return results


def _render_doctor(results: list[Check]) -> None:
    """Print the checks grouped by category, then an OK/WARN/FAIL summary."""
    ordered = sorted(
        results,
        key=lambda c: _DOCTOR_CATEGORIES.index(c.category)
        if c.category in _DOCTOR_CATEGORIES else len(_DOCTOR_CATEGORIES),
    )
    current: str | None = None
    for check in ordered:
        if check.category != current:
            current = check.category
            typer.secho(f"\n{check.category}", bold=True)
        line = f"{check.name:<12} {check.detail}"
        if check.status == "OK":
            _echo_ok(line)
        elif check.status == "WARN":
            _echo_warn(line)
        else:
            _echo_fail(line)
        if check.next_step and check.status != "OK":
            typer.secho(f"      → {check.next_step}", fg=typer.colors.CYAN)

    fails = sum(1 for c in results if c.status == "FAIL")
    warns = sum(1 for c in results if c.status == "WARN")
    typer.echo("")
    summary = f"{len(results) - fails - warns} OK · {warns} WARN · {fails} FAIL"
    typer.secho(summary, bold=True)


def _apply_fixes(results: list[Check], *, auto: bool) -> int:
    """Offer or apply the fixes attached to ``results``; return how many succeeded.

    Safe fixes are applied silently under ``--fix`` (``auto=True``); every other
    case prompts for confirmation. Unsafe fixes always prompt, even under
    ``--fix``.
    """
    fixable = [c for c in results if c.fix is not None]
    if not fixable:
        return 0

    typer.secho("\nFixes", bold=True)
    applied = 0
    for check in fixable:
        fix = check.fix
        assert fix is not None  # narrowed by the comprehension above
        if auto and fix.safe:
            run_it = True
        else:
            run_it = typer.confirm(
                f"  {check.name}: {fix.description}?", default=fix.safe
            )
        if not run_it:
            _echo_warn(f"{check.name}: skipped")
            continue
        ok, message = fix.apply()
        if ok:
            _echo_ok(f"{check.name}: {message}")
            applied += 1
        else:
            _echo_fail(f"{check.name}: {message}")
    return applied


@app.command()
def doctor(
    fix: bool = typer.Option(
        False, "--fix", help="Apply safe fixes automatically; prompt for unsafe ones."
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit the health report as JSON and exit."
    ),
) -> None:
    """Validate the Eidetic OS setup, diagnose problems, and offer fixes.

    Groups checks by category (Config, Git, LLM, RAG, SMTP), colour-codes each
    row, and prints an actionable next step for anything that isn't OK. Pass
    ``--fix`` to auto-apply safe remediations (clearing stale git locks) while
    still prompting for unsafe ones; pass ``--json`` for machine-readable output.
    """
    if as_json:
        results = _doctor_results()
        fail_count = sum(1 for c in results if c.status == "FAIL")
        payload = {
            "checks": [c.as_dict() for c in results],
            "summary": {
                "ok": sum(1 for c in results if c.status == "OK"),
                "warn": sum(1 for c in results if c.status == "WARN"),
                "fail": fail_count,
            },
        }
        typer.echo(json.dumps(payload, indent=2))
        raise typer.Exit(code=1 if fail_count else 0)

    typer.secho("\nEidetic OS — doctor", bold=True)
    results = _doctor_results()
    _render_doctor(results)

    if any(c.fix is not None for c in results):
        _apply_fixes(results, auto=fix)
        # Re-run so the summary and exit code reflect what the fixes changed.
        results = _doctor_results()
        typer.secho("\nAfter fixes", bold=True)
        _render_doctor(results)

    if any(c.status == "FAIL" for c in results):
        raise typer.Exit(code=1)


# ─────────────────────────────────────────────────────────────────────────────
# dashboard — the lightweight local web UI
# ─────────────────────────────────────────────────────────────────────────────
def _serve_dashboard(
    host: str,
    port: int,
    *,
    open_browser: bool,
    open_path: str = "/",
    debug: bool = False,
) -> None:
    """Build the dashboard app and run it, optionally opening a browser tab.

    Shared by ``eidetic dashboard`` and ``eidetic graph --open`` (which lands on
    ``/graph``). Exits with a friendly message if the dashboard extra (Flask)
    isn't installed.
    """
    try:
        from eidetic_os.dashboard.app import create_app
    except ModuleNotFoundError as exc:
        _echo_fail(str(exc))
        raise typer.Exit(code=1) from exc

    flask_app = create_app()
    base = f"http://{host}:{port}"
    typer.secho(f"\n  ⛰  Eidetic OS dashboard → {base}", fg=typer.colors.CYAN, bold=True)
    typer.echo("  Local-first and read-only. Press Ctrl+C to stop.\n")

    # Open the browser once, after a short delay so the server is accepting
    # connections. Skipped under --debug (the reloader spawns a child process,
    # which would otherwise open a second tab).
    if open_browser and not debug:
        import threading
        import webbrowser

        url = base + open_path
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    flask_app.run(host=host, port=port, debug=debug)


@app.command()
def dashboard(
    host: str = typer.Option(
        "127.0.0.1", "--host", help="Interface to bind (default localhost only)."
    ),
    port: int = typer.Option(8501, "--port", "-p", help="Port to serve on."),
    open_browser: bool = typer.Option(
        True, "--open/--no-open", help="Open the dashboard in your browser."
    ),
    debug: bool = typer.Option(
        False, "--debug", help="Run Flask in debug mode (auto-reload, tracebacks)."
    ),
) -> None:
    """Launch the local web dashboard (health, audit, skills, graph, vectors, search).

    A minimal, local-first Flask UI over the data ``eidetic`` already exposes —
    system health, the audit trail, scheduled tasks, the skills catalog, the
    knowledge graph, vector-store stats, and RAG search. It reads from your
    machine only; bind it to localhost and never expose it publicly with vault
    data behind it.

    Needs the optional dashboard extra: ``pip install 'eidetic-os[dashboard]'``.
    """
    _serve_dashboard(host, port, open_browser=open_browser, debug=debug)


# ─────────────────────────────────────────────────────────────────────────────
# serve — the lightweight REST API the Obsidian plugin talks to
# ─────────────────────────────────────────────────────────────────────────────
@app.command()
def serve(
    host: str = typer.Option(
        "127.0.0.1", "--host", help="Interface to bind (default localhost only)."
    ),
    port: int = typer.Option(8501, "--port", "-p", help="Port to serve on."),
    debug: bool = typer.Option(
        False, "--debug", help="Run Flask in debug mode (auto-reload, tracebacks)."
    ),
) -> None:
    """Start the plugin API server for the Obsidian plugin (and any local client).

    A minimal, local-first Flask REST layer over the same data ``eidetic`` already
    exposes — RAG search, the fact store, vector-store stats, and fact extraction —
    under ``/api/*`` with CORS enabled for localhost. The companion Obsidian plugin
    (``obsidian-plugin/``) points at this server (default
    ``http://localhost:8501``) to search memory, browse facts, and extract facts
    from a note without leaving Obsidian.

    It reads from your machine only; bind it to localhost and never expose it
    publicly with vault data behind it.

    Needs the optional dashboard extra: ``pip install 'eidetic-os[dashboard]'``.
    """
    try:
        from eidetic_os.plugin_server import create_plugin_app
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via import path
        _echo_fail(str(exc))
        raise typer.Exit(code=1) from exc

    try:
        flask_app = create_plugin_app()
    except ModuleNotFoundError as exc:
        _echo_fail(str(exc))
        raise typer.Exit(code=1) from exc

    base = f"http://{host}:{port}"
    typer.secho(
        f"\n  ⛰  Eidetic OS plugin API → {base}/api", fg=typer.colors.CYAN, bold=True
    )
    typer.echo("  Point the Obsidian plugin's server URL here.")
    typer.echo("  Local-first. Press Ctrl+C to stop.\n")
    flask_app.run(host=host, port=port, debug=debug)


# ─────────────────────────────────────────────────────────────────────────────
# extensions — optional, domain-specific modules that plug into the core
# ─────────────────────────────────────────────────────────────────────────────
extensions_app = typer.Typer(
    no_args_is_help=True,
    help="List and inspect the optional extensions plugged into Eidetic OS.",
)
app.add_typer(extensions_app, name="extensions")


@extensions_app.command("list")
def extensions_list() -> None:
    """List every discovered extension and whether it loaded cleanly.

    Extensions are domain-specific modules (trading, voice, jobs) discovered via
    the ``eidetic_os.extensions`` entry-point group and the bundled built-ins. Each
    is loaded onto this CLI at startup; anything that failed to load is shown with
    its error.
    """
    from eidetic_os import extensions as ext

    discovered = ext.list_extensions()
    if not discovered:
        _echo_warn("no extensions found")
        raise typer.Exit()

    errors = ext.discovery_errors()
    loaded = {e.name for e in ext.loaded_extensions()}

    typer.secho(f"\nExtensions ({len(discovered)} discovered):\n", bold=True)
    for found in discovered:
        instance = ext.get_extension(found.name) if found.name in loaded else None
        if instance is not None:
            typer.secho(f"  {found.name}", fg=typer.colors.CYAN, nl=False)
            typer.echo(f"  v{instance.version}  ·  [{found.source}]")
            typer.echo(f"    {instance.description}")
        elif found.name in errors:
            typer.secho(f"  {found.name}", fg=typer.colors.RED, nl=False)
            typer.echo(f"  [{found.source}] — failed to load")
            typer.secho(f"    {errors[found.name]}", fg=typer.colors.RED)
        else:
            typer.secho(f"  {found.name}", fg=typer.colors.CYAN, nl=False)
            typer.echo(f"  [{found.source}] — not loaded")
    typer.echo("\nRun `eidetic extensions info <name>` for details.")


@extensions_app.command("info")
def extensions_info(
    name: str = typer.Argument(..., help="Extension name to inspect."),
) -> None:
    """Show an extension's metadata, commands, skills, and schedules."""
    from eidetic_os import extensions as ext

    try:
        instance = ext.load_extension(name)
    except ext.ExtensionNotFoundError:
        _echo_fail(f"unknown extension {name!r} — run `eidetic extensions list`")
        raise typer.Exit(code=2) from None
    except ext.ExtensionLoadError as exc:
        _echo_fail(f"extension {name!r} failed to load: {exc}")
        raise typer.Exit(code=1) from exc

    typer.secho(f"\n{instance.name}  v{instance.version}", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  {instance.description}\n")

    skills = instance.register_skills()
    typer.secho(f"  Skills ({len(skills)}):", bold=True)
    for skill in skills:
        typer.echo(f"    • {skill.get('name', '?')} — {skill.get('description', '')}")
    if not skills:
        typer.echo("    (none)")

    schedules = instance.register_schedules()
    typer.secho(f"\n  Schedules ({len(schedules)}):", bold=True)
    for schedule in schedules:
        typer.echo(f"    • {schedule.get('name', '?')} — {schedule.get('cron', '')}")
    if not schedules:
        typer.echo("    (none)")
    typer.echo("")


def _load_extensions() -> None:
    """Discover and load every extension, registering its commands onto ``app``.

    Called once at import time, after all core commands are defined, so extension
    subcommands are present whenever the CLI runs. Fault-tolerant: a broken
    extension is skipped (its error surfaces in ``eidetic extensions list``) rather
    than stopping the core CLI from starting.
    """
    from eidetic_os import extensions as ext

    ext.load_all_extensions(app)


_load_extensions()


if __name__ == "__main__":
    app()
