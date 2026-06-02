"""The unified ``atlas`` command-line interface.

Subcommands:

* ``atlas init``     — interactive onboarding: detect your LLM, write .env,
                       scaffold the vault, install templates.
* ``atlas doctor``   — validate the whole setup and report OK / WARN / FAIL.
* ``atlas embed``    — RAG pipeline           (wraps scripts/embed_vault.py)
* ``atlas graph``    — knowledge graph        (wraps scripts/build_graph.py)
* ``atlas commit``   — auto-commit the vault  (wraps scripts/vault_commit.py)
* ``atlas changelog``— vault changelog        (wraps scripts/vault_changelog.py)
* ``atlas health``   — full health probe      (wraps scripts/health_check.py)
* ``atlas email``    — send an email          (wraps scripts/send_email.py)
* ``atlas schemas``  — enforce frontmatter     (wraps schemas/enforce_schemas.py)

Configuration is read from the environment; a ``.env`` in the current directory
or the repo root is auto-loaded on startup.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import requests
import typer
from dotenv import load_dotenv

from atlas_os import __version__
from atlas_os._paths import repo_root, schemas_dir, scripts_dir, templates_dir
from atlas_os._probe import detect_endpoints
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
def _run(path: Path, args: list[str]) -> None:
    if not path.exists():
        _echo_fail(f"Script not found: {path}")
        raise typer.Exit(code=2)
    raise typer.Exit(code=subprocess.call([sys.executable, str(path), *args]))


@app.command(context_settings=_PASSTHROUGH)
def embed(ctx: typer.Context) -> None:
    """Build/refresh the RAG vector store (--full | --incremental | --test N | …)."""
    _run(scripts_dir() / "embed_vault.py", ctx.args)


@app.command(context_settings=_PASSTHROUGH)
def graph(ctx: typer.Context) -> None:
    """Rebuild the wikilink knowledge graph."""
    _run(scripts_dir() / "build_graph.py", ctx.args)


@app.command(context_settings=_PASSTHROUGH)
def commit(ctx: typer.Context) -> None:
    """Auto-commit the vault with a categorised message (--dry-run | --json)."""
    _run(scripts_dir() / "vault_commit.py", ctx.args)


@app.command(context_settings=_PASSTHROUGH)
def changelog(ctx: typer.Context) -> None:
    """Summarise vault changes over a window (--since | --markdown | --json)."""
    _run(scripts_dir() / "vault_changelog.py", ctx.args)


@app.command(context_settings=_PASSTHROUGH)
def health(ctx: typer.Context) -> None:
    """Full subsystem health probe (--json | --quiet)."""
    _run(scripts_dir() / "health_check.py", ctx.args)


@app.command(context_settings=_PASSTHROUGH)
def email(ctx: typer.Context) -> None:
    """Send an email via SMTP. Pass a JSON payload as the argument."""
    _run(scripts_dir() / "send_email.py", ctx.args)


@app.command(context_settings=_PASSTHROUGH)
def schemas(ctx: typer.Context) -> None:
    """Enforce per-folder frontmatter schemas (--dry-run | --folder | --verbose)."""
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


@app.command()
def skills(
    sync: bool = typer.Option(
        False, "--sync", help="Write/refresh the catalog note in the vault."
    ),
    output: Path = typer.Option(
        None, "--output", help="Override the catalog note path (with --sync)."
    ),
) -> None:
    """List the agent skills catalog; ``--sync`` writes it into the vault."""
    items = load_skills()
    if not items:
        _echo_warn("no skills found")
        raise typer.Exit()

    typer.secho(f"\nAgent skills catalog ({len(items)} skill(s)):\n", bold=True)
    for s in items:
        typer.secho(f"  {s.name}", fg=typer.colors.CYAN, nl=False)
        typer.echo(f"  [{s.cadence}]")
        typer.echo(f"    {s.description}")

    if sync:
        vault = _resolve_vault()
        if vault is None or not vault.is_dir():
            _echo_fail("VAULT_PATH is not set or does not exist — run `atlas init`")
            raise typer.Exit(code=1)
        path = _write_catalog(vault, output)
        _echo_ok(f"wrote catalog → {path}")
    else:
        typer.echo("\nRun `atlas skills --sync` to write this into your vault.")


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


def _scaffold_vault(vault: Path) -> None:
    """Copy the vault skeleton, stripping .template suffixes."""
    skel = templates_dir() / "vault-skeleton"
    (vault / "wiki").mkdir(parents=True, exist_ok=True)
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
    """Guided onboarding: detect your LLM, write .env, scaffold the vault."""
    typer.secho("\nAtlas OS — setup\n", bold=True)

    # 1. Vault path
    default_vault = os.path.expanduser(
        os.environ.get("VAULT_PATH", "~/Documents/Obsidian/MyVault")
    )
    if vault is not None:
        vault_path = vault.expanduser().resolve()
    elif yes:
        vault_path = Path(default_vault).resolve()
    else:
        vault_path = Path(
            typer.prompt("Vault path", default=default_vault)
        ).expanduser().resolve()

    values: dict[str, str] = {"VAULT_PATH": str(vault_path)}

    # 2. Detect a local LLM
    typer.echo("\nProbing for a local LLM endpoint…")
    endpoints = detect_endpoints()
    if endpoints:
        for ep in endpoints:
            models = ", ".join(ep.models[:3]) or "no models reported"
            _echo_ok(f"{ep.label} at {ep.base_url} ({models})")
        chosen = endpoints[0]
        values["EMBED_HOST"] = chosen.host
        values["EMBED_PORT"] = str(chosen.port)
        values["LM_STUDIO_HOST"] = chosen.host
        values["LM_STUDIO_PORT"] = str(chosen.port)
        embed_models = [m for m in chosen.models if "embed" in m.lower()]
        if embed_models:
            values["EMBED_MODEL"] = embed_models[0]
        _echo_ok(f"using {chosen.base_url} for embeddings + chat")
    else:
        _echo_warn("no local LLM found — RAG/trading stay off until you set one up")

    # 3. Email (optional)
    if not yes and typer.confirm("\nConfigure email reports now?", default=False):
        values["SENDER_EMAIL"] = typer.prompt("Sender email")
        values["SMTP_SERVER"] = typer.prompt("SMTP server", default="smtp.gmail.com")
        values["SMTP_PORT"] = typer.prompt("SMTP port", default="587")
        values["SMTP_APP_PASSWORD"] = typer.prompt(
            "SMTP app password", hide_input=True, default=""
        )
        values["USER_EMAIL"] = typer.prompt(
            "Send reports to", default=values.get("SENDER_EMAIL", "")
        )

    # 4. Write .env
    env_dir = repo_root() or Path.cwd()
    env_path = env_dir / ".env"
    if env_path.exists() and not force:
        _echo_warn(f".env already exists at {env_path} — not overwriting (use --force)")
    else:
        env_path.write_text(_render_env(values), encoding="utf-8")
        _echo_ok(f"wrote {env_path}")

    # 5. Scaffold the vault
    typer.echo("\nScaffolding the vault skeleton…")
    _scaffold_vault(vault_path)
    try:
        catalog = _write_catalog(vault_path, None)
        _echo_ok(f"generated {catalog.relative_to(vault_path)}")
    except (FileNotFoundError, OSError) as exc:
        _echo_warn(f"could not generate the skills catalog ({exc})")
    _git_init(vault_path)

    # 6. CLAUDE.md (opt-in)
    home_claude = Path.home() / "CLAUDE.md"
    if not yes and not home_claude.exists() and typer.confirm(
        f"\nInstall the CLAUDE.md template to {home_claude}?", default=False
    ):
        shutil.copyfile(templates_dir() / "CLAUDE.md.template", home_claude)
        _echo_ok(f"wrote {home_claude} (edit the placeholders)")

    # 7. Next steps
    typer.secho("\nDone. Next steps:", bold=True)
    typer.echo("  1. Review your .env            (docs/CONFIGURATION.md)")
    typer.echo("  2. atlas doctor                 # verify the setup")
    typer.echo("  3. atlas embed --full           # build the RAG index (needs an LLM)")
    typer.echo("  4. atlas health                 # full subsystem report\n")


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


@app.command()
def doctor() -> None:
    """Validate the Atlas OS setup and report OK / WARN / FAIL."""
    typer.secho("\nAtlas OS — doctor\n", bold=True)
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

    # Render
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
    if fails:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
