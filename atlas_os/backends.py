"""Pluggable LLM backend detection for Atlas OS.

Atlas OS is local-first: it talks to whatever OpenAI-compatible LLM server you
already run. This module auto-detects which one is up so the scripts and CLI
don't have to hardcode a host, port, or model.

Four backends are supported, all of which expose the OpenAI-compatible API
(``/v1/models``, ``/v1/chat/completions``, ``/v1/embeddings``):

==================  ===========================  ============================
Backend             Default base URL             URL override env var
==================  ===========================  ============================
``lmstudio``        ``http://localhost:5555``    ``LM_STUDIO_URL``
``ollama``          ``http://localhost:11434``   ``OLLAMA_URL``
``llamacpp``        ``http://localhost:8080``    ``LLAMACPP_URL``
``openai-compatible``  (no default — opt-in)     ``OPENAI_COMPATIBLE_URL``
==================  ===========================  ============================

Detection probes the backends in the order above and returns the first that
responds. Two environment variables override the auto-behaviour:

* ``ATLAS_LLM_BACKEND`` — force a backend by name (``lmstudio`` / ``ollama`` /
  ``llamacpp`` / ``openai-compatible``); skips probing entirely.
* ``ATLAS_LLM_MODEL`` — override the chat model name reported to callers.

**Backward compatibility:** the original LM Studio configuration still works
unchanged. ``LM_STUDIO_URL`` (or ``LM_STUDIO_HOST`` + ``LM_STUDIO_PORT``) feeds
the ``lmstudio`` backend, ``LM_STUDIO_MODEL`` supplies the chat model, and
``EMBED_MODEL`` / ``EMBED_API_KEY`` continue to drive embeddings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import requests

# ── Tunables ──────────────────────────────────────────────────────────────────
DEFAULT_PROBE_TIMEOUT = 1.5  # seconds per endpoint when probing
DEFAULT_CHAT_MODEL = "local-model"
DEFAULT_EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"

FORCE_BACKEND_ENV = "ATLAS_LLM_BACKEND"
MODEL_ENV = "ATLAS_LLM_MODEL"


# ── Backend catalogue ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class BackendSpec:
    """Static description of a supported backend.

    ``url_env_vars`` are tried in order; the first set one wins. ``default_base_url``
    is ``None`` for backends that must be opted into explicitly (there is no
    sensible localhost default for an arbitrary OpenAI-compatible server).
    """

    name: str
    label: str
    default_base_url: str | None
    url_env_vars: tuple[str, ...]


# Probe precedence: LM Studio → Ollama → llama.cpp → any OpenAI-compatible server.
BACKEND_SPECS: tuple[BackendSpec, ...] = (
    BackendSpec(
        name="lmstudio",
        label="LM Studio",
        default_base_url="http://localhost:5555",
        url_env_vars=("LM_STUDIO_URL", "LM_STUDIO_ENDPOINT"),
    ),
    BackendSpec(
        name="ollama",
        label="Ollama",
        default_base_url="http://localhost:11434",
        url_env_vars=("OLLAMA_URL",),
    ),
    BackendSpec(
        name="llamacpp",
        label="llama.cpp",
        default_base_url="http://localhost:8080",
        url_env_vars=("LLAMACPP_URL",),
    ),
    BackendSpec(
        name="openai-compatible",
        label="OpenAI-compatible",
        default_base_url=None,
        url_env_vars=("OPENAI_COMPATIBLE_URL", "OPENAI_BASE_URL"),
    ),
)

BACKEND_NAMES: tuple[str, ...] = tuple(s.name for s in BACKEND_SPECS)
_SPECS_BY_NAME: dict[str, BackendSpec] = {s.name: s for s in BACKEND_SPECS}

# Forgiving aliases accepted from ATLAS_LLM_BACKEND / get_client(backend=...).
_NAME_ALIASES: dict[str, str] = {
    "lm-studio": "lmstudio",
    "lm_studio": "lmstudio",
    "lmstudio": "lmstudio",
    "ollama": "ollama",
    "llama-cpp": "llamacpp",
    "llama.cpp": "llamacpp",
    "llama_cpp": "llamacpp",
    "llamacpp": "llamacpp",
    "openai": "openai-compatible",
    "openai-compatible": "openai-compatible",
    "openai_compatible": "openai-compatible",
}


# ── Errors ────────────────────────────────────────────────────────────────────
class BackendError(RuntimeError):
    """A backend was misconfigured or named incorrectly."""


class BackendUnavailable(BackendError):
    """No backend could be reached (and none was forced)."""


# ── Value objects ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Backend:
    """A concrete, resolved backend with a known base URL."""

    name: str
    label: str
    base_url: str  # normalised root, e.g. http://localhost:5555 (no /v1 suffix)

    @property
    def api_base(self) -> str:
        return f"{self.base_url}/v1"

    @property
    def models_url(self) -> str:
        return f"{self.api_base}/models"

    @property
    def chat_url(self) -> str:
        return f"{self.api_base}/chat/completions"

    @property
    def embeddings_url(self) -> str:
        return f"{self.api_base}/embeddings"


@dataclass(frozen=True)
class BackendStatus:
    """The result of probing a backend's ``/v1/models`` endpoint."""

    backend: Backend
    reachable: bool
    models: tuple[str, ...]
    error: str | None


