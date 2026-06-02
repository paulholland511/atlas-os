"""Tests for scripts/vault_changelog.py — git log parsing, aggregation, formatting."""

from __future__ import annotations

import vault_changelog


def test_module_imports() -> None:
    assert hasattr(vault_changelog, "get_commits")
    assert hasattr(vault_changelog, "aggregate")


class TestAggregate:
    def test_deduplicates_across_commits(self) -> None:
        entries = [
            vault_changelog.CommitEntry("h1", "d1", "s1", added=["a.md"], modified=["b.md"]),
            vault_changelog.CommitEntry("h2", "d2", "s2", modified=["a.md"], deleted=["c.md"]),
        ]
        agg = vault_changelog.aggregate(entries)
        # a.md was added then modified → stays in added only, not modified
        assert agg["added"] == ["a.md"]
        assert agg["modified"] == ["b.md"]
        assert agg["deleted"] == ["c.md"]

    def test_deleted_wins_over_added(self) -> None:
        entries = [
            vault_changelog.CommitEntry("h1", "d1", "s1", added=["x.md"]),
            vault_changelog.CommitEntry("h2", "d2", "s2", deleted=["x.md"]),
        ]
        agg = vault_changelog.aggregate(entries)
        assert agg["deleted"] == ["x.md"]
        assert "x.md" not in agg["added"]


class TestGetCommits:
    def test_parses_log_into_entries(self, monkeypatch) -> None:
        log_output = (
            "0123456789012345678901234567890123456789|2026-06-01 10:00:00 +0000|First commit\n"
            "A\tnotes/new.md\n"
            "M\tnotes/changed.md\n"
            "D\tnotes/gone.md\n"
        )
        monkeypatch.setattr(vault_changelog, "run", lambda cmd: log_output)
        entries = vault_changelog.get_commits("24 hours ago")
        assert len(entries) == 1
        e = entries[0]
        assert e.hash == "01234567"
        assert e.subject == "First commit"
        assert e.added == ["notes/new.md"]
        assert e.modified == ["notes/changed.md"]
        assert e.deleted == ["notes/gone.md"]

    def test_empty_log_returns_no_entries(self, monkeypatch) -> None:
        monkeypatch.setattr(vault_changelog, "run", lambda cmd: "")
        assert vault_changelog.get_commits("24 hours ago") == []


class TestFormatting:
    def _fixture(self):
        entries = [vault_changelog.CommitEntry("abc12345", "2026-06-01 10:00:00", "Subject")]
        agg = {"added": ["a.md"], "modified": ["b.md"], "deleted": []}
        return entries, agg

    def test_markdown_has_sections(self) -> None:
        entries, agg = self._fixture()
        out = vault_changelog.format_markdown("24 hours ago", entries, agg)
        assert "## Vault changelog since 24 hours ago" in out
        assert "### Added (1)" in out
        assert "`a.md`" in out
        assert "### Commits" in out

    def test_plain_reports_counts(self) -> None:
        entries, agg = self._fixture()
        out = vault_changelog.format_plain("24 hours ago", entries, agg)
        assert "1 commit(s), 2 file(s) affected" in out
        assert "+ a.md" in out
        assert "~ b.md" in out
