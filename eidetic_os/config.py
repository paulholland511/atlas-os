"""Shared YAML configuration for Eidetic OS — ``.eidetic/config.yaml``.

The setup wizard (``eidetic init``) writes this file; other subsystems read it.
It is deliberately small and dependency-light: a single YAML document with a
handful of nested sections, loaded into a plain ``dict``. Nothing here ever
raises on a missing or malformed file — callers always get a usable dict (the
defaults) so a fresh machine with no config still works.

Resolution order for the file location mirrors :func:`eidetic_os.facts.facts_db_path`:

1. ``EIDETIC_CONFIG_PATH`` — explicit override (used by tests).
2. ``$VAULT_PATH/.eidetic/config.yaml`` — the conventional home.
3. ``./.eidetic/config.yaml`` — when run from a vault checkout with no env set.

Sections written by the wizard:

* ``vault_path``         — the resolved vault directory.
* ``backend``            — detected LLM endpoint (label, base_url, embed_model).
* ``profile``            — optional name / role / communication style.
* ``memory``             — decay/relevance parameters (see :data:`DEFAULT_MEMORY`).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Final

import yaml

CONFIG_DIRNAME: Final = ".eidetic"
CONFIG_FILENAME: Final = "config.yaml"

# Default memory-scoring parameters (Feature #27). Kept here so both the scorer
# and the wizard agree on the shape, and a config that omits the section still
# yields a fully-specified set of knobs.
DEFAULT_MEMORY: Final[dict[str, float]] = {
    # Slow exponential decay: λ=0.01 per day ≈ a 69-day half-life.
    "decay_lambda": 0.01,
    # Reinforcement: each access nudges relevance up by this coefficient.
    "reinforcement_beta": 0.5,
    # Facts whose relevance falls below this are deactivated (forgotten).
    "deactivation_threshold": 0.05,
}


def config_path() -> Path:
    """Resolve the config file path from the environment.

    Order: ``EIDETIC_CONFIG_PATH`` → ``$VAULT_PATH/.eidetic/config.yaml`` →
    ``./.eidetic/config.yaml``.
    """
    override = os.environ.get("EIDETIC_CONFIG_PATH")
    if override:
        return Path(os.path.expanduser(override))
    vault = os.environ.get("VAULT_PATH")
    base = Path(os.path.expanduser(vault)) if vault else Path.cwd()
    return base / CONFIG_DIRNAME / CONFIG_FILENAME


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load the config document, or an empty dict if it is absent/unreadable.

    Never raises: a missing file, a permission error, or malformed YAML all
    return ``{}`` so callers can layer their own defaults on top.
    """
    target = path or config_path()
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def save_config(data: dict[str, Any], path: Path | None = None) -> Path:
    """Write ``data`` as YAML to the config path, creating parents. Returns the path."""
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return target


def memory_params(path: Path | None = None) -> dict[str, float]:
    """The memory-scoring parameters, config overriding :data:`DEFAULT_MEMORY`.

    Reads the ``memory:`` section of the config (if any) and overlays it on the
    defaults, coercing each value to ``float`` and silently dropping anything
    that isn't a recognised key or isn't numeric — so a hand-edited config can
    never feed a bad type into the decay formula.
    """
    params = dict(DEFAULT_MEMORY)
    section = load_config(path).get("memory")
    if isinstance(section, dict):
        for key in DEFAULT_MEMORY:
            if key in section:
                try:
                    params[key] = float(section[key])
                except (TypeError, ValueError):
                    continue
    return params
