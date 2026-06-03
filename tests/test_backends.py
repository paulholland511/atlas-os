"""Tests for the pluggable LLM backend module.

All network access is mocked — ``requests.get`` (probing ``/v1/models``) and
``requests.post`` (the inference test) are monkeypatched, so these tests never
touch a real endpoint.
"""

from __future__ import annotations

import pytest
import requests
from typer.testing import CliRunner

from atlas_os import backends
from atlas_os.cli import app

runner = CliRunner()


# ── Fakes ─────────────────────────────────────────────────────────────────────
class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: object = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {"data": [{"id": "model-x"}]}
        self.text = text

    def json(self) -> object:
        return self._payload


def _get_returning(reachable_ports: set[str], payload: object = None):
    """Build a fake ``requests.get`` reachable only for the given ports."""

    def fake_get(url: str, timeout: float | None = None) -> _FakeResponse:
        if any(f":{port}" in url for port in reachable_ports):
            return _FakeResponse(200, payload)
        raise requests.RequestException("connection refused")

    return fake_get


def _all_unreachable(url: str, timeout: float | None = None) -> _FakeResponse:
    raise requests.RequestException("connection refused")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start each test from a known, override-free environment."""
    for var in (
        "ATLAS_LLM_BACKEND", "ATLAS_LLM_MODEL", "ATLAS_LLM_API_KEY",
        "LM_STUDIO_URL", "LM_STUDIO_ENDPOINT", "LM_STUDIO_HOST", "LM_STUDIO_PORT",
        "LM_STUDIO_MODEL", "OLLAMA_URL", "LLAMACPP_URL", "OPENAI_COMPATIBLE_URL",
        "OPENAI_BASE_URL", "OPENAI_API_KEY", "EMBED_API_KEY", "EMBED_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)


# ── Base-URL resolution ───────────────────────────────────────────────────────
def test_default_base_urls() -> None:
    assert backends.get_backend("lmstudio").base_url == "http://localhost:5555"
    assert backends.get_backend("ollama").base_url == "http://localhost:11434"
    assert backends.get_backend("llamacpp").base_url == "http://localhost:8080"


def test_openai_compatible_requires_url() -> None:
    with pytest.raises(backends.BackendError):
        backends.get_backend("openai-compatible")


def test_openai_compatible_configured_when_url_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_COMPATIBLE_URL", "http://box:9000/v1")
    backend = backends.get_backend("openai-compatible")
    assert backend.base_url == "http://box:9000"  # /v1 suffix stripped
    assert backend.chat_url == "http://box:9000/v1/chat/completions"
    names = [b.name for b in backends.configured_backends()]
    assert "openai-compatible" in names


def test_unknown_backend_name_raises() -> None:
    with pytest.raises(backends.BackendError):
        backends.get_backend("not-a-backend")


def test_backend_name_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    assert backends.get_backend("lm-studio").name == "lmstudio"
    assert backends.get_backend("llama.cpp").name == "llamacpp"
    # The "openai" alias maps to openai-compatible, which still needs a URL.
    monkeypatch.setenv("OPENAI_COMPATIBLE_URL", "http://box:9000")
    assert backends.get_backend("openai").name == "openai-compatible"


# ── Backward compatibility with the original LM Studio config ─────────────────
def test_lm_studio_url_backward_compat(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pre-existing LM_STUDIO_URL drives the lmstudio backend unchanged."""
    monkeypatch.setenv("LM_STUDIO_URL", "http://legacy-host:1234/v1")
    backend = backends.get_backend("lmstudio")
    assert backend.base_url == "http://legacy-host:1234"
    assert backend.embeddings_url == "http://legacy-host:1234/v1/embeddings"


def test_lm_studio_host_port_backward_compat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LM_STUDIO_HOST", "10.0.0.5")
    monkeypatch.setenv("LM_STUDIO_PORT", "7777")
    assert backends.get_backend("lmstudio").base_url == "http://10.0.0.5:7777"


# ── Detection & fallback ──────────────────────────────────────────────────────
def test_detect_returns_first_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backends.requests, "get", _get_returning({"5555"}))
    backend = backends.detect_backend()
    assert backend is not None
    assert backend.name == "lmstudio"


def test_detect_falls_back_to_next_when_primary_down(monkeypatch: pytest.MonkeyPatch) -> None:
    # LM Studio (5555) down, Ollama (11434) up → detection skips to Ollama.
    monkeypatch.setattr(backends.requests, "get", _get_returning({"11434"}))
    backend = backends.detect_backend()
    assert backend is not None
    assert backend.name == "ollama"


def test_detect_returns_none_when_all_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backends.requests, "get", _all_unreachable)
    assert backends.detect_backend() is None


