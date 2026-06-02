"""Tests for scripts/health_check.py — probes, status combination, formatting."""

from __future__ import annotations

import socket
from urllib import error

import health_check


def test_module_imports() -> None:
    assert hasattr(health_check, "run_all")
    assert hasattr(health_check, "combine")


class TestProbePath:
    def test_missing(self, tmp_path) -> None:
        ok, detail = health_check.probe_path(tmp_path / "nope.txt")
        assert ok is False
        assert "missing" in detail

    def test_exists_without_age_check(self, tmp_path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("x")
        ok, detail = health_check.probe_path(f)
        assert ok is True
        assert detail == "exists"

    def test_fresh_within_age_limit(self, tmp_path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("x")
        ok, _ = health_check.probe_path(f, max_age_hours=24)
        assert ok is True


class _FakeHTTPResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class TestProbeHttp:
    def test_status_in_accept_is_up(self, monkeypatch) -> None:
        monkeypatch.setattr(
            health_check.request, "urlopen", lambda req, timeout: _FakeHTTPResponse(200)
        )
        ok, detail = health_check.probe_http("http://x/")
        assert ok is True
        assert detail == "HTTP 200"

    def test_http_error_code_respected(self, monkeypatch) -> None:
        def raise_http(req, timeout):
            raise error.HTTPError("http://x/", 404, "Not Found", {}, None)

        monkeypatch.setattr(health_check.request, "urlopen", raise_http)
        ok, detail = health_check.probe_http("http://x/", accept=range(200, 300))
        assert ok is False
        assert "404" in detail

    def test_unreachable_is_down(self, monkeypatch) -> None:
        def raise_urlerror(req, timeout):
            raise error.URLError(socket.timeout("timed out"))

        monkeypatch.setattr(health_check.request, "urlopen", raise_urlerror)
        ok, detail = health_check.probe_http("http://x/")
        assert ok is False
        assert "unreachable" in detail


class TestCombine:
    def test_all_passing_is_up(self) -> None:
        r = health_check.combine("svc", [("a", True, ""), ("b", True, "")])
        assert r.status == "up"

    def test_none_passing_is_down(self) -> None:
        r = health_check.combine("svc", [("a", False, ""), ("b", False, "")])
        assert r.status == "down"

    def test_partial_is_degraded(self) -> None:
        r = health_check.combine("svc", [("a", True, ""), ("b", False, "")])
        assert r.status == "degraded"
        assert r.detail == "1/2 checks passed"


def test_result_icon_mapping() -> None:
    assert health_check.Result("n", "up").icon == "✅"
    assert health_check.Result("n", "down").icon == "❌"


def test_format_human_includes_summary() -> None:
    results = [
        health_check.combine("Up svc", [("a", True, "ok")]),
        health_check.combine("Down svc", [("a", False, "bad")]),
    ]
    out = health_check.format_human(results)
    assert "Atlas OS Health Check" in out
    assert "Summary: 1 up · 0 degraded · 1 down" in out


def test_check_email_reflects_env_password(monkeypatch) -> None:
    monkeypatch.setenv("SMTP_APP_PASSWORD", "secret")
    result = health_check.check_email()
    pw_check = next(c for c in result.checks if "SMTP_APP_PASSWORD" in c["name"])
    assert pw_check["ok"] is True