@dataclass(frozen=True)
class Client:
    """A ready-to-use handle: a resolved backend plus model + credential config."""

    backend: Backend
    model: str  # chat/completions model name
    embed_model: str  # embeddings model name
    api_key: str  # "" when the endpoint needs no auth

    # Convenience pass-throughs so callers can use a Client directly.
    @property
    def chat_url(self) -> str:
        return self.backend.chat_url

    @property
    def embeddings_url(self) -> str:
        return self.backend.embeddings_url

    @property
    def models_url(self) -> str:
        return self.backend.models_url

    @property
    def api_base(self) -> str:
        return self.backend.api_base

    def headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h


@dataclass(frozen=True)
class InferenceResult:
    """Outcome of a one-shot chat test against a backend."""

    ok: bool
    content: str
    model: str
    error: str | None


# ── Resolution helpers ────────────────────────────────────────────────────────
def _normalize_base_url(url: str) -> str:
    """Strip whitespace, a trailing slash, and a trailing ``/v1`` segment.

    Callers set the various URL env vars inconsistently — some include ``/v1``
    (``LM_STUDIO_URL``), some don't (``LM_STUDIO_ENDPOINT``). We normalise to the
    bare root and rebuild the ``/v1/...`` paths from there.
    """
    url = url.strip().rstrip("/")
    if url.endswith("/v1"):
        url = url[: -len("/v1")]
    return url


def _resolve_base_url(spec: BackendSpec) -> str | None:
    """Resolve a backend's base URL from the environment, or its default."""
    for var in spec.url_env_vars:
        value = os.environ.get(var)
        if value:
            return _normalize_base_url(value)
    # Backward-compat: the original setup configured LM Studio via host/port.
    if spec.name == "lmstudio":
        host = os.environ.get("LM_STUDIO_HOST")
        port = os.environ.get("LM_STUDIO_PORT")
        if host or port:
            return f"http://{host or 'localhost'}:{port or '5555'}"
    return spec.default_base_url


def _canonical_name(name: str) -> str:
    key = name.strip().lower()
    canonical = _NAME_ALIASES.get(key)
    if canonical is None:
        raise BackendError(
            f"Unknown backend {name!r}; choose from {', '.join(BACKEND_NAMES)}."
        )
    return canonical


