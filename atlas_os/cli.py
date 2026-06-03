"""The unified ``atlas`` command-line interface.

Subcommands:

* ``atlas init``     — interactive onboarding: detect your LLM, write .env,
                       scaffold the vault, install templates.
* ``atlas doctor``   — validate the whole setup and report OK / WARN / FAIL.
* ``atlas backends`` — show detected LLM backends; ``test`` runs an inference.
* ``atlas skills``   — list/show/install agent skills; ``--sync`` writes the catalog
* ``atlas embed``    — RAG pipeline           (wraps scripts/embed_vault.py)
* ``atlas graph``    — knowledge graph        (wraps scripts/build_graph.py)
* ``atlas commit``   — auto-commit the vault  (wraps scripts/vault_commit.py)
* ``atlas changelog``— vault changelog        (wraps scripts/vault_changelog.py)
* ``atlas health``   — full health probe      (wraps scripts/health_check.py)
* ``atlas email``    — send an email          (wraps scripts/send_email.py)
* ``atlas trading``  — trading research brief  (wraps scripts/trading_briefing.py)
* ``atlas schemas``  — enforce frontmatter     (wraps schemas/enforce_schemas.py)
* ``atlas audit``    — inspect the append-only audit trail (show | tail | export)

Every script-wrapping command appends an entry to the audit trail (see
``atlas_os.audit``) recording what ran, how it was triggered, the outcome,
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
from pathlib import Path

import requests
import typer
from dotenv import load_dotenv

from atlas_os import __version__, audit
from atlas_os import backends as llm_backends
from atlas_os import _skills
from atlas_os._paths import repo_root, schemas_dir, scripts_dir, templates_dir
from atlas_os._probe import Endpoint, detect_endpoints
from atlas_os._skills import default_catalog_path, load_skills, render_catalog

# ── Auto-load .env (repo root first, then cwd, which wins) ────────────────────
_root = repo_root()
if _root is not None:
    load_dotenv(_root / ".env")
load_dotenv(Path.cwd() / ".env", override=True)

app = typer.Typer(
    add_completion=True,
    no_args_is_help=True,
    help="Atlas OS — your local-first personal AI operating system.",
)

# Context settings that let a wrapper command forward arbitrary flags to the
# underlying script (e.g. `atlas embed --full --batch-size 16`).
_PASSTHROUGH = {"allow_extra_args": True, "ignore_unknown_options": True}


def _echo_ok(msg: str) -> None:
    typer.secho(f"  ✓ {msg}", fg=typer.colors.GREEN)


def _echo_warn(msg: str) -> None:
    typer.secho(f"  ! {msg}", fg=typer.colors.YELLOW)


def _echo_fail(msg: str) -> None:
    typer.secho(f"  ✗ {msg}", fg=typer.colors.RED)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"atlas-os {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    _version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Show the Atlas OS version and exit.",
    ),
) -> None:
    """Atlas OS command-line interface."""


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
        typer.echo("  Set them in .env (see .env.example) or run `atlas init`.")
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
    ``ATLAS_TRIGGER=scheduled`` to mark unattended runs.
    """
    if not path.exists():
        _echo_fail(f"Script not found: {path}")
        audit.log_action(
            action, os.environ.get("ATLAS_TRIGGER", "cli"), "error",
            context=context, error=f"script not found: {path}",
        )
        raise typer.Exit(code=2)

    trigger = os.environ.get("ATLAS_TRIGGER", "cli")
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
    return f"atlas {action}{extra}".strip()


@app.command(context_settings=_PASSTHROUGH)
def embed(ctx: typer.Context) -> None:
    """Build/refresh the RAG vector store (--full | --incremental | --test N | …)."""
    _require_env("VAULT_PATH")
    _run_audited("embed", scripts_dir() / "embed_vault.py", ctx.args,
                 _context_for("embed", ctx.args))


@app.command(context_settings=_PASSTHROUGH)
def graph(ctx: typer.Context) -> None:
    """Rebuild the wikilink knowledge graph."""
    _require_env("VAULT_PATH")
    _run_audited("graph", scripts_dir() / "build_graph.py", ctx.args,
                 _context_for("graph", ctx.args))


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


