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

import sys
import tempfile
import types
from pathlib import Path

# ── 1. Hermetic vault/RAG locations (set BEFORE importing any script) ──────────
_TMP = Path(tempfile.mkdtemp(prefix="atlas-os-tests-"))
_VAULT = _TMP / "vault"
_VAULT.mkdir(parents=True, exist_ok=True)

import os  # noqa: E402  (import after computing temp paths for clarity)

os.environ["VAULT_PATH"] = str(_VAULT)
os.environ["RAG_DIR"] = str(_TMP / "rag")

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
