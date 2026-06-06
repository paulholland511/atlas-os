"""Graceful migration from the legacy Atlas OS layout to Eidetic OS.

The project was renamed Atlas OS → Eidetic OS in the v4.0 cycle (see the
"Why we renamed" note in the README). Two pieces of legacy state can linger on
machines upgraded from an older install:

* a state directory written under ``.atlas/`` (or ``.atlas-os/``) rather than
  the current ``.eidetic/``; and
* ``ATLAS_*`` environment variables (in the shell or a ``.env``) rather than
  their ``EIDETIC_*`` equivalents.

This module bridges both forward automatically, once, so the user does not have
to do anything by hand:

* :func:`migrate_state_dir` copies a legacy state directory to ``.eidetic/`` the
  first time Eidetic OS runs against a vault that has the old layout but not the
  new one.
* :func:`migrate_env_vars` maps every ``ATLAS_<suffix>`` variable to
  ``EIDETIC_<suffix>`` when the new name is unset, so old shells and ``.env``
  files keep working while the user transitions.

Both are best-effort and deliberately defensive: a migration failure must never
stop the CLI from starting. :func:`run_migrations` ties them together and is
invoked once from the CLI's top-level callback.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable, MutableMapping
from pathlib import Path
from typing import Final

# Kept in sync with :data:`eidetic_os.config.CONFIG_DIRNAME`; duplicated here so
# this module stays import-light and usable before config is loaded.
NEW_DIRNAME: Final = ".eidetic"

# Legacy state directories, newest naming first. ``.atlas`` was the original
# per-vault state dir; ``.atlas-os`` was a short-lived variant.
LEGACY_DIRNAMES: Final[tuple[str, ...]] = (".atlas", ".atlas-os")

LEGACY_ENV_PREFIX: Final = "ATLAS_"
NEW_ENV_PREFIX: Final = "EIDETIC_"

# A message sink. The CLI passes a typer-backed writer that targets stderr (so
# migration notices never corrupt a command's ``--json`` stdout); the default
# writes to stderr directly for callers that use this module standalone.
Emit = Callable[[str], None]


def _default_emit(message: str) -> None:
    print(f"  ! {message}", file=sys.stderr)


def _resolve_base(environ: MutableMapping[str, str]) -> Path:
    """The primary vault base, mirroring :func:`eidetic_os.config.config_path`.

    ``VAULT_PATH`` wins (expanded); otherwise the current working directory.
    """
    vault = environ.get("VAULT_PATH")
    return Path(os.path.expanduser(vault)) if vault else Path.cwd()


def _candidate_bases(environ: MutableMapping[str, str]) -> list[Path]:
    """Directories that may hold a legacy state dir, de-duplicated, order-stable.

    The vault base (``VAULT_PATH`` or cwd) is checked first, then the user's home
    directory — covering both per-vault state and the ``~/.atlas/`` global case.
    """
    bases: list[Path] = []
    seen: set[Path] = set()
    for base in (_resolve_base(environ), Path.home()):
        resolved = base.expanduser()
        if resolved not in seen:
            seen.add(resolved)
            bases.append(resolved)
    return bases


def migrate_state_dir(
    base: Path,
    *,
    emit: Emit = _default_emit,
    copytree: Callable[[Path, Path], object] = shutil.copytree,
) -> Path | None:
    """Copy a legacy ``.atlas/`` / ``.atlas-os/`` dir under *base* to ``.eidetic/``.

    No-op (returns ``None``) when *base* already has a ``.eidetic/`` directory or
    holds no legacy directory. On success the new directory is a full copy of the
    legacy one (the original is left untouched as a safety net), a deprecation
    notice is emitted, and the new path is returned. Never raises.
    """
    new_dir = base / NEW_DIRNAME
    if new_dir.exists():
        return None
    for legacy_name in LEGACY_DIRNAMES:
        legacy_dir = base / legacy_name
        if not legacy_dir.is_dir():
            continue
        try:
            copytree(legacy_dir, new_dir)
        except OSError as exc:
            emit(f"could not migrate {legacy_dir} → {new_dir}: {exc}")
            return None
        emit(
            f"Migrated legacy {legacy_name}/ state to {NEW_DIRNAME}/ "
            f"(at {base}); the old directory was left in place and can be removed."
        )
        return new_dir
    return None


def migrate_env_vars(
    environ: MutableMapping[str, str] | None = None,
    *,
    emit: Emit = _default_emit,
) -> list[tuple[str, str]]:
    """Map ``ATLAS_*`` variables to their ``EIDETIC_*`` equivalents in *environ*.

    For every ``ATLAS_<suffix>`` that is set without a corresponding
    ``EIDETIC_<suffix>``, the value is copied across and a deprecation warning is
    emitted. The legacy variable is left in place (external tooling may still
    read it). Returns the list of ``(old_name, new_name)`` pairs mapped.
    """
    env = os.environ if environ is None else environ
    mapped: list[tuple[str, str]] = []
    # Snapshot the items: we mutate ``env`` while iterating.
    for name, value in list(env.items()):
        if not name.startswith(LEGACY_ENV_PREFIX):
            continue
        new_name = NEW_ENV_PREFIX + name[len(LEGACY_ENV_PREFIX) :]
        if env.get(new_name):
            continue
        env[new_name] = value
        emit(
            f"{name} is deprecated; applied its value as {new_name}. "
            f"Please rename it to {new_name}."
        )
        mapped.append((name, new_name))
    return mapped


def run_migrations(
    *,
    environ: MutableMapping[str, str] | None = None,
    emit: Emit = _default_emit,
) -> None:
    """Run all legacy→Eidetic migrations once at startup. Never raises.

    Env vars are mapped first (so a legacy ``ATLAS_VAULT_PATH`` can inform the
    state-dir base resolution if it ever existed), then each candidate base is
    checked for a legacy state directory.
    """
    env = os.environ if environ is None else environ
    try:
        migrate_env_vars(env, emit=emit)
        for base in _candidate_bases(env):
            migrate_state_dir(base, emit=emit)
    except Exception as exc:  # noqa: BLE001 — migration must never break startup
        emit(f"migration skipped after an unexpected error: {exc}")