@app.command(context_settings=_PASSTHROUGH)
def health(ctx: typer.Context) -> None:
    """Full subsystem health probe (--json | --quiet)."""
    _run_audited("health", scripts_dir() / "health_check.py", ctx.args,
                 _context_for("health", ctx.args))


@app.command(context_settings=_PASSTHROUGH)
def trading(ctx: typer.Context) -> None:
    """Generate a trading research briefing (--ticker | --date | --dry-run).

    Optional component — needs the third-party TradingAgents package and a
    running local LLM endpoint. Reads VAULT_PATH and LM_STUDIO_* from the env.
    """
    _require_env("VAULT_PATH")
    _run_audited("trading", scripts_dir() / "trading_briefing.py", ctx.args,
                 _context_for("trading", ctx.args))


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
    help="List, show, and install the agent skills shipped with Atlas OS.",
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
            _echo_fail("VAULT_PATH is not set or does not exist — run `atlas init`")
            raise typer.Exit(code=1)
        path = _write_catalog(vault, output)
        _echo_ok(f"wrote catalog → {path}")
    else:
        typer.echo(
            "\nRun `atlas skills install <name>` to install one, "
            "or `atlas skills --sync` to write the catalog into your vault."
        )


@skills_app.command("list")
def skills_list() -> None:
    """List every available skill from the skills/ directory."""
    items = load_skills()
    if not items:
        _echo_warn("no skills found")
        raise typer.Exit()
    _print_skill_list(items)
    typer.echo("\nRun `atlas skills install <name>` to install one.")


@skills_app.command("show")
def skills_show(name: str = typer.Argument(..., help="Skill slug to display.")) -> None:
    """Print a skill's SKILL.md content to stdout."""
    skill = _skills.find_skill(name)
    if skill is None:
        _echo_fail(f"unknown skill {name!r} — run `atlas skills list`")
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

    The skill's SKILL.md is copied to ``$ATLAS_SKILLS_DIR/<name>/`` (or
    ``$VAULT_PATH/.claude/skills/<name>/`` by default) with its
    ``{{PLACEHOLDER}}`` tokens substituted from your environment / .env.
    """
    try:
        result = _skills.install_skill(name, force=force)
    except _skills.SkillNotFoundError:
        _echo_fail(f"unknown skill {name!r} — run `atlas skills list`")
        raise typer.Exit(code=2) from None
    except _skills.SkillInstallError as exc:
        _echo_fail(str(exc))
        raise typer.Exit(code=1) from exc

    verb = "reinstalled" if result.overwrote else "installed"
    _echo_ok(f"{verb} {result.slug} → {result.dest}")
    if result.resolved:
        filled = ", ".join(sorted(result.resolved))
        typer.echo(f"  filled {len(result.resolved)} placeholder(s): {filled}")
    if result.unresolved:
        left = ", ".join(result.unresolved)
        _echo_warn(
            f"{len(result.unresolved)} placeholder(s) left to fill by hand: {left}"
        )
        typer.echo(f"  edit them in {result.dest}")


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
# Atlas OS configuration — generated by `atlas init`.
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
SENDER_NAME={g("SENDER_NAME", "Atlas")}
SMTP_SERVER={g("SMTP_SERVER", "smtp.gmail.com")}
SMTP_PORT={g("SMTP_PORT", "587")}
SMTP_APP_PASSWORD={g("SMTP_APP_PASSWORD", "")}
USER_EMAIL={g("USER_EMAIL", "")}
"""


# Directories every Atlas OS vault needs, created up front by the wizard so the
# RAG store, audit trail, and wiki all have a home before anything writes to them.
_VAULT_DIRS: tuple[str, ...] = (".atlas", ".rag", "wiki")


