"""Tests for the skills catalog, placeholder substitution, and install command.

These are hermetic: the install tests point ``ATLAS_SKILLS_DIR`` at a temp
directory and never touch the real vault. The source skills are read from the
repo's ``skills/`` directory (the live checkout), so they exercise the real
SKILL.md files.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from atlas_os import _skills
from atlas_os.cli import app

runner = CliRunner()


# ── substitute_placeholders ───────────────────────────────────────────────────
def test_substitute_fills_known_tokens() -> None:
    text = "vault={{VAULT_PATH}} mail={{USER_EMAIL}}"
    env = {"VAULT_PATH": "/v", "USER_EMAIL": "a@b.c"}
    rendered, resolved, unresolved = _skills.substitute_placeholders(text, env)
    assert rendered == "vault=/v mail=a@b.c"
    assert resolved == {"VAULT_PATH": "/v", "USER_EMAIL": "a@b.c"}
    assert unresolved == []


def test_substitute_leaves_unknown_tokens_untouched() -> None:
    text = "have={{VAULT_PATH}} missing={{JOB_TRACKER_PATH}}"
    rendered, resolved, unresolved = _skills.substitute_placeholders(
        text, {"VAULT_PATH": "/v"}
    )
    assert rendered == "have=/v missing={{JOB_TRACKER_PATH}}"
    assert resolved == {"VAULT_PATH": "/v"}
    assert unresolved == ["JOB_TRACKER_PATH"]


def test_substitute_unresolved_is_deduped_and_ordered() -> None:
    text = "{{B}} {{A}} {{B}} {{A}}"
    _, _, unresolved = _skills.substitute_placeholders(text, {})
    assert unresolved == ["B", "A"]


def test_substitute_empty_env_value_counts_as_unresolved() -> None:
    text = "x={{USER_EMAIL}}"
    rendered, resolved, unresolved = _skills.substitute_placeholders(
        text, {"USER_EMAIL": ""}
    )
    assert rendered == "x={{USER_EMAIL}}"
    assert resolved == {}
    assert unresolved == ["USER_EMAIL"]


def test_substitute_token_alias_llm_port() -> None:
    rendered, resolved, _ = _skills.substitute_placeholders(
        "port={{LLM_PORT}}", {"LM_STUDIO_PORT": "5555"}
    )
    assert rendered == "port=5555"
    assert resolved == {"LLM_PORT": "5555"}


def test_substitute_atlas_os_resolves_to_repo_root() -> None:
    rendered, resolved, unresolved = _skills.substitute_placeholders(
        "repo={{ATLAS_OS}}", {}
    )
    assert "{{ATLAS_OS}}" not in rendered
    assert "ATLAS_OS" in resolved
    assert unresolved == []


# ── skills_install_root ───────────────────────────────────────────────────────
def test_install_root_prefers_explicit_override(tmp_path: Path) -> None:
    root = _skills.skills_install_root({"ATLAS_SKILLS_DIR": str(tmp_path)})
    assert root == tmp_path


def test_install_root_defaults_to_vault_claude_skills(tmp_path: Path) -> None:
    root = _skills.skills_install_root({"VAULT_PATH": str(tmp_path)})
    assert root == tmp_path / ".claude" / "skills"


def test_install_root_none_when_unconfigured() -> None:
    assert _skills.skills_install_root({}) is None


# ── find_skill ────────────────────────────────────────────────────────────────
def test_find_skill_by_slug() -> None:
    skill = _skills.find_skill("vault-lint-report")
    assert skill is not None
    assert skill.slug == "vault-lint-report"


def test_find_skill_unknown_returns_none() -> None:
    assert _skills.find_skill("does-not-exist") is None


# ── install_skill ─────────────────────────────────────────────────────────────
def test_install_skill_writes_and_substitutes(tmp_path: Path) -> None:
    env = {"ATLAS_SKILLS_DIR": str(tmp_path), "USER_EMAIL": "me@example.com"}
    result = _skills.install_skill("atlas-daily-report-email", env=env)

    assert result.dest == tmp_path / "atlas-daily-report-email" / "SKILL.md"
    assert result.dest.is_file()
    assert not result.overwrote

    body = result.dest.read_text(encoding="utf-8")
    assert "me@example.com" in body
    assert "{{USER_EMAIL}}" not in body
    assert "USER_EMAIL" in result.resolved
    # VAULT_PATH wasn't provided, so it stays a placeholder and is flagged.
    assert "VAULT_PATH" in result.unresolved
    assert "{{VAULT_PATH}}" in body


def test_install_skill_refuses_overwrite_without_force(tmp_path: Path) -> None:
    env = {"ATLAS_SKILLS_DIR": str(tmp_path)}
    _skills.install_skill("vault-lint-report", env=env)
    with pytest.raises(_skills.SkillInstallError):
        _skills.install_skill("vault-lint-report", env=env)


def test_install_skill_force_overwrites(tmp_path: Path) -> None:
    env = {"ATLAS_SKILLS_DIR": str(tmp_path)}
    _skills.install_skill("vault-lint-report", env=env)
    result = _skills.install_skill("vault-lint-report", env=env, force=True)
    assert result.overwrote is True


def test_install_skill_unknown_raises(tmp_path: Path) -> None:
    with pytest.raises(_skills.SkillNotFoundError):
        _skills.install_skill("nope", env={"ATLAS_SKILLS_DIR": str(tmp_path)})


def test_install_skill_no_target_raises() -> None:
    with pytest.raises(_skills.SkillInstallError):
        _skills.install_skill("vault-lint-report", env={})


# ── CLI: skills list / show / install ─────────────────────────────────────────
def test_cli_skills_list() -> None:
    result = runner.invoke(app, ["skills", "list"])
    assert result.exit_code == 0
    assert "vault-lint-report" in result.stdout


def test_cli_skills_show() -> None:
    result = runner.invoke(app, ["skills", "show", "vault-lint-report"])
    assert result.exit_code == 0
    assert "name: vault-lint-report" in result.stdout


def test_cli_skills_show_unknown() -> None:
    result = runner.invoke(app, ["skills", "show", "nope"])
    assert result.exit_code == 2
    assert "unknown skill" in result.stdout


def test_cli_skills_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_SKILLS_DIR", str(tmp_path))
    monkeypatch.setenv("USER_EMAIL", "me@example.com")
    result = runner.invoke(app, ["skills", "install", "atlas-daily-report-email"])
    assert result.exit_code == 0
    assert (tmp_path / "atlas-daily-report-email" / "SKILL.md").is_file()
    assert "installed" in result.stdout


def test_cli_skills_install_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_SKILLS_DIR", "/tmp/atlas-skills-test")
    result = runner.invoke(app, ["skills", "install", "nope"])
    assert result.exit_code == 2
    assert "unknown skill" in result.stdout


def test_cli_skills_install_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_SKILLS_DIR", str(tmp_path))
    first = runner.invoke(app, ["skills", "install", "vault-lint-report"])
    assert first.exit_code == 0
    second = runner.invoke(app, ["skills", "install", "vault-lint-report"])
    assert second.exit_code == 1
    assert "already exists" in second.stdout
    forced = runner.invoke(
        app, ["skills", "install", "vault-lint-report", "--force"]
    )
    assert forced.exit_code == 0
