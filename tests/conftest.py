"""
Shared pytest fixtures and import-time setup for the Atlas OS test suite.

The scripts under ``scripts/`` are standalone modules (not an installed
package), and a couple of them read configuration *and* create directories at
import time. To keep the suite hermetic and free of network/env dependencies we,
before any test module is imported:

1. Point ``VAULT_PATH`` / ``RAG_DIR`` at a throwaway temp directory so importing
   ``embed_vault`` / ``build_graph`` never touches the real vault or repo.
2. Put ``scripts/`` on ``sys.path`` so the modules import by their bare names.
3. Inject a stub ``tradingagents`` package so ``trading_briefing`` (which would
   otherwise ``sys.exit`` when the optional dependency is missing) imports
   cleanly without the real third-party package installed.
"""

from __future__ import annotations

import json as _json
import subprocess
import sys
import tempfile
import threading
import types
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

# ── 1. Hermetic vault/RAG locations (set BEFORE importing any script) ──────────
_TMP = Path(tempfile.mkdtemp(prefix="atlas-os-tests-"))
_VAULT = _TMP / "vault"
_VAULT.mkdir(parents=True, exist_ok=True)

import os  # noqa: E402  (import after computing temp paths for clarity)

os.environ["VAULT_PATH"] = str(_VAULT)
os.environ["RAG_DIR"] = str(_TMP / "rag")

# Pin the LLM endpoint hosts so scripts resolve their URLs purely from the
# environment at import time and never probe the network for a live backend
# (the backend auto-detection in atlas_os.backends only runs when *no* endpoint
# is configured). These match the historic defaults, so behaviour is unchanged.
os.environ.setdefault("EMBED_HOST", "localhost")
os.environ.setdefault("LM_STUDIO_HOST", "localhost")

# ── 2. Make the standalone scripts importable by name ──────────────────────────
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


# ── 3. Stub the optional `tradingagents` dependency ────────────────────────────
def _install_tradingagents_stub() -> None:
    if "tradingagents" in sys.modules:
        return

    tradingagents = types.ModuleType("tradingagents")
    graph_pkg = types.ModuleType("tradingagents.graph")
    trading_graph = types.ModuleType("tradingagents.graph.trading_graph")
    default_config = types.ModuleType("tradingagents.default_config")

    class TradingAgentsGraph:  # minimal stand-in
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._args = args
            self._kwargs = kwargs

        def propagate(self, ticker: str, date: str) -> tuple[object, str]:
            return ({}, "HOLD")

    trading_graph.TradingAgentsGraph = TradingAgentsGraph  # type: ignore[attr-defined]
    default_config.DEFAULT_CONFIG = {  # type: ignore[attr-defined]
        "llm_provider": "openai",
        "backend_url": "",
        "deep_think_llm": "",
        "quick_think_llm": "",
    }

    sys.modules["tradingagents"] = tradingagents
    sys.modules["tradingagents.graph"] = graph_pkg
    sys.modules["tradingagents.graph.trading_graph"] = trading_graph
    sys.modules["tradingagents.default_config"] = default_config


_install_tradingagents_stub()


# ──────────────────────────────────────────────────────────────────────────────
# Integration-test fixtures
#
# These power the end-to-end suite (``tests/test_integration.py``), which drives
# the real ``atlas`` CLI through Typer's ``CliRunner``. Commands that wrap a
# pipeline script genuinely shell out to a subprocess, so the only way to inject
# test config is via the environment — every fixture below sets env vars (which
# the child process inherits) rather than monkeypatching internals.
# ──────────────────────────────────────────────────────────────────────────────

