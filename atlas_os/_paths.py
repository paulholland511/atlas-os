"""Locate the scripts, schemas, and templates the CLI drives.

Two install modes are supported, and resolved in this order:

1. **Source checkout / editable install** — the operational dirs live at the
   repo root; we detect that by walking up from this module. Preferred so dev
   edits to the scripts take effect immediately.
2. **Wheel / ``uv tool install`` / ``pipx install``** — the dirs are bundled
   into a top-level ``atlas_os_data/`` directory on ``sys.path`` (deliberately
   *not* inside the ``atlas_os`` package, so it can never shadow the import).
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent

# Markers that identify the repo root when running from a source checkout.
_ROOT_MARKERS = ("scripts", "schemas", "templates")
_DATA_DIRNAME = "atlas_os_data"


@lru_cache(maxsize=1)
def repo_root() -> Path | None:
    """Best-effort path to the source checkout root, or None if not found."""
    for parent in (_PACKAGE_ROOT, *_PACKAGE_ROOT.parents):
        if all((parent / m).is_dir() for m in _ROOT_MARKERS):
            return parent
    return None


@lru_cache(maxsize=1)
def _data_root() -> Path | None:
    """The bundled atlas_os_data dir from a wheel install, if present."""
    for entry in sys.path:
        if not entry:
            continue
        candidate = Path(entry) / _DATA_DIRNAME
        if candidate.is_dir():
            return candidate
    return None


def _resolve(name: str) -> Path:
    """Resolve a resource dir: live repo first, then bundled data."""
    root = repo_root()
    if root is not None and (root / name).is_dir():
        return root / name
    data = _data_root()
    if data is not None and (data / name).is_dir():
        return data / name
    raise FileNotFoundError(
        f"Could not locate the '{name}' resource directory. "
        "Reinstall Atlas OS, or run from a source checkout."
    )


def scripts_dir() -> Path:
    """Directory containing the pipeline scripts (embed_vault.py, …)."""
    return _resolve("scripts")


def schemas_dir() -> Path:
    """Directory containing enforce_schemas.py and schema docs."""
    return _resolve("schemas")


def templates_dir() -> Path:
    """Directory containing CLAUDE.md.template, the vault skeleton, etc."""
    return _resolve("templates")


def skills_dir() -> Path:
    """Directory containing the scheduled-task skill folders (each a SKILL.md)."""
    return _resolve("skills")
