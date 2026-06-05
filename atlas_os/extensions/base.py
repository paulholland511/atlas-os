"""The extension contract — :class:`AtlasExtension`.

An *extension* is an optional, domain-specific bundle of functionality that
plugs into the lean Atlas OS core (vault parsing, git sync, RAG, CLI, dashboard,
audit trail) without the core ever importing it. Trading, voice/TTS, and the job
tracker are the bundled examples; a third-party package can ship its own by
exposing a subclass under the ``atlas_os.extensions`` entry-point group.

The core only ever sees this abstract surface. An extension declares its
identity (``name`` / ``description``) and may hook into four extension points:

* **commands** — add subcommands to the ``atlas`` Typer app
  (``register_commands``);
* **skills** — contribute scheduled-task skill definitions
  (``register_skills``);
* **schedules** — contribute cron-like schedule definitions
  (``register_schedules``);
* **lifecycle** — run setup/teardown when loaded or unloaded
  (``on_load`` / ``on_unload``).

Every hook except the two identity properties has a no-op default, so a minimal
extension only has to implement ``name`` and ``description``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import typer


class AtlasExtension(ABC):
    """Base class for Atlas OS extensions.

    Subclass this and implement at least :attr:`name` and :attr:`description`.
    The core discovers, instantiates, and drives subclasses through this
    interface alone — it never imports an extension's internals directly, which
    is what keeps the core decoupled from every domain module.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The extension's stable identifier (lowercase slug, e.g. ``trading``).

        Used as the key for ``atlas extensions info <name>``, entry-point
        registration, and de-duplication when the same extension is found via
        more than one discovery channel.
        """

    @property
    @abstractmethod
    def description(self) -> str:
        """A one-line, human-readable summary shown in ``atlas extensions list``."""

    @property
    def version(self) -> str:
        """The extension's version string. Defaults to ``"0.0.0"``."""
        return "0.0.0"

    def register_commands(self, cli: typer.Typer) -> None:
        """Register this extension's CLI commands onto the ``atlas`` Typer app.

        Called once at load time with the top-level :class:`typer.Typer`
        instance. Add commands with ``@cli.command()`` or mount a sub-app with
        ``cli.add_typer(...)``. The default is a no-op.
        """

    def register_skills(self) -> list[dict[str, Any]]:
        """Return the scheduled-task skill definitions this extension provides.

        Each entry is a plain dict (``name``, ``description``, ``cadence``, …)
        so the core can list them without importing the extension's types. The
        default returns an empty list.
        """
        return []

    def register_schedules(self) -> list[dict[str, Any]]:
        """Return the cron-like schedule definitions this extension provides.

        Each entry is a plain dict (``name``, ``cron``, ``command``, …). The
        default returns an empty list.
        """
        return []

    def on_load(self) -> None:
        """Hook run once after the extension is instantiated and registered.

        Use for cheap, side-effect-light setup (reading config, warming a
        cache). Heavy or failure-prone work belongs in the commands themselves
        so a broken dependency never stops the core from starting. The default
        is a no-op.
        """

    def on_unload(self) -> None:
        """Hook run when the extension is unloaded. The default is a no-op."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} name={self.name!r} version={self.version!r}>"
