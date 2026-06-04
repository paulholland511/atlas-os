"""Tests for the skills marketplace — registry, search, publish, dependencies.

Hermetic: registry config is redirected to a temp directory via
``ATLAS_REGISTRIES_PATH``; packaging writes to ``tmp_path``; the built-in
registry is read from the live repo's ``skills/registry.json``. No network.
"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from atlas_os import marketplace
from atlas_os.cli import app

runner = CliRunner()


# ── helpers ────────────────────────────────────────────────────────────────--
def _write_skill(
    folder: Path,
    *,
    name: str = "demo-skill",
    version: str = "1.0.0",
    extra_frontmatter: str = "",
    body: str = "Do the thing.",
) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    fm = f"name: {name}\nversion: {version}\ndescription: A demo skill for tests.\n"
    if extra_frontmatter:
        fm += extra_frontmatter
    (folder / "SKILL.md").write_text(f"---\n{fm}---\n\n{body}\n", encoding="utf-8")
    return folder


def _registry_doc(*skills: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "Test Registry",
        "description": "fixture",
        "skills": list(skills),
    }


# ── RegistryEntry ──────────────────────────────────────────────────────────--
def test_entry_from_dict_fills_defaults() -> None:
    entry = marketplace.RegistryEntry.from_dict({"name": "x", "description": "d"})
    assert entry.name == "x"
    assert entry.version == "0.0.0"
    assert entry.author == "unknown"
    assert entry.tags == ()
    assert entry.dependencies == ()


def test_entry_from_dict_requires_name() -> None:
    with pytest.raises(marketplace.RegistryError):
        marketplace.RegistryEntry.from_dict({"description": "no name"})


def test_entry_matches_name_description_and_tags() -> None:
    entry = marketplace.RegistryEntry(
        name="vault-lint", version="1.0.0", description="finds orphans",
        author="a", tags=("maintenance",),
    )
    assert entry.matches("lint")
    assert entry.matches("ORPHAN")
    assert entry.matches("maintenance")
    assert entry.matches("")  # empty query matches everything
    assert not entry.matches("trading")


# ── SkillRegistry parsing ────────────────────────────────────────────────────
def test_registry_from_dict_parses_entries() -> None:
    doc = _registry_doc(
        {"name": "a", "description": "first", "tags": ["x"]},
        {"name": "b", "description": "second"},
    )
    reg = marketplace.SkillRegistry.from_dict(doc, source="mem")
    assert reg.name == "Test Registry"
    assert [e.name for e in reg.entries] == ["a", "b"]


def test_registry_rejects_future_schema_version() -> None:
    with pytest.raises(marketplace.RegistryError):
        marketplace.SkillRegistry.from_dict(
            {"schema_version": 999, "skills": []}, source="mem"
        )


def test_registry_rejects_non_list_skills() -> None:
    with pytest.raises(marketplace.RegistryError):
        marketplace.SkillRegistry.from_dict({"skills": {}}, source="mem")


def test_registry_from_file_bad_json_raises(tmp_path: Path) -> None:
    bad = tmp_path / "registry.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(marketplace.RegistryError):
        marketplace.SkillRegistry.from_file(bad)


def test_registry_search_sorted_and_find() -> None:
    doc = _registry_doc(
        {"name": "zeta", "description": "trade"},
        {"name": "alpha", "description": "trade"},
    )
    reg = marketplace.SkillRegistry.from_dict(doc, source="mem")
    assert [e.name for e in reg.search("trade")] == ["alpha", "zeta"]
    assert reg.find("alpha") is not None
    assert reg.find("missing") is None


# ── dependency resolution ────────────────────────────────────────────────────
def test_resolve_dependencies_orders_deps_first() -> None:
    doc = _registry_doc(
        {"name": "app", "description": "d", "dependencies": ["lib", "util"]},
        {"name": "lib", "description": "d", "dependencies": ["util"]},
        {"name": "util", "description": "d"},
    )
    reg = marketplace.SkillRegistry.from_dict(doc, source="mem")
    order = reg.resolve_dependencies("app")
    assert order[-1] == "app"
    assert order.index("util") < order.index("lib") < order.index("app")
    assert sorted(order) == ["app", "lib", "util"]


def test_resolve_dependencies_missing_raises() -> None:
    doc = _registry_doc({"name": "app", "description": "d", "dependencies": ["ghost"]})
    reg = marketplace.SkillRegistry.from_dict(doc, source="mem")
    with pytest.raises(marketplace.DependencyError):
        reg.resolve_dependencies("app")


def test_resolve_dependencies_detects_cycle() -> None:
    doc = _registry_doc(
        {"name": "a", "description": "d", "dependencies": ["b"]},
        {"name": "b", "description": "d", "dependencies": ["a"]},
    )
    reg = marketplace.SkillRegistry.from_dict(doc, source="mem")
    with pytest.raises(marketplace.DependencyError):
        reg.resolve_dependencies("a")


# ── registries config (add / list / load) ────────────────────────────────────
def test_load_sources_defaults_to_builtin_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ATLAS_REGISTRIES_PATH", str(tmp_path / "regs.json"))
    assert marketplace.load_registry_sources() == [marketplace.DEFAULT_REGISTRY]


def test_add_registry_persists_and_dedupes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "regs.json"
    monkeypatch.setenv("ATLAS_REGISTRIES_PATH", str(cfg))
    marketplace.add_registry("https://example.com/registry.json")
    again = marketplace.add_registry("https://example.com/registry.json")
    assert again == [marketplace.DEFAULT_REGISTRY, "https://example.com/registry.json"]
    saved = json.loads(cfg.read_text(encoding="utf-8"))
    assert saved["registries"] == ["https://example.com/registry.json"]


def test_add_registry_rejects_builtin_sentinel(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ATLAS_REGISTRIES_PATH", str(tmp_path / "regs.json"))
    with pytest.raises(marketplace.RegistryError):
        marketplace.add_registry(marketplace.DEFAULT_REGISTRY)


def test_resolve_registry_source_dispatch() -> None:
    assert isinstance(marketplace.resolve_registry_source(marketplace.DEFAULT_REGISTRY), Path)
    assert marketplace.resolve_registry_source("https://x/r.json") == "https://x/r.json"
    assert isinstance(marketplace.resolve_registry_source("./local.json"), Path)


def test_search_registries_includes_builtin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ATLAS_REGISTRIES_PATH", str(tmp_path / "regs.json"))
    hits, loads = marketplace.search_registries("vault")
    assert all(load.error is None for load in loads)
    assert any(h.entry.name == "vault-lint-report" for h in hits)


def test_search_registries_records_bad_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "regs.json"
    cfg.write_text(json.dumps({"registries": [str(tmp_path / "nope.json")]}), encoding="utf-8")
    monkeypatch.setenv("ATLAS_REGISTRIES_PATH", str(cfg))
    _, loads = marketplace.search_registries("anything")
    assert any(load.error is not None for load in loads)


# ── validation ────────────────────────────────────────────────────────────--
def test_validate_skill_ok(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path / "demo-skill", extra_frontmatter="tags:\n  - demo\nauthor: me\n")
    manifest = marketplace.validate_skill(folder)
    assert manifest.name == "demo-skill"
    assert manifest.version == "1.0.0"
    assert manifest.tags == ("demo",)
    assert manifest.author == "me"


def test_validate_skill_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(marketplace.SkillValidationError):
        marketplace.validate_skill(tmp_path / "ghost")


def test_validate_skill_no_skill_md(tmp_path: Path) -> None:
    folder = tmp_path / "empty"
    folder.mkdir()
    with pytest.raises(marketplace.SkillValidationError):
        marketplace.validate_skill(folder)


def test_validate_skill_collects_all_problems(tmp_path: Path) -> None:
    folder = tmp_path / "bad"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\nname: Bad_Name\nversion: not-semver\ntags: hello\n---\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(marketplace.SkillValidationError) as excinfo:
        marketplace.validate_skill(folder)
    problems = excinfo.value.problems
    assert any("description" in p for p in problems)
    assert any("slug" in p for p in problems)
    assert any("semver" in p for p in problems)
    assert any("tags" in p for p in problems)


def test_validate_skill_no_frontmatter(tmp_path: Path) -> None:
    folder = tmp_path / "plain"
    folder.mkdir()
    (folder / "SKILL.md").write_text("just text, no frontmatter\n", encoding="utf-8")
    with pytest.raises(marketplace.SkillValidationError):
        marketplace.validate_skill(folder)


# ── packaging ────────────────────────────────────────────────────────────────
def test_package_skill_creates_tarball_with_manifest(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path / "demo-skill")
    (folder / "extra.txt").write_text("sidecar", encoding="utf-8")
    out = tmp_path / "dist"
    result = marketplace.package_skill(folder, out)

    assert result.archive == out / "demo-skill-1.0.0.tar.gz"
    assert result.archive.is_file()
    with tarfile.open(result.archive, "r:gz") as tar:
        names = set(tar.getnames())
        assert "demo-skill/manifest.json" in names
        assert "demo-skill/SKILL.md" in names
        assert "demo-skill/extra.txt" in names
        manifest_member = tar.extractfile("demo-skill/manifest.json")
        assert manifest_member is not None
        manifest = json.loads(manifest_member.read())
    assert manifest["name"] == "demo-skill"
    assert manifest["schema_version"] == marketplace.SCHEMA_VERSION


def test_package_skill_excludes_cruft(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path / "demo-skill")
    (folder / ".DS_Store").write_text("junk", encoding="utf-8")
    result = marketplace.package_skill(folder, tmp_path / "dist")
    with tarfile.open(result.archive, "r:gz") as tar:
        assert not any(".DS_Store" in n for n in tar.getnames())


def test_package_skill_invalid_raises(tmp_path: Path) -> None:
    folder = tmp_path / "bad"
    folder.mkdir()
    (folder / "SKILL.md").write_text("---\nname: x\n---\nno description\n", encoding="utf-8")
    with pytest.raises(marketplace.SkillValidationError):
        marketplace.package_skill(folder, tmp_path / "dist")


# ── manifest projection ──────────────────────────────────────────────────────
def test_manifest_to_registry_entry_roundtrip() -> None:
    manifest = marketplace.SkillManifest(
        name="x", version="2.1.0", description="d", author="me",
        tags=("a", "b"), dependencies=("dep",),
    )
    entry = manifest.to_registry_entry(download_url="https://x/dl")
    assert entry.name == "x"
    assert entry.download_url == "https://x/dl"
    assert entry.tags == ("a", "b")
    assert entry.dependencies == ("dep",)


# ── built-in registry invariant ──────────────────────────────────────────────
def test_builtin_registry_entries_all_resolve_to_real_skills() -> None:
    # The key invariant: every registry.json entry names a real shipped skill.
    assert marketplace.validate_builtin_registry() == []


def test_builtin_registry_is_well_formed() -> None:
    reg = marketplace.SkillRegistry.from_file(marketplace.builtin_registry_path())
    assert reg.entries
    for entry in reg.entries:
        assert entry.name
        assert entry.description
        assert entry.version
        assert entry.author == "Atlas OS"


# ── CLI ────────────────────────────────────────────────────────────────────--
def test_cli_skills_search_builtin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ATLAS_REGISTRIES_PATH", str(tmp_path / "regs.json"))
    result = runner.invoke(app, ["skills", "search", "trading"])
    assert result.exit_code == 0
    assert "daily-trading-report" in result.stdout


def test_cli_skills_search_no_match(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ATLAS_REGISTRIES_PATH", str(tmp_path / "regs.json"))
    result = runner.invoke(app, ["skills", "search", "zzzznotaskill"])
    assert result.exit_code == 0
    assert "no skills match" in result.stdout


def test_cli_skills_publish(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path / "demo-skill")
    out = tmp_path / "dist"
    result = runner.invoke(app, ["skills", "publish", str(folder), "--output", str(out)])
    assert result.exit_code == 0
    assert "packaged demo-skill" in result.stdout
    assert (out / "demo-skill-1.0.0.tar.gz").is_file()


def test_cli_skills_publish_invalid(tmp_path: Path) -> None:
    folder = tmp_path / "bad"
    folder.mkdir()
    (folder / "SKILL.md").write_text("---\nname: x\n---\nbody\n", encoding="utf-8")
    result = runner.invoke(app, ["skills", "publish", str(folder)])
    assert result.exit_code == 1
    assert "validation failed" in result.stdout


def test_cli_registry_add_and_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ATLAS_REGISTRIES_PATH", str(tmp_path / "regs.json"))
    add = runner.invoke(app, ["skills", "registry", "add", "https://example.com/r.json"])
    assert add.exit_code == 0
    assert "added registry" in add.stdout

    listing = runner.invoke(app, ["skills", "registry", "list"])
    assert listing.exit_code == 0
    assert "built-in" in listing.stdout


def test_cli_registry_list_builtin_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ATLAS_REGISTRIES_PATH", str(tmp_path / "regs.json"))
    result = runner.invoke(app, ["skills", "registry", "list"])
    assert result.exit_code == 0
    assert "Atlas OS Built-in Skills" in result.stdout