# ── Forced backend selection ──────────────────────────────────────────────────
def test_forced_backend_skips_probing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_LLM_BACKEND", "ollama")
    # Even though nothing is reachable, the forced backend is returned.
    monkeypatch.setattr(backends.requests, "get", _all_unreachable)
    backend = backends.detect_backend()
    assert backend is not None
    assert backend.name == "ollama"


def test_forced_backend_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_LLM_BACKEND", "LM-Studio")
    assert backends.forced_backend_name() == "lmstudio"


def test_forced_unknown_backend_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_LLM_BACKEND", "bogus")
    with pytest.raises(backends.BackendError):
        backends.forced_backend_name()


# ── get_client ────────────────────────────────────────────────────────────────
def test_get_client_uses_detected_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backends.requests, "get", _get_returning({"5555"}))
    client = backends.get_client()
    assert client.backend.name == "lmstudio"
    assert client.model == backends.DEFAULT_CHAT_MODEL
    assert client.chat_url == "http://localhost:5555/v1/chat/completions"


def test_get_client_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_LLM_MODEL", "qwen2.5")
    monkeypatch.setattr(backends.requests, "get", _get_returning({"5555"}))
    assert backends.get_client().model == "qwen2.5"


def test_get_client_legacy_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """LM_STUDIO_MODEL still supplies the chat model when ATLAS_LLM_MODEL is unset."""
    monkeypatch.setenv("LM_STUDIO_MODEL", "legacy-model")
    monkeypatch.setattr(backends.requests, "get", _get_returning({"5555"}))
    assert backends.get_client().model == "legacy-model"


def test_get_client_raises_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backends.requests, "get", _all_unreachable)
    with pytest.raises(backends.BackendUnavailable):
        backends.get_client()


def test_get_client_explicit_name(monkeypatch: pytest.MonkeyPatch) -> None:
    # No probing for an explicitly named backend.
    monkeypatch.setattr(backends.requests, "get", _all_unreachable)
    client = backends.get_client("ollama")
    assert client.backend.name == "ollama"


def test_api_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBED_API_KEY", "secret-token")
    monkeypatch.setattr(backends.requests, "get", _get_returning({"5555"}))
    client = backends.get_client()
    assert client.api_key == "secret-token"
    assert client.headers()["Authorization"] == "Bearer secret-token"


# ── list_models ───────────────────────────────────────────────────────────────
def test_list_models_parses_openai_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"data": [{"id": "alpha"}, {"id": "beta"}]}
    monkeypatch.setattr(backends.requests, "get", _get_returning({"5555"}, payload))
    assert backends.list_models("lmstudio") == ["alpha", "beta"]


def test_list_models_empty_when_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backends.requests, "get", _all_unreachable)
    assert backends.list_models() == []


# ── Inference test ────────────────────────────────────────────────────────────
def test_run_inference_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backends.requests, "get", _get_returning({"5555"}))
    client = backends.get_client()

    def fake_post(url: str, headers: dict, json: dict, timeout: float) -> _FakeResponse:
        assert url == "http://localhost:5555/v1/chat/completions"
        assert json["model"] == client.model
        return _FakeResponse(200, {"choices": [{"message": {"content": "pong"}}]})

    monkeypatch.setattr(backends.requests, "post", fake_post)
    result = backends.run_inference(client)
    assert result.ok is True
    assert result.content == "pong"


def test_run_inference_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backends.requests, "get", _get_returning({"5555"}))
    client = backends.get_client()

    def fake_post(url: str, headers: dict, json: dict, timeout: float) -> _FakeResponse:
        return _FakeResponse(500, text="internal error")

    monkeypatch.setattr(backends.requests, "post", fake_post)
    result = backends.run_inference(client)
    assert result.ok is False
    assert "HTTP 500" in (result.error or "")


# ── CLI integration ───────────────────────────────────────────────────────────
def test_cli_backends_help() -> None:
    result = runner.invoke(app, ["backends", "--help"])
    assert result.exit_code == 0


def test_cli_backends_list(monkeypatch: pytest.MonkeyPatch) -> None:
    from atlas_os import backends as cli_backends

    monkeypatch.setattr(cli_backends.requests, "get", _get_returning({"11434"}))
    result = runner.invoke(app, ["backends"])
    assert result.exit_code == 0
    assert "active backend: ollama" in result.stdout


def test_cli_backends_test_runs_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    from atlas_os import backends as cli_backends

    monkeypatch.setattr(cli_backends.requests, "get", _get_returning({"5555"}))

    def fake_post(url: str, headers: dict, json: dict, timeout: float) -> _FakeResponse:
        return _FakeResponse(200, {"choices": [{"message": {"content": "pong"}}]})

    monkeypatch.setattr(cli_backends.requests, "post", fake_post)
    result = runner.invoke(app, ["backends", "test"])
    assert result.exit_code == 0
    assert "inference OK" in result.stdout
