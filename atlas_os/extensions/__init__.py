"""Extension discovery and loading for Atlas OS.

The core stays lean by never importing a domain module directly. Instead it asks
this package, at startup, "what extensions exist?" and loads each one through the
:class:`~atlas_os.extensions.base.AtlasExtension` contract.

Two discovery channels are merged, in priority order:

1. **Entry points** — any installed package that registers a class under the
   ``atlas_os.extensions`` group (see ``pyproject.toml``). This is how a
   third-party extension ships, and how the bundled ones are found once
   Atlas OS is installed.
2. **Built-ins** — the extensions vendored in this package (``trading``,
   ``voice``, ``jobs``). Listed explicitly so they are discoverable even from a
   bare source checkout where entry-point metadata may be stale.

An entry point and a built-in that resolve to the same ``name`` are de-duplicated
(the entry point wins, so a user override of a bundled extension takes effect).

Discovery is intentionally fault-tolerant: an extension whose import raises (a
missing optional dependency, a syntax error in a third-party package) is skipped
with a recorded error rather than crashing the whole ``atlas`` CLI. Inspect those
with :func:`discovery_errors`.

Public API: :func:`list_extensions`, :func:`load_extension`,
:func:`load_all_extensions`, :func:`get_extension`, :func:`loaded_extensions`,
:func:`unload_extension`, :func:`discovery_errors`.
"""

from __future__ import annotations

import importlib
import importlib.metadata as importlib_metadata
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

from atlas_os.extensions.base import AtlasExtension

if TYPE_CHECKING:
    import typer

__all__ = [
    "AtlasExtension",
    "ExtensionError",
    "ExtensionLoadError",
    "ExtensionNotFoundError",
    "DiscoveredExtension",
    "ENTRY_POINT_GROUP",
    "BUILTIN_EXTENSIONS",
    "list_extensions",
    "load_extension",
    "load_all_extensions",
    "get_extension",
    "loaded_extensions",
    "unload_extension",
    "discovery_errors",
]

# The setuptools/importlib entry-point group third-party packages register under.
ENTRY_POINT_GROUP = "atlas_os.extensions"

# Built-in extensions vendored in this package, as ``name -> "module:ClassName"``
# import targets. Mirrors the entry points declared in pyproject.toml so the
# bundled extensions work from a source checkout too.
BUILTIN_EXTENSIONS: dict[str, str] = {
    "trading": "atlas_os.extensions.trading:TradingExtension",
    "voice": "atlas_os.extensions.voice:VoiceExtension",
    "jobs": "atlas_os.extensions.jobs:JobsExtension",
}


class ExtensionError(Exception):
    """Base class for extension errors."""


class ExtensionNotFoundError(ExtensionError):
    """Raised when no extension is registered under the requested name."""


class ExtensionLoadError(ExtensionError):
    """Raised when a discovered extension cannot be imported or instantiated."""


@dataclass(frozen=True)
class DiscoveredExtension:
    """A located-but-not-necessarily-loaded extension.

    ``target`` is the ``"module:ClassName"`` import path. ``source`` is where it
    was found — ``"entry-point"`` or ``"built-in"`` — for display and debugging.
    """

    name: str
    target: str
    source: str


# Module-level registry of loaded extension instances, keyed by name. Loading is
# idempotent: a second ``load_extension`` of an already-loaded name returns the
# cached instance rather than re-running ``on_load``.
_loaded: dict[str, AtlasExtension] = {}

# Errors hit during the last discovery/load, keyed by extension name, so the CLI
# can surface "trading: missing dependency yfinance" without aborting startup.
_errors: dict[str, str] = {}


def _resolve_target(target: str) -> type[AtlasExtension]:
    """Import a ``"module:ClassName"`` target and return the extension class.

    Raises :class:`ExtensionLoadError` if the module can't be imported, the
    attribute is missing, or the resolved object isn't an
    :class:`AtlasExtension` subclass.
    """
    module_name, _, attr = target.partition(":")
    if not module_name or not attr:
        raise ExtensionLoadError(f"malformed extension target {target!r} (want 'module:Class')")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ExtensionLoadError(f"could not import {module_name!r}: {exc}") from exc
    try:
        obj = getattr(module, attr)
    except AttributeError as exc:
        raise ExtensionLoadError(f"{module_name!r} has no attribute {attr!r}") from exc
    if not (isinstance(obj, type) and issubclass(obj, AtlasExtension)):
        raise ExtensionLoadError(f"{target!r} is not an AtlasExtension subclass")
    return obj


