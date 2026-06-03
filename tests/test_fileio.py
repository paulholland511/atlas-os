"""Tests for atlas_os.fileio — atomic writes and graceful reads."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas_os import fileio


class TestAtomicWrites:
    def test_write_and_read_text(self, tmp_path: Path) -> None:
        target = tmp_path / "note.txt"
        fileio.atomic_write_text(target, "hello")
        assert target.read_text(encoding="utf-8") == "hello"

    def test_write_json_roundtrip(self, tmp_path: Path) -> None:
        target = tmp_path / "data" / "vectors.json"
        fileio.atomic_write_json(target, {"a": [1, 2, 3]})
        assert fileio.read_json(target) == {"a": [1, 2, 3]}

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "deep" / "nested" / "f.txt"
        fileio.atomic_write_text(target, "x")
        assert target.is_file()

    def test_no_temp_file_left_behind(self, tmp_path: Path) -> None:
        target = tmp_path / "f.json"
        fileio.atomic_write_json(target, [1, 2])
        leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
        assert leftovers == []

    def test_overwrite_is_atomic_replace(self, tmp_path: Path) -> None:
        target = tmp_path / "f.txt"
        fileio.atomic_write_text(target, "first")
        fileio.atomic_write_text(target, "second")
        assert target.read_text(encoding="utf-8") == "second"


class TestReadJson:
    def test_missing_returns_default(self, tmp_path: Path) -> None:
        assert fileio.read_json(tmp_path / "nope.json", default=[]) == []

    def test_missing_without_default_raises(self, tmp_path: Path) -> None:
        with pytest.raises(fileio.MissingFileError):
            fileio.read_json(tmp_path / "nope.json")

    def test_corrupt_returns_default(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        assert fileio.read_json(bad, default=[]) == []

    def test_corrupt_without_default_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid", encoding="utf-8")
        with pytest.raises(fileio.CorruptFileError):
            fileio.read_json(bad)


class TestReadText:
    def test_reads_existing(self, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("content", encoding="utf-8")
        assert fileio.read_text(f) == "content"

    def test_missing_returns_default(self, tmp_path: Path) -> None:
        assert fileio.read_text(tmp_path / "nope.txt", default="") == ""

    def test_missing_without_default_raises(self, tmp_path: Path) -> None:
        with pytest.raises(fileio.MissingFileError):
            fileio.read_text(tmp_path / "nope.txt")


class TestIsDataless:
    def test_normal_file_is_not_dataless(self, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("x", encoding="utf-8")
        assert fileio.is_dataless(f) is False

    def test_missing_file_is_not_dataless(self, tmp_path: Path) -> None:
        assert fileio.is_dataless(tmp_path / "nope") is False