def _api_key() -> str:
    """Bearer token, if any. Honours the original ``EMBED_API_KEY`` first."""
    return (
        os.environ.get("ATLAS_LLM_API_KEY")
        or os.environ.get("EMBED_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    )


def _chat_model() -> str:
    """The chat model name. ``ATLAS_LLM_MODEL`` wins, then legacy ``LM_STUDIO_MODEL``."""
    return (
        os.environ.get(MODEL_ENV)
        or os.environ.get("LM_STUDIO_MODEL")
        or DEFAULT_CHAT_MODEL
    )


def _embed_model() -> str:
    return os.environ.get("EMBED_MODEL") or DEFAULT_EMBED_MODEL


def get_backend(name: str) -> Backend:
    """Build a :class:`Backend` for ``name`` (aliases accepted).

    Raises :class:`BackendError` if the name is unknown or the backend has no URL
    configured (only possible for ``openai-compatible``, which has no default).
    """
    canonical = _canonical_name(name)
    spec = _SPECS_BY_NAME[canonical]
    base = _resolve_base_url(spec)
    if base is None:
        raise BackendError(
            f"Backend {canonical!r} has no URL configured — set {spec.url_env_vars[0]}."
        )
    return Backend(name=spec.name, label=spec.label, base_url=base)


def configured_backends() -> list[Backend]:
    """Every backend that has a resolvable base URL, in probe precedence order."""
    out: list[Backend] = []
    for spec in BACKEND_SPECS:
        base = _resolve_base_url(spec)
        if base is not None:
            out.append(Backend(name=spec.name, label=spec.label, base_url=base))
    return out


def forced_backend_name() -> str | None:
    """The backend forced via ``ATLAS_LLM_BACKEND``, or ``None``.

    Raises :class:`BackendError` if the env var names an unknown backend.
    """
    value = os.environ.get(FORCE_BACKEND_ENV)
    if not value or not value.strip():
        return None
    return _canonical_name(value)


# ── Probing ───────────────────────────────────────────────────────────────────
def _parse_models(payload: object) -> tuple[str, ...]:
    """Extract model ids from an OpenAI ``/v1/models`` body (or Ollama's shape)."""
    if not isinstance(payload, dict):
        return ()
    out: list[str] = []
    for item in payload.get("data") or []:  # OpenAI shape: {"data": [{"id": ...}]}
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            out.append(item["id"])
    for item in payload.get("models") or []:  # Ollama native shape, defensively
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            out.append(item["name"])
    return tuple(out)


def probe_backend(
    backend: Backend, timeout: float = DEFAULT_PROBE_TIMEOUT
) -> BackendStatus:
    """GET ``/v1/models`` and report reachability plus any advertised models."""
    try:
        resp = requests.get(backend.models_url, timeout=timeout)
    except requests.RequestException as exc:
        return BackendStatus(backend, False, (), type(exc).__name__)
    if resp.status_code >= 400:
        return BackendStatus(backend, False, (), f"HTTP {resp.status_code}")
    try:
        models = _parse_models(resp.json())
    except ValueError:
        models = ()
    return BackendStatus(backend, True, models, None)


def backend_statuses(
    timeout: float = DEFAULT_PROBE_TIMEOUT,
) -> list[BackendStatus]:
    """Probe every configured backend (for ``atlas backends`` display)."""
    return [probe_backend(b, timeout) for b in configured_backends()]


# ── Detection / client construction ───────────────────────────────────────────
def detect_backend(timeout: float = DEFAULT_PROBE_TIMEOUT) -> Backend | None:
    """Return the active backend.

    If ``ATLAS_LLM_BACKEND`` is set, that backend is returned without probing
    (forcing means "trust me"). Otherwise the configured backends are probed in
    precedence order and the first reachable one is returned, or ``None``.
    """
    forced = forced_backend_name()
    if forced is not None:
        return get_backend(forced)
    for backend in configured_backends():
        if probe_backend(backend, timeout).reachable:
            return backend
    return None


def _resolve(backend: Backend | str | None, timeout: float) -> Backend | None:
    if backend is None:
        return detect_backend(timeout)
    if isinstance(backend, Backend):
        return backend
    return get_backend(backend)


def get_client(
    backend: Backend | str | None = None,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
) -> Client:
    """Return a configured :class:`Client` for the detected or named backend.

    Raises :class:`BackendUnavailable` if ``backend`` is ``None`` and nothing is
    reachable; raises :class:`BackendError` for an unknown explicit backend name.
    """
    resolved = _resolve(backend, timeout)
    if resolved is None:
        hint = f"or set {FORCE_BACKEND_ENV} and the matching *_URL env var."
        raise BackendUnavailable(
            f"No LLM backend reachable. Start LM Studio / Ollama / llama.cpp, {hint}"
        )
    return Client(
        backend=resolved,
        model=_chat_model(),
        embed_model=_embed_model(),
        api_key=_api_key(),
    )


def list_models(
    backend: Backend | str | None = None,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
) -> list[str]:
    """List models advertised by the detected or named backend (``[]`` if down)."""
    resolved = _resolve(backend, timeout)
    if resolved is None:
        return []
    return list(probe_backend(resolved, timeout).models)


# ── Inference test ────────────────────────────────────────────────────────────
def run_inference(
    client: Client,
    prompt: str = "Reply with exactly one word: pong",
    *,
    max_tokens: int = 16,
    timeout: float = 30.0,
) -> InferenceResult:
    """Send a tiny chat completion to verify the backend actually generates."""
    payload = {
        "model": client.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    try:
        resp = requests.post(
            client.chat_url, headers=client.headers(), json=payload, timeout=timeout
        )
    except requests.RequestException as exc:
        return InferenceResult(False, "", client.model, f"{type(exc).__name__}: {exc}")
    if resp.status_code >= 400:
        return InferenceResult(
            False, "", client.model, f"HTTP {resp.status_code}: {resp.text[:200]}"
        )
    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        return InferenceResult(
            False, "", client.model, f"unexpected response shape: {exc}"
        )
    return InferenceResult(True, str(content).strip(), client.model, None)
