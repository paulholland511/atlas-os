"""Tests for scripts/vault_commit.py — status parsing, classification, messages."""

from __future__ import annotations

import subprocess

import vault_commit


def test_module_imports() -> None:
    assert hasattr(vault_commit, "git_status")
    assert hasattr(vault_commit, "build_message")


class TestClassifyPaths:
    def test_research_and_config_tags(self) -> None:
        tags = vault_commit.classify_paths(["wiki/a.md", "scripts/b.py"])
        assert tags == ["config", "research"]

    def test_memory_tag(self) -> None:
        assert vault_commit.classify_paths(["memory/note.md"]) == ["memory"]

    def test_unknown_paths_default_to_content(self) -> None:
        assert vault_commit.classify_paths(["random.md"]) == ["content"]


class TestBuildMessage:
    def test_includes_counts_tags_and_timestamp(self) -> None:
        stats = {
            "new": ["wiki/a.md"],
            "modified": ["scripts/b.py"],
            "deleted": ["projects/c.md"],
        }
        msg = vault_commit.build_message(stats)
        assert "1 new" in msg
        assert "1 modified" in msg
        assert "1 deleted" in msg
        assert "config" in msg and "research" in msg and "project" in msg
        assert "Indexed-at:" in msg

    def test_truncates_long_file_lists(self) -> None:
        stats = {"new": [f"wiki/note-{i}.md" for i in range(12)], "modified": [], "deleted": []}
        msg = vault_commit.build_message(stats)
        assert "… and 4 more" in msg


class TestGitStatus:
    def _patch_run(self, monkeypatch, porcelain: str) -> None:
        def fake_run(cmd, *, check=True):
            return subprocess.CompletedProcess(cmd, 0, stdout=porcelain, stderr="")

        monkeypatch.setattr(vault_commit, "run", fake_run)

    def test_categorises_new_modified_deleted(self, monkeypatch) -> None:
        self._patch_run(
            monkeypatch,
            "?? brand_new.md\n M changed.md\n D removed.md\n",
        )
        stats = vault_commit.git_status()
        assert stats["new"] == ["brand_new.md"]
        assert stats["modified"] == ["changed.md"]
        assert stats["deleted"] == ["removed.md"]

    def test_handles_rename_arrow(self, monkeypatch) -> None:
        self._patch_run(monkeypatch, "R  old.md -> new.md\n")
        stats = vault_commit.git_status()
        assert stats["modified"] == ["new.md"]

    def test_clean_tree(self, monkeypatch) -> None:
        self._patch_run(monkeypatch, "")
        stats = vault_commit.git_status()
        assert stats == {"new": [], "modified": [], "deleted": []}
