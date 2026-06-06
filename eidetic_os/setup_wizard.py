"""The interactive onboarding wizard behind ``eidetic init`` (Feature #25).

``eidetic init`` walks a fresh machine from nothing to a working setup. This
module holds the guided-interview pieces that make that walk friendly: an ASCII
banner, vault auto-detection, local-LLM probing, embedding-model selection, an
optional user profile, and the ``.eidetic/config.yaml`` writer — each usable on
its own and wired together by :func:`run_wizard`.

**Rich, with a plain fallback.** Output goes through a small :class:`WizardUI`
abstraction with two implementations: :class:`RichUI` (panels, tables, rules,
spinners) when `rich <https://rich.readthedocs.io>`_ is importable, and
:class:`PlainUI` (typer/click echo) when it isn't. Callers never branch on which
is active. Input goes through injectable ``prompt``/``confirm`` callables so the
whole flow is drivable from a test with scripted answers and captured output.

The CLI (``eidetic_os.cli``) keeps its own battle-tested vault/backend detection for
backward compatibility; this module's :func:`detect_vault` and
:func:`probe_backends` are the richer, independently-tested equivalents the
wizard and its tests use directly.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Protocol

import requests

from eidetic_os import config
from eidetic_os._probe import Endpoint, _parse_models

# ── ASCII banner ────────────────────────────────────────────────────────────────

BANNER: Final = r"""
 ___ _    _      _   _      ___  ___
