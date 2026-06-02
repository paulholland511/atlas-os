"""Tests for scripts/trading_briefing.py — config, endpoint probe, formatting, saving.

The optional ``tradingagents`` dependency is stubbed in conftest.py so the module
imports cleanly without the real package installed.
"""

from __future__ import annotations

import trading_briefing


def test_module_imports() -> None:
    assert hasattr(trading_briefing, "format_briefing")
    assert hasattr(trading_briefing, "get_trading_config")


def test_get_trading_config_points_at_local_endpoint() -> None:
    config = trading_briefing.get_trading_config()
    assert config["llm_provider"] == "ollama"
    assert config["backend_url"] == trading_briefing.LM_STUDIO_URL
    assert config["data_vendors"]["core_stock_apis"] == "yfinance"


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class TestCheckLmStudio:
    def test_available(self, monkeypatch) -> None:
        monkeypatch.setattr(
            trading_briefing.requests, "get", lambda url, timeout: _FakeResponse(200)
        )
        assert trading_briefing.check_lm_studio() is True

    def test_non_200_is_unavailable(self, monkeypatch) -> None:
        monkeypatch.setattr(
            trading_briefing.requests, "get", lambda url, timeout: _FakeResponse(503)
        )
        assert trading_briefing.check_lm_studio() is False

    def test_connection_error_is_unavailable(self, monkeypatch) -> None:
        def boom(url, timeout):
            raise trading_briefing.requests.exceptions.ConnectionError("down")

        monkeypatch.setattr(trading_briefing.requests, "get", boom)
        assert trading_briefing.check_lm_studio() is False


class TestFormatBriefing:
    def test_recommendation_extraction(self) -> None:
        results = [
            {"ticker": "BTC-USD", "success": True, "decision": "We recommend a BUY", "error": None},
            {"ticker": "ETH-USD", "success": True, "decision": "Time to SELL", "error": None},
            {"ticker": "SOL-USD", "success": False, "decision": None, "error": "endpoint down"},
        ]
        out = trading_briefing.format_briefing(results, "2026-06-01")
        assert "# Trading Briefing - 2026-06-01" in out
        assert "Not financial advice" in out
        assert "| BTC-USD | OK | BUY |" in out
        assert "| ETH-USD | OK | SELL |" in out
        assert "| SOL-USD | FAILED |" in out

    def test_failed_analysis_shows_error_detail(self) -> None:
        results = [{"ticker": "BTC-USD", "success": False, "decision": None, "error": "boom"}]
        out = trading_briefing.format_briefing(results, "2026-06-01")
        assert "**Analysis failed:** boom" in out


def test_save_briefing_writes_to_output_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(trading_briefing, "OUTPUT_DIR", tmp_path / "sources")
    path = trading_briefing.save_briefing("# hello", "2026-06-01")
    assert path.exists()
    assert path.name == "trading-briefing-2026-06-01.md"
    assert path.read_text() == "# hello"
