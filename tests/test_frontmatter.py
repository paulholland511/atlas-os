"""Tests for atlas_os.frontmatter — the pre-commit YAML validation gate."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas_os import frontmatter


class TestValidateText:
    def test_no_frontmatter_is_valid(self) -> None:
        result = frontmatter.validate_text("# Just a heading\n\nbody")
        assert result.ok
        assert not result.had_frontmatter

    def test_well_formed_frontmatter_passes(self) -> None:
        text = "---\ntitle: Hello\ntags: [a, b]\n---\nbody\n"
        result = frontmatter.validate_text(text)
        assert result.ok
        assert result.had_frontmatter

    def test_broken_yaml_fails(self) -> None:
        text = "---\ntitle: [unclosed\n---\nbody\n"
        result = frontmatter.validate_text(text)
        assert not result.ok
        assert any("YAML" in e for e in result.errors)

    def test_unterminated_block_fails(self) -> None:
        text = "---\ntitle: Hello\nbody with no closing fence\n"
        result = frontmatter.validate_text(text)
        assert not result.ok
        assert any("unterminated" in e for e in result.errors)

    def test_non_mapping_frontmatter_fails(self) -> None:
        text = "---\n- just\n- a\n- list\n---\nbody\n"
        result = frontmatter.validate_text(text)
        assert not result.ok
        assert any("mapping" in e for e in result.errors)

    def test_missing_required_key_fails(self) -> None:
        text = "---\ntitle: Hello\n---\nbody\n"
        result = frontmatter.validate_text(text, required=("id",))
        assert not result.ok
        assert any("required key" in e and "id" in e for e in result.errors)

    def test_present_required_key_passes(self) -> None:
        text = "---\nid: 42\ntitle: Hello\n---\nbody\n"
        result = frontmatter.validate_text(text, required=("id", "title"))
        assert result.ok

    def test_invalid_date_fails(self) -> None:
        text = "---\ndate: not-a-date\n---\nbody\n"
        result = frontmatter.validate_text(text)
        assert not result.ok
        assert any("date" in e for e in result.errors)

    def test_iso_date_string_passes(self) -> None:
        text = "---\ncreated: 2026-06-05T10:00:00\n---\nbody\n"
        assert frontmatter.validate_text(text).ok

    def test_yaml_native_date_passes(self) -> None:
        text = "---\ndate: 2026-06-05\n---\nbody\n"
        assert frontmatter.validate_text(text).ok

    def test_empty_date_value_is_ignored(self) -> None:
        text = "---\ndate:\ntitle: Hello\n---\nbody\n"
        assert frontmatter.validate_text(text).ok


class TestValidateFrontmatterFile:
    def test_valid_file(self, tmp_path: Path) -> None:
        f = tmp_path / "note.md"
        f.write_text("---\ntitle: Hi\n---\nbody\n", encoding="utf-8")
        assert frontmatter.validate_frontmatter(f).ok

    def test_missing_file_fails(self, tmp_path: Path) -> None:
        result = frontmatter.validate_frontmatter(tmp_path / "nope.md")
        assert not result.ok


class TestValidateBeforeCommit:
    def test_explicit_files_mixed(self, tmp_path: Path) -> None:
        good = tmp_path / "good.md"
        good.write_text("---\ntitle: ok\n---\nbody\n", encoding="utf-8")
        bad = tmp_path / "bad.md"
        bad.write_text("---\nbroken: [\n---\nbody\n", encoding="utf-8")

        report = frontmatter.validate_before_commit(tmp_path, files=[good, bad])
        assert not report.ok
        assert len(report.failures) == 1
        assert report.failures[0].file_path == bad

    def test_all_valid_report_ok(self, tmp_path: Path) -> None:
        good = tmp_path / "good.md"
        good.write_text("---\ntitle: ok\n---\nbody\n", encoding="utf-8")
        report = frontmatter.validate_before_commit(tmp_path, files=[good])
        assert report.ok

    def test_reads_staged_markdown_from_git(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
            monkeypatch.setenv(var, "Atlas Test")
        for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
            monkeypatch.setenv(var, "atlas-test@example.com")
        subprocess.run(["git", "init", "-b", "main", str(tmp_path)],
                       check=True, capture_output=True)
        bad = tmp_path / "bad.md"
        bad.write_text("---\ntitle: [oops\n---\nbody\n", encoding="utf-8")
        subprocess.run(["git", "add", "bad.md"], cwd=tmp_path,
                       check=True, capture_output=True)

        report = frontmatter.validate_before_commit(tmp_path)
        assert not report.ok
        assert report.failures[0].file_path.name == "bad.md"