| __(_)__| |___ | |_(_)__  / _ \/ __|
| _|| / _` / -_)|  _| / _| | (_) \__ \
|___|_\__,_\___| \__|_\__|  \___/|___/
"""

TAGLINE: Final = "your local-first personal AI operating system"


# ── Vault detection ─────────────────────────────────────────────────────────────

# Where Obsidian vaults commonly live, in preference order. ``~`` is expanded at
# scan time so the list stays a plain, testable constant.
_VAULT_SEARCH_PATHS: Final[tuple[str, ...]] = (
    "~/Documents/Obsidian",
    "~/Obsidian",
    "~/vault",
    "~/Documents/vault",
    "~/Notes",
)


def detect_vault(
    search_paths: Sequence[str] = _VAULT_SEARCH_PATHS,
    *,
    home: Path | None = None,
) -> Path | None:
    """Best guess at the user's vault directory, or ``None`` if nothing looks right.

    ``VAULT_PATH`` in the environment always wins. Otherwise each candidate in
    ``search_paths`` is examined: a directory that itself contains markdown (or a
    ``.obsidian`` folder) is taken as the vault; a directory that merely *holds*
    vaults (the standard ``~/Documents/Obsidian`` case) yields its first
    vault-looking sub-folder. ``home`` is injectable so tests can point the whole
    scan at a temp directory.
    """
    env = os.environ.get("VAULT_PATH")
    if env:
        return Path(os.path.expanduser(env))

    base = home or Path.home()
    for raw in search_paths:
        candidate = _expand(raw, base)
        if not candidate.is_dir():
            continue
        if _looks_like_vault(candidate):
            return candidate
        for child in sorted(candidate.iterdir()):
            if child.is_dir() and not child.name.startswith(".") and _looks_like_vault(child):
                return child
    return None


def _expand(raw: str, base: Path) -> Path:
    """Expand ``~`` against ``base`` (so tests can redirect home), else literally."""
    if raw.startswith("~/"):
        return base / raw[2:]
    if raw == "~":
        return base
    return Path(os.path.expanduser(raw))


def _looks_like_vault(path: Path) -> bool:
    """A directory is vault-shaped if it has an ``.obsidian`` dir or *top-level* markdown.

    Only markdown directly inside ``path`` counts — a directory that merely
    *holds* vaults (markdown one level down) is deliberately not vault-shaped, so
    :func:`detect_vault` descends into it and returns the actual sub-vault rather
    than the container.
    """
    if (path / ".obsidian").is_dir():
        return True
    try:
        return any(path.glob("*.md"))
    except OSError:
        return False


# ── LLM backend probing ─────────────────────────────────────────────────────────

# (label, base_url, models_path). A superset of eidetic_os._probe's list: the wizard
# also checks LM Studio's default :1234 and the documented LAN host so a freshly
# installed LM Studio is found without configuration. Probed in order; the first
# response per host:port wins.
_BACKEND_CANDIDATES: Final[tuple[tuple[str, str, str], ...]] = (
    ("LM Studio", "http://localhost:1234", "/v1/models"),
    ("LM Studio", "http://localhost:5555", "/v1/models"),
    ("LM Studio", "http://192.168.50.120:5555", "/v1/models"),
    ("Ollama", "http://localhost:11434", "/v1/models"),
    ("Ollama (native)", "http://localhost:11434", "/api/tags"),
    ("llama.cpp", "http://localhost:8080", "/v1/models"),
)


def probe_backends(
    candidates: Sequence[tuple[str, str, str]] = _BACKEND_CANDIDATES,
    *,
    timeout: float = 1.0,
) -> list[Endpoint]:
    """Probe well-known local LLM endpoints and return whatever responds.

    At most one :class:`Endpoint` per ``host:port`` is returned (first responding
    path wins), so a server exposing both ``/v1/models`` and a native API never
    appears twice. Every network error is swallowed — a probe that can't connect
    simply isn't in the result.
    """
    found: list[Endpoint] = []
    seen: set[str] = set()
    for label, base, path in candidates:
        if base in seen:
            continue
        try:
            resp = requests.get(f"{base}{path}", timeout=timeout)
        except requests.RequestException:
            continue
        if resp.status_code >= 400:
            continue
        try:
            models = _parse_models(resp.json())
        except ValueError:
            models = ()
        host = base.split("://", 1)[-1].split(":", 1)[0]
        port = int(base.rsplit(":", 1)[-1])
        seen.add(base)
        found.append(
            Endpoint(label=label, base_url=base, host=host, port=port, models=models)
        )
    return found


def embedding_models(endpoint: Endpoint) -> list[str]:
    """The endpoint's models that look like embedding models (name contains 'embed')."""
    return [m for m in endpoint.models if "embed" in m.lower()]


# ── UI abstraction (Rich with a plain fallback) ─────────────────────────────────

class WizardUI(Protocol):
    """The terminal surface the wizard draws on — Rich or plain, same calls."""

    def banner(self, version: str) -> None: ...
    def rule(self, text: str) -> None: ...
    def panel(self, title: str, lines: Sequence[str]) -> None: ...
    def success(self, text: str) -> None: ...
    def warn(self, text: str) -> None: ...
    def info(self, text: str) -> None: ...
    def table(self, title: str, columns: Sequence[str], rows: Sequence[Sequence[str]]) -> None: ...


class PlainUI:
    """A dependency-free UI: plain ``click.echo`` lines. The fallback when Rich is absent."""

    def __init__(self, echo: Callable[[str], None] | None = None) -> None:
        import click

        self._echo = echo or click.echo

    def banner(self, version: str) -> None:
        self._echo(BANNER)
        self._echo(f"  {TAGLINE}  ·  v{version}\n")

    def rule(self, text: str) -> None:
        self._echo(f"\n── {text} " + "─" * max(0, 60 - len(text)))

    def panel(self, title: str, lines: Sequence[str]) -> None:
        self._echo(f"\n  {title}")
        for line in lines:
            self._echo(f"    {line}")

    def success(self, text: str) -> None:
        self._echo(f"  ✓ {text}")

    def warn(self, text: str) -> None:
        self._echo(f"  ! {text}")

    def info(self, text: str) -> None:
        self._echo(f"  · {text}")

    def table(self, title: str, columns: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        self._echo(f"\n  {title}")
        self._echo("    " + "  ".join(columns))
        for row in rows:
            self._echo("    " + "  ".join(str(c) for c in row))


class RichUI:
    """A Rich-powered UI: banners in panels, real tables, coloured status lines."""

    def __init__(self, console: Any | None = None) -> None:
        from rich.console import Console

        self.console = console or Console()

    def banner(self, version: str) -> None:
        from rich.panel import Panel
        from rich.text import Text

        body = Text(BANNER.strip("\n"), style="bold cyan")
        body.append(f"\n\n{TAGLINE}", style="dim")
        self.console.print(Panel(body, subtitle=f"v{version}", expand=False))

    def rule(self, text: str) -> None:
        self.console.rule(f"[bold]{text}", align="left")

    def panel(self, title: str, lines: Sequence[str]) -> None:
        from rich.panel import Panel

        self.console.print(Panel("\n".join(lines), title=title, expand=False))

    def success(self, text: str) -> None:
        self.console.print(f"  [green]✓[/green] {text}")

    def warn(self, text: str) -> None:
        self.console.print(f"  [yellow]![/yellow] {text}")

    def info(self, text: str) -> None:
        self.console.print(f"  [dim]·[/dim] {text}")

    def table(self, title: str, columns: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        from rich.table import Table

        table = Table(title=title, title_justify="left")
        for col in columns:
            table.add_column(col)
        for row in rows:
            table.add_row(*(str(c) for c in row))
        self.console.print(table)


def make_ui(*, plain: bool = False) -> WizardUI:
    """Return a :class:`RichUI` when Rich is importable, else a :class:`PlainUI`.

    Pass ``plain=True`` to force the dependency-free renderer (used by tests and
    by ``--no-rich``).
    """
    if plain:
        return PlainUI()
    try:
        return RichUI()
    except Exception:  # noqa: BLE001 - rich missing or a console it can't build → plain
        return PlainUI()


# ── Profile + config assembly ───────────────────────────────────────────────────

@dataclass(frozen=True)
class Profile:
    """The optional user profile collected by the wizard (any field may be empty)."""

    name: str = ""
    role: str = ""
    style: str = ""

    @property
    def is_empty(self) -> bool:
        return not (self.name or self.role or self.style)

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "role": self.role, "style": self.style}


@dataclass
class WizardResult:
    """Everything the wizard gathered: the config document and the .env values.

    ``config`` is the dict written to ``.eidetic/config.yaml``; ``env`` is the
    subset that also belongs in ``.env`` (so the existing ``.env`` machinery and
    the new YAML config stay in agreement).
    """

    vault_path: Path
    endpoint: Endpoint | None
    embed_model: str | None
    profile: Profile
    config: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)


def build_config(
    *,
    vault_path: Path,
    endpoint: Endpoint | None,
    embed_model: str | None,
    profile: Profile,
    memory: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Assemble the ``.eidetic/config.yaml`` document from the collected settings.

    The ``memory`` section is seeded with the decay/relevance defaults (Feature
    #27) so the file is self-documenting and a user can tune scoring by editing
    it. Sections with nothing to say (no backend, an empty profile) are omitted.
    """
    document: dict[str, Any] = {"vault_path": str(vault_path)}
    if endpoint is not None:
        backend: dict[str, Any] = {
            "label": endpoint.label,
            "base_url": endpoint.base_url,
            "host": endpoint.host,
            "port": endpoint.port,
        }
        if embed_model:
            backend["embed_model"] = embed_model
        document["backend"] = backend
    if not profile.is_empty:
        document["profile"] = profile.as_dict()
    document["memory"] = dict(memory or config.DEFAULT_MEMORY)
    return document


def env_from_result(
    vault_path: Path, endpoint: Endpoint | None, embed_model: str | None
) -> dict[str, str]:
    """The ``.env`` key/value pairs implied by the detected vault + backend."""
    env: dict[str, str] = {"VAULT_PATH": str(vault_path)}
    if endpoint is not None:
        env.update(
            {
                "EMBED_HOST": endpoint.host,
                "EMBED_PORT": str(endpoint.port),
                "LM_STUDIO_HOST": endpoint.host,
                "LM_STUDIO_PORT": str(endpoint.port),
            }
        )
        if embed_model:
            env["EMBED_MODEL"] = embed_model
    return env


def write_config(document: dict[str, Any], path: Path | None = None) -> Path:
    """Persist the config document to ``.eidetic/config.yaml``. Returns the path."""
    return config.save_config(document, path)


# ── Interactive flow ─────────────────────────────────────────────────────────────

# Injectable IO so the whole interview is drivable from a test. Defaults bind to
# click at call time (not import time) to keep the module import side-effect-free.
Prompt = Callable[[str, str], str]  # (question, default) -> answer
Confirm = Callable[[str, bool], bool]  # (question, default) -> yes/no
Select = Callable[[str, Sequence[str], int], int]  # (question, options, default_idx) -> idx


def _default_prompt(question: str, default: str) -> str:
    import click

    return click.prompt(question, default=default, show_default=True)


def _default_confirm(question: str, default: bool) -> bool:
    import click

    return click.confirm(question, default=default)


def _default_select(question: str, options: Sequence[str], default_idx: int) -> int:
    import click

    for i, option in enumerate(options):
        click.echo(f"    {i + 1}. {option}")
    choice = click.prompt(
        question, default=default_idx + 1, show_default=True, type=int
    )
    return max(0, min(len(options) - 1, int(choice) - 1))


def select_embedding_model(
    ui: WizardUI,
    endpoint: Endpoint,
    *,
    interactive: bool,
    select: Select | None = None,
) -> str | None:
    """Choose which embedding model to use, prompting only when it's ambiguous.

    With zero or one embedding model the choice is automatic (and silent). With
    several, an interactive run asks; a non-interactive run takes the first.
    """
    options = embedding_models(endpoint)
    if not options:
        return None
    if len(options) == 1 or not interactive:
        return options[0]
    chooser = select or _default_select
    idx = chooser("  Embedding model", options, 0)
    return options[idx]


def collect_profile(
    ui: WizardUI,
    *,
    interactive: bool,
    prompt: Prompt | None = None,
    confirm: Confirm | None = None,
) -> Profile:
    """Optionally collect name / role / communication style (skippable, interactive only)."""
    if not interactive:
        return Profile()
    ask = prompt or _default_prompt
    yes_no = confirm or _default_confirm
    if not yes_no("\n  Set up your profile now? (optional)", False):
        return Profile()
    name = ask("  Your name", "").strip()
    role = ask("  Your role", "").strip()
    style = ask("  Preferred communication style (e.g. terse, detailed)", "").strip()
    return Profile(name=name, role=role, style=style)


def run_wizard(
    *,
    version: str,
    vault: Path | None = None,
    interactive: bool = True,
    plain: bool = False,
    ui: WizardUI | None = None,
    prompt: Prompt | None = None,
    confirm: Confirm | None = None,
    select: Select | None = None,
    probe: Callable[[], list[Endpoint]] = probe_backends,
    write: bool = True,
) -> WizardResult:
    """Run the full guided interview and return everything it gathered.

    Steps: banner → vault detection/confirmation → backend probe → embedding-model
    selection → profile → build & (optionally) write ``.eidetic/config.yaml``. All
    IO is injectable, so a test drives it with scripted ``prompt``/``confirm``/
    ``select`` callables and an in-memory ``ui``; ``write=False`` returns the
    assembled config without touching disk. The CLI's ``init`` reuses the building
    blocks above rather than this orchestrator, so the two can't drift on the
    asserted output, but ``run_wizard`` is a complete, standalone entry point.
    """
    ui = ui or make_ui(plain=plain)
    ask = prompt or _default_prompt

    ui.banner(version)

    # 1. Vault.
    ui.rule("Vault")
    detected = vault or detect_vault()
    if interactive:
        chosen = ask("  Vault path", str(detected) if detected else "")
        vault_path = Path(os.path.expanduser(chosen)).resolve()
    else:
        vault_path = (detected or Path.cwd()).expanduser().resolve()
    ui.success(f"vault: {vault_path}")

    # 2. Backend.
    ui.rule("Local LLM")
    endpoints = probe()
    if endpoints:
        ui.table(
            "Detected backends",
            ["backend", "endpoint", "models"],
            [
                (ep.label, ep.base_url, str(len(ep.models)))
                for ep in endpoints
            ],
        )
        endpoint: Endpoint | None = endpoints[0]
        ui.success(f"using {endpoint.label} at {endpoint.base_url}")
    else:
        endpoint = None
        ui.warn("no local LLM found — RAG stays off until you configure one")

    # 3. Embedding model.
    embed_model = (
        select_embedding_model(ui, endpoint, interactive=interactive, select=select)
        if endpoint is not None
        else None
    )
    if embed_model:
        ui.success(f"embedding model: {embed_model}")

    # 4. Profile.
    ui.rule("Profile")
    profile = collect_profile(ui, interactive=interactive, prompt=prompt, confirm=confirm)
    if profile.is_empty:
        ui.info("no profile set (you can add one later in .eidetic/config.yaml)")

    # 5. Assemble + write config.
    document = build_config(
        vault_path=vault_path,
        endpoint=endpoint,
        embed_model=embed_model,
        profile=profile,
    )
    result = WizardResult(
        vault_path=vault_path,
        endpoint=endpoint,
        embed_model=embed_model,
        profile=profile,
        config=document,
        env=env_from_result(vault_path, endpoint, embed_model),
    )
    if write:
        path = write_config(document)
        ui.success(f"wrote {path}")
    return result
