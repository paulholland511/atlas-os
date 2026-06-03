"""Tests for atlas_os.scriptkit — exit codes, structured errors, error_boundary."""

from __future__ import annotations

import json

import pytest

from atlas_os import fileio, gitutil, netio, scriptkit


class TestEmitError:
    def test_human_output_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = scriptkit.emit_error("boom")
        captured = capsys.readouterr()
        assert code == scriptkit.EXIT_ERROR
        assert "ERROR: boom" in captured.err
        assert captured.out == ""

    def test_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = scriptkit.emit_error("boom", json_mode=True, code=2, detail="x")
        payload = json.loads(capsys.readouterr().err)
        assert code == 2
        assert payload == {"status": "error", "error": "boom", "detail": "x"}


class TestFail:
    def test_raises_system_exit_with_code(self) -> None:
        with pytest.raises(SystemExit) as exc:
            scriptkit.fail("nope", code=scriptkit.EXIT_CONFIG)
        assert exc.value.code == scriptkit.EXIT_CONFIG


class TestEmitWarning:
    def test_human_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        scriptkit.emit_warning("skipping email")
        assert "WARNING: skipping email" in capsys.readouterr().err

    def test_json_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        scriptkit.emit_warning("skip", json_mode=True)
        assert json.loads(capsys.readouterr().err)["warning"] == "skip"


class TestJsonModeRequested:
    def test_detects_flag(self) -> None:
        assert scriptkit.json_mode_requested(["--full", "--json"]) is True

    def test_absent(self) -> None:
        assert scriptkit.json_mode_requested(["--full"]) is False


class TestErrorBoundary:
    def test_clean_block_does_nothing(self) -> None:
        with scriptkit.error_boundary():
            x = 1 + 1
        assert x == 2

    def test_passes_through_system_exit(self) -> None:
        with pytest.raises(SystemExit) as exc:
            with scriptkit.error_boundary():
                raise SystemExit(3)
        assert exc.value.code == 3

    def test_network_error_becomes_exit_1(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            with scriptkit.error_boundary():
                raise netio.EndpointUnreachable("server down", url="http://x")
        assert exc.value.code == scriptkit.EXIT_ERROR
        assert "server down" in capsys.readouterr().err

    def test_fileio_error_is_caught(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit):
            with scriptkit.error_boundary():
                raise fileio.MissingFileError("no file")
        assert "no file" in capsys.readouterr().err

    def test_git_error_is_caught(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit):
            with scriptkit.error_boundary():
                raise gitutil.GitError("lock held")
        assert "lock held" in capsys.readouterr().err

    def test_unexpected_exception_has_no_traceback(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            with scriptkit.error_boundary():
                raise RuntimeError("kaboom")
        assert exc.value.code == scriptkit.EXIT_ERROR
        assert "Unexpected error: kaboom" in capsys.readouterr().err

    def test_json_mode_emits_json_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            with scriptkit.error_boundary(json_mode=True):
                raise netio.EndpointUnreachable("down", url="http://x")
        assert json.loads(capsys.readouterr().err)["status"] == "error"

    def test_keyboard_interrupt_exits_130(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            with scriptkit.error_boundary():
                raise KeyboardInterrupt()
        assert exc.value.code == 130
