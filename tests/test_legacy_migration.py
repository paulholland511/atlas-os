"""Tests for the legacy Atlas OS → Eidetic OS startup migration.

Covers :mod:`eidetic_os.migration`: copying a legacy ``.atlas/`` state directory
to ``.eidetic/`` and mapping ``ATLAS_*`` environment variables to ``EIDETIC_*``.
Both must be idempotent, non-destructive, and never raise.
"""

from __future__ import annotations

from pathlib import Path

from eidetic_os import migration


def _seed_legacy_dir(base: Path, name: str = ".atlas") -> Path:
    legacy = base / name
    legacy.mkdir(parents=True)
    (legacy / "config.yaml").write_text("vault_path: /tmp/v\n", encoding="utf-8")
    (legacy / "audit.jsonl").write_text('{"action": "x"}\n', encoding="utf-8")
    return legacy


def test_migrate_state_dir_copies_legacy(tmp_path: Path) -> None:
    _seed_legacy_dir(tmp_path)
    notices: list[str] = []

    result = migration.migrate_state_dir(tmp_path, emit=notices.append)

    assert result == tmp_path / ".eidetic"
    assert (tmp_path / ".eidetic" / "config.yaml").read_text(encoding="utf-8") == (
        "vault_path: /tmp/v\n"
    )
    assert (tmp_path / ".eidetic" / "audit.jsonl").exists()
    # Non-destructive: the legacy directory is left in place.
    assert (tmp_path / ".atlas" / "config.yaml").exists()
    assert any("Migrated legacy .atlas/ state to .eidetic/" in m for m in notices)


def test_migrate_state_dir_noop_when_new_dir_exists(tmp_path: Path) -> None:
    _seed_legacy_dir(tmp_path)
    (tmp_path / ".eidetic").mkdir()
    notices: list[str] = []

    assert migration.migrate_state_dir(tmp_path, emit=notices.append) is None
    assert notices == []
    # The existing .eidetic dir is untouched (not overwritten by the legacy copy).
    assert not (tmp_path / ".eidetic" / "config.yaml").exists()


def test_migrate_state_dir_noop_without_legacy(tmp_path: Path) -> None:
    notices: list[str] = []
    assert migration.migrate_state_dir(tmp_path, emit=notices.append) is None
    assert notices == []


def test_migrate_state_dir_prefers_dot_atlas(tmp_path: Path) -> None:
    _seed_legacy_dir(tmp_path, ".atlas")
    _seed_legacy_dir(tmp_path, ".atlas-os")
    notices: list[str] = []

    migration.migrate_state_dir(tmp_path, emit=notices.append)

    assert any(".atlas/ state" in m for m in notices)


def test_migrate_state_dir_never_raises_on_copy_error(tmp_path: Path) -> None:
    _seed_legacy_dir(tmp_path)
    notices: list[str] = []

    def _boom(_src: Path, _dst: Path) -> object:
        raise OSError("disk full")

    result = migration.migrate_state_dir(
        tmp_path, emit=notices.append, copytree=_boom
    )
    assert result is None
    assert any("could not migrate" in m for m in notices)


def test_migrate_env_vars_maps_unset(tmp_path: Path) -> None:
    env: dict[str, str] = {"ATLAS_LLM_BACKEND": "ollama", "PATH": "/usr/bin"}
    notices: list[str] = []

    mapped = migration.migrate_env_vars(env, emit=notices.append)

    assert env["EIDETIC_LLM_BACKEND"] == "ollama"
    # Legacy variable is left in place for external tooling.
    assert env["ATLAS_LLM_BACKEND"] == "ollama"
    assert ("ATLAS_LLM_BACKEND", "EIDETIC_LLM_BACKEND") in mapped
    assert any("EIDETIC_LLM_BACKEND" in m for m in notices)


def test_migrate_env_vars_does_not_clobber_existing(tmp_path: Path) -> None:
    env = {"ATLAS_LLM_BACKEND": "ollama", "EIDETIC_LLM_BACKEND": "lmstudio"}
    notices: list[str] = []

    mapped = migration.migrate_env_vars(env, emit=notices.append)

    assert env["EIDETIC_LLM_BACKEND"] == "lmstudio"
    assert mapped == []
    assert notices == []


def test_migrate_env_vars_ignores_unrelated(tmp_path: Path) -> None:
    env = {"VAULT_PATH": "/x", "HOME": "/home/u"}
    assert migration.migrate_env_vars(env) == []


def test_run_migrations_end_to_end(tmp_path: Path, monkeypatch) -> None:
    _seed_legacy_dir(tmp_path)
    monkeypatch.chdir(tmp_path)
    env: dict[str, str] = {"VAULT_PATH": str(tmp_path), "ATLAS_TRIGGER": "scheduled"}
    notices: list[str] = []

    migration.run_migrations(environ=env, emit=notices.append)

    assert (tmp_path / ".eidetic" / "config.yaml").exists()
    assert env["EIDETIC_TRIGGER"] == "scheduled"
