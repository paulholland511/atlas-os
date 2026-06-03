"""Make the ``atlas_os`` package importable from a standalone script run.

The pipeline scripts run two ways:

1. Installed (``atlas embed`` → wheel): ``atlas_os`` is on ``sys.path`` already,
   so ``import atlas_os`` just works.
2. Source checkout (``python scripts/embed_vault.py``): the package isn't
   installed, so we walk up from this file to the repo root (the dir containing
   ``atlas_os/__init__.py``) and put it on ``sys.path``.

Call :func:`ensure_atlas_os` at the top of a script before importing the shared
hardening helpers (``atlas_os.retry`` / ``netio`` / ``fileio`` / ``gitutil`` /
``scriptkit``). It returns ``True`` if the package is importable, ``False`` if
not — letting a script degrade gracefully rather than crash on import.
"""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_atlas_os() -> bool:
    """Ensure ``import atlas_os`` works; return whether it is importable."""
    try:
        import atlas_os  # noqa: F401
        return True
    except ImportError:
        pass
    for parent in Path(__file__).resolve().parents:
        if (parent / "atlas_os" / "__init__.py").exists():
            sys.path.insert(0, str(parent))
            break
    try:
        import atlas_os  # noqa: F401
        return True
    except ImportError:
        return False