# A small, realistic vault: a handful of short markdown notes across the folders
# the RAG pipeline knows about. Each file is well under one chunk (≈2 000 chars),
# so the embed step produces exactly one vector per file — making the expected
# vector count predictable.
_SAMPLE_VAULT_FILES: dict[str, str] = {
    "research/kelly-criterion.md": (
        "---\ntags: [trading, research]\n---\n"
        "# Kelly Criterion\n\nOptimal bet sizing for the crypto trading bot.\n"
    ),
    "wiki/index.md": (
        "---\ntags: [wiki]\n---\n# Wiki Index\n\nEntry point for the knowledge base.\n"
    ),
    "projects/atlas-os.md": (
        "---\ntags: [project]\n---\n"
        "# Atlas OS\n\nA local-first personal AI operating system.\n"
    ),
    "memory/decisions.md": (
        "---\ntags: [memory]\n---\n# Decisions\n\nUse uv for package management.\n"
    ),
}

# Number of markdown files in the sample vault → expected vector count after embed.
SAMPLE_VAULT_MD_COUNT = len(_SAMPLE_VAULT_FILES)


@pytest.fixture()
def sample_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temp vault of sample markdown files and point the env at it.

    Sets ``VAULT_PATH``, ``RAG_DIR``, and ``ATLAS_AUDIT_PATH`` so every command
    (and every subprocess it spawns) reads and writes inside the sandbox.
    Returns the vault root.
    """
    vault = tmp_path / "vault"
    for rel, content in _SAMPLE_VAULT_FILES.items():
        path = vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    (vault / ".rag").mkdir(parents=True, exist_ok=True)
    (vault / ".atlas").mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("RAG_DIR", str(vault / ".rag"))
    monkeypatch.setenv("ATLAS_AUDIT_PATH", str(vault / ".atlas" / "audit.jsonl"))
    return vault


@pytest.fixture()
def git_vault(sample_vault: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A :func:`sample_vault` that is an initialised git repo with one commit.

    Pins the git author/committer identity through the environment so commits
    succeed hermetically regardless of the machine's global git config.
    """
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(var, "Atlas Test")
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(var, "atlas-test@example.com")

    subprocess.run(["git", "init", "-q"], cwd=sample_vault, check=True)
    subprocess.run(["git", "add", "-A"], cwd=sample_vault, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "Initial vault commit"],
        cwd=sample_vault,
        check=True,
    )
    return sample_vault


def _make_llm_handler(models: tuple[str, ...]) -> type[BaseHTTPRequestHandler]:
    """Build a request handler that speaks a minimal OpenAI-compatible API."""

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server naming
            # /v1/models — advertise the configured model ids.
            self._send({"data": [{"id": name} for name in models]})

        def do_POST(self) -> None:  # noqa: N802 - http.server naming
            length = int(self.headers.get("Content-Length", "0"))
            body = _json.loads(self.rfile.read(length) or b"{}")
            if "messages" in body:  # /v1/chat/completions
                self._send({"choices": [{"message": {"content": "pong"}}]})
                return
            # /v1/embeddings — one deterministic vector per input string.
            inputs = body.get("input") or []
            if isinstance(inputs, str):
                inputs = [inputs]
            data = [
                {"index": i, "embedding": [round((len(text) % 7) / 7.0, 4), 0.1, 0.2]}
                for i, text in enumerate(inputs)
            ]
            self._send({"data": data})

        def _send(self, obj: object) -> None:
            payload = _json.dumps(obj).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return  # silence the access log

    return _Handler


@pytest.fixture()
def llm_server() -> Iterator[Callable[..., str]]:
    """Factory that spins up real local OpenAI-compatible mock servers.

    Each call returns the base URL (``http://127.0.0.1:<port>``) of a fresh
    background HTTP server that answers ``/v1/models``, ``/v1/embeddings``, and
    ``/v1/chat/completions``. Multiple servers can be started in one test (e.g.
    to mimic LM Studio *and* Ollama running side by side). All are shut down on
    teardown.
    """
    servers: list[HTTPServer] = []

    def _start(models: tuple[str, ...] = ("fake-model",)) -> str:
        server = HTTPServer(("127.0.0.1", 0), _make_llm_handler(models))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    try:
        yield _start
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