def _discover_entry_points() -> dict[str, DiscoveredExtension]:
    """Find extensions registered under the ``atlas_os.extensions`` entry-point group.

    The ``group=`` keyword form of ``entry_points`` is available on Python 3.10+;
    Atlas OS requires 3.11+, so no legacy fallback is needed.
    """
    found: dict[str, DiscoveredExtension] = {}
    for ep in importlib_metadata.entry_points(group=ENTRY_POINT_GROUP):
        # ep.value is the "module:ClassName" import target.
        found[ep.name] = DiscoveredExtension(
            name=ep.name, target=ep.value, source="entry-point"
        )
    return found


@lru_cache(maxsize=1)
def _discover() -> dict[str, DiscoveredExtension]:
    """Merge entry-point and built-in discovery, entry points taking precedence.

    Cached so repeated CLI lookups don't re-scan metadata; the cache is process
    -lifetime, which matches the CLI's single-invocation model.
    """
    discovered: dict[str, DiscoveredExtension] = {}
    for name, target in BUILTIN_EXTENSIONS.items():
        discovered[name] = DiscoveredExtension(name=name, target=target, source="built-in")
    # Entry points override built-ins of the same name (user/third-party wins).
    for name, found in _discover_entry_points().items():
        discovered[name] = found
    return dict(sorted(discovered.items()))


def list_extensions() -> list[DiscoveredExtension]:
    """Return every discovered extension, sorted by name (loaded or not)."""
    return list(_discover().values())


def discovery_errors() -> dict[str, str]:
    """Return the {name: error} map of extensions that failed to load."""
    return dict(_errors)


def load_extension(name: str) -> AtlasExtension:
    """Load, cache, and return the extension registered under ``name``.

    Idempotent: a second call returns the already-loaded instance without
    re-running ``on_load``. Raises :class:`ExtensionNotFoundError` if no
    extension is registered under ``name``, or :class:`ExtensionLoadError` if it
    is registered but cannot be imported or instantiated.
    """
    if name in _loaded:
        return _loaded[name]

    discovered = _discover().get(name)
    if discovered is None:
        raise ExtensionNotFoundError(
            f"no extension named {name!r} — run `atlas extensions list`"
        )

    cls = _resolve_target(discovered.target)
    instance = cls()
    instance.on_load()
    _loaded[name] = instance
    _errors.pop(name, None)
    return instance


def load_all_extensions(cli: typer.Typer | None = None) -> list[AtlasExtension]:
    """Load every discovered extension, registering commands onto ``cli`` if given.

    Fault-tolerant by design: an extension that fails to load is skipped and its
    error recorded in :func:`discovery_errors`, so one broken extension never
    stops the core CLI from starting. Returns the extensions that loaded cleanly,
    in discovery order.
    """
    loaded: list[AtlasExtension] = []
    for discovered in list_extensions():
        try:
            instance = load_extension(discovered.name)
        except ExtensionError as exc:
            _errors[discovered.name] = str(exc)
            continue
        if cli is not None:
            try:
                instance.register_commands(cli)
            except Exception as exc:  # noqa: BLE001 - a bad extension must not crash the CLI
                _errors[discovered.name] = f"register_commands failed: {exc}"
                continue
        loaded.append(instance)
    return loaded


def get_extension(name: str) -> AtlasExtension:
    """Return the already-loaded extension named ``name``.

    Raises :class:`ExtensionNotFoundError` if it has not been loaded. Use
    :func:`load_extension` to load on demand.
    """
    instance = _loaded.get(name)
    if instance is None:
        raise ExtensionNotFoundError(f"extension {name!r} is not loaded")
    return instance


def loaded_extensions() -> list[AtlasExtension]:
    """Return every currently-loaded extension instance, sorted by name."""
    return [_loaded[name] for name in sorted(_loaded)]


def unload_extension(name: str) -> None:
    """Unload a loaded extension, running its ``on_unload`` hook.

    Raises :class:`ExtensionNotFoundError` if it is not loaded. Primarily for
    tests and long-running hosts; the one-shot CLI rarely needs it.
    """
    instance = _loaded.pop(name, None)
    if instance is None:
        raise ExtensionNotFoundError(f"extension {name!r} is not loaded")
    instance.on_unload()


def _reset_for_tests() -> None:
    """Clear loaded instances, errors, and the discovery cache (test helper)."""
    _loaded.clear()
    _errors.clear()
    _discover.cache_clear()
