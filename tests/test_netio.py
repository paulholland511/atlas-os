"""Tests for atlas_os.netio — timeouts, retries, and clear network errors."""

from __future__ import annotations

import pytest
import requests

from atlas_os import netio


class _Resp:
    def __init__(self, status_code: int, payload: object | None = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _no_sleep(_: float) -> None:
    return None


class TestLabels:
    def test_endpoint_label_extracts_host_port(self) -> None:
        assert netio.endpoint_label("http://localhost:5555/v1/embeddings") == "localhost:5555"

    def test_unreachable_message_names_service_and_host(self) -> None:
        msg = netio.unreachable_message("http://localhost:5555/v1", "Embeddings endpoint")
        assert "Embeddings endpoint at localhost:5555 is not responding" in msg
        assert "Check that the server is running" in msg


class TestRequest:
    def test_get_json_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            netio.requests, "request", lambda *a, **k: _Resp(200, {"data": [1, 2]})
        )
        out = netio.get_json("http://x/v1/models", sleep=_no_sleep)
        assert out == {"data": [1, 2]}

    def test_post_json_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, object] = {}

        def fake_request(method, url, **kwargs):  # noqa: ANN001, ANN002
            captured["method"] = method
            captured["json"] = kwargs.get("json")
            captured["timeout"] = kwargs.get("timeout")
            return _Resp(200, {"ok": True})

        monkeypatch.setattr(netio.requests, "request", fake_request)
        out = netio.post_json("http://x/v1/embeddings", {"input": "hi"}, sleep=_no_sleep)
        assert out == {"ok": True}
        assert captured["method"] == "POST"
        assert captured["json"] == {"input": "hi"}
        assert captured["timeout"] == netio.DEFAULT_TIMEOUT

    def test_retries_on_503_then_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seq = [_Resp(503), _Resp(503), _Resp(200, {"ok": 1})]

        def fake_request(*a, **k):  # noqa: ANN002, ANN003
            return seq.pop(0)

        monkeypatch.setattr(netio.requests, "request", fake_request)
        out = netio.get_json("http://x/v1/models", sleep=_no_sleep)
        assert out == {"ok": 1}
        assert seq == []  # all three consumed

    def test_connection_error_becomes_endpoint_unreachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*a, **k):  # noqa: ANN002, ANN003
            raise requests.exceptions.ConnectionError("refused")

        monkeypatch.setattr(netio.requests, "request", boom)
        with pytest.raises(netio.EndpointUnreachable) as exc:
            netio.get_json("http://localhost:5555/v1/models", service="LM Studio", sleep=_no_sleep)
        assert "LM Studio at localhost:5555 is not responding" in str(exc.value)
        assert exc.value.url == "http://localhost:5555/v1/models"

    def test_persistent_5xx_becomes_status_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(netio.requests, "request", lambda *a, **k: _Resp(500))
        with pytest.raises(netio.HTTPStatusError) as exc:
            netio.get_json("http://x/v1/models", sleep=_no_sleep)
        assert exc.value.status_code == 500

    def test_4xx_is_not_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = []

        def fake_request(*a, **k):  # noqa: ANN002, ANN003
            calls.append(1)
            return _Resp(404)

        monkeypatch.setattr(netio.requests, "request", fake_request)
        with pytest.raises(netio.HTTPStatusError) as exc:
            netio.get_json("http://x/v1/models", sleep=_no_sleep)
        assert exc.value.status_code == 404
        assert len(calls) == 1  # 404 is final, not retried

    def test_non_json_body_raises_status_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(netio.requests, "request", lambda *a, **k: _Resp(200, None))
        with pytest.raises(netio.HTTPStatusError, match="non-JSON"):
            netio.get_json("http://x/v1/models", sleep=_no_sleep)


class TestIsReachable:
    def test_true_for_2xx(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(netio.requests, "get", lambda *a, **k: _Resp(200))
        assert netio.is_reachable("http://x/") is True

    def test_false_on_connection_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*a, **k):  # noqa: ANN002, ANN003
            raise requests.exceptions.ConnectionError("down")

        monkeypatch.setattr(netio.requests, "get", boom)
        assert netio.is_reachable("http://x/") is False

    def test_false_on_5xx(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(netio.requests, "get", lambda *a, **k: _Resp(503))
        assert netio.is_reachable("http://x/") is False