def _detect_default_vault() -> str:
    """Best guess at where the user's vault lives, for the wizard's default.

    Resolution order:

    1. ``VAULT_PATH`` from the environment / an existing ``.env`` (explicit wins).
    2. The first sub-folder of ``~/Documents/Obsidian`` (the standard Obsidian
       home — most people have exactly one vault there).
    3. ``~/vault`` if it exists.
    4. The current directory, if it already looks like a vault (contains
       markdown files) and isn't the Atlas OS source checkout.
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
    """Friendly banner explaining what `atlas init` is about to do."""
    typer.secho("\n  ⛰  Atlas OS — setup wizard\n", fg=typer.colors.CYAN, bold=True)
    typer.echo(
        "  Atlas OS is your local-first personal AI operating system: a"
        " searchable\n  markdown vault with git history, RAG semantic search over"
        " your notes,\n  and a library of automated agent skills — all running"
        " on your machine.\n"
    )
    typer.echo("  This wizard will:")
    typer.echo("    • find your vault and any local LLM you're running")
    typer.echo("    • write a .env you can tweak later")
    typer.echo("    • scaffold the vault structure (.atlas/, .rag/, wiki/)")
    typer.echo("    • run `atlas doctor` to confirm everything works\n")


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


def _detect_backend(values: dict[str, str]) -> None:
    """Probe for a local LLM and fold any match's host/port/model into ``values``."""
    typer.echo("\n  Probing for a local LLM endpoint…")
    typer.secho(
        "    (LM Studio :5555 · Ollama :11434 · llama.cpp :8080)",
        fg=typer.colors.BRIGHT_BLACK,
    )
    endpoints = detect_endpoints()
    if not endpoints:
        _echo_warn("no local LLM found — RAG/trading stay off until you set one up")
        return
    for ep in endpoints:
        models = ", ".join(ep.models[:3]) or "no models reported"
        _echo_ok(f"{ep.label} at {ep.base_url} ({models})")
    chosen = endpoints[0]
    values.update(_backend_env_from_endpoint(chosen))
    _echo_ok(f"using {chosen.base_url} for embeddings + chat")


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
    vault: Path = typer.Option(
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
    ``atlas doctor`` to confirm it all works. ``--yes`` accepts every default for
    a fully non-interactive run.
    """
    _print_welcome()

    # 1. Vault path
    vault_path = _prompt_vault_path(vault, yes)
    values: dict[str, str] = {"VAULT_PATH": str(vault_path)}

    # 2. Detect a local LLM backend
    _detect_backend(values)

    # 3. Email (optional, interactive only)
    _prompt_email(values, yes)

    # 4. Write .env
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

    # 5. Scaffold the vault
    typer.echo("\n  Scaffolding the vault…")
    _scaffold_vault(vault_path)
    try:
        catalog = _write_catalog(vault_path, None)
        _echo_ok(f"generated {catalog.relative_to(vault_path)}")
    except (FileNotFoundError, OSError) as exc:
        _echo_warn(f"could not generate the skills catalog ({exc})")
    _git_init(vault_path)

    # 6. CLAUDE.md (opt-in, interactive only)
    home_claude = Path.home() / "CLAUDE.md"
    if not yes and not home_claude.exists() and typer.confirm(
        f"\n  Install the CLAUDE.md template to {home_claude}?", default=False
    ):
        shutil.copyfile(templates_dir() / "CLAUDE.md.template", home_claude)
        _echo_ok(f"wrote {home_claude} (edit the placeholders)")

    # 7. Verify the setup with the doctor
    typer.secho("\n  Verifying your setup…", bold=True)
    results = _doctor_results()
    _render_doctor(results)
    fails = sum(1 for _, status, _ in results if status == "FAIL")

    # 8. You're ready
    if fails:
        typer.secho(
            "\n  ⚠  Setup finished with issues — fix the FAILs above, "
            "then re-run `atlas doctor`.\n",
            fg=typer.colors.YELLOW,
            bold=True,
        )
    else:
        typer.secho("\n  ✓ You're ready!\n", fg=typer.colors.GREEN, bold=True)
    typer.echo("  Next steps:")
    typer.echo("    1. Review your .env             (docs/CONFIGURATION.md)")
    typer.echo("    2. atlas embed --full           # build the RAG index (needs an LLM)")
    typer.echo("    3. atlas skills list            # browse the agent skills")
    typer.echo("    4. atlas health                 # full subsystem report\n")


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
        _echo_warn("no backend reachable — start one, or set ATLAS_LLM_BACKEND + *_URL")
        typer.echo("Run `atlas backends test` once one is up to verify inference.")
    else:
        typer.secho(f"active backend: {active}", bold=True)
        typer.echo("Run `atlas backends test` to verify inference end-to-end.")


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
    """Show detected LLM backends; ``atlas backends test`` runs an inference."""
    if action is None or action == "list":
        _backends_list()
    elif action == "test":
        _backends_test()
    else:
        _echo_fail(f"unknown action {action!r} — use nothing (list) or 'test'")
        raise typer.Exit(code=2)


# ─────────────────────────────────────────────────────────────────────────────
# doctor
# ─────────────────────────────────────────────────────────────────────────────
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


def _doctor_results() -> list[tuple[str, str, str]]:
    """Run every health check and return ``(name, status, detail)`` rows.

    Pure inspection — no printing, no process exit — so both ``atlas doctor`` and
    the ``atlas init`` verification step can share it. ``status`` is one of
    ``"OK"`` / ``"WARN"`` / ``"FAIL"``.
    """
    results: list[tuple[str, str, str]] = []

    # Python
    py_ok = sys.version_info >= (3, 11)
    results.append((
        "Python", "OK" if py_ok else "FAIL",
        f"{sys.version_info.major}.{sys.version_info.minor} (need ≥ 3.11)",
    ))

    # Vault
    vault_env = os.environ.get("VAULT_PATH")
    if not vault_env:
        results.append(("Vault path", "FAIL", "VAULT_PATH not set — run `atlas init`"))
    else:
        vault = Path(os.path.expanduser(vault_env))
        if not vault.is_dir():
            results.append(("Vault path", "FAIL", f"{vault} does not exist"))
        else:
            results.append(("Vault path", "OK", str(vault)))
            git_state = "OK" if (vault / ".git").is_dir() else "WARN"
            results.append((
                "Vault git", git_state,
                "tracked" if git_state == "OK" else "not a git repo (commit/changelog off)",
            ))
            rag_dir = Path(os.path.expanduser(os.environ.get("RAG_DIR", str(vault / ".rag"))))
            vectors = rag_dir / "vectors.json"
            results.append((
                "RAG index", "OK" if vectors.exists() else "WARN",
                str(vectors) if vectors.exists() else "no vectors yet — run `atlas embed --full`",
            ))

    # Embeddings endpoint
    results.append(("Embeddings", *_check_embeddings()))

    # Email
    has_email = bool(os.environ.get("SENDER_EMAIL")) and bool(os.environ.get("SMTP_APP_PASSWORD"))
    results.append((
        "Email (SMTP)", "OK" if has_email else "WARN",
        "configured" if has_email else "not configured (reports won't send)",
    ))

    return results


def _render_doctor(results: list[tuple[str, str, str]]) -> None:
    """Print the doctor rows and a one-line OK/WARN/FAIL summary."""
    for name, status, detail in results:
        line = f"{name:<14} {detail}"
        if status == "OK":
            _echo_ok(line)
        elif status == "WARN":
            _echo_warn(line)
        else:
            _echo_fail(line)

    fails = sum(1 for _, s, _ in results if s == "FAIL")
    warns = sum(1 for _, s, _ in results if s == "WARN")
    typer.echo("")
    summary = f"{len(results) - fails - warns} OK · {warns} WARN · {fails} FAIL"
    typer.secho(summary, bold=True)


@app.command()
def doctor() -> None:
    """Validate the Atlas OS setup and report OK / WARN / FAIL."""
    typer.secho("\nAtlas OS — doctor\n", bold=True)
    results = _doctor_results()
    _render_doctor(results)
    if any(status == "FAIL" for _, status, _ in results):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
