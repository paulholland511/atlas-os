#!/usr/bin/env python3
"""
Trading Briefing Generator (TradingAgents).

Runs a multi-agent TradingAgents analysis for a configurable set of tickers
against a local LLM endpoint, then saves the output as a markdown note in your
vault so the RAG pipeline can index it.

This is an OPTIONAL component. It requires the third-party TradingAgents package
and a running LLM endpoint. All configuration is read from the environment —
no hardcoded hosts, paths, emails, or positions.

NOTHING IN THIS SCRIPT IS FINANCIAL ADVICE. It is a research/automation
template. Use at your own risk.

Environment variables:
    VAULT_PATH          Absolute path to the vault (required)
    LM_STUDIO_HOST      LLM host                 (default: localhost)
    LM_STUDIO_PORT      LLM port                 (default: 5555)
    LM_STUDIO_MODEL     Model name               (default: local-model)
    TRADING_AGENTS_PATH Path to TradingAgents    (default: ~/Documents/TradingAgents)
    TRADING_TICKERS     Comma-separated tickers  (default: BTC-USD,ETH-USD)

Usage:
    python trading_briefing.py
    python trading_briefing.py --ticker BTC-USD
    python trading_briefing.py --date 2026-01-01
    python trading_briefing.py --dry-run
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Fix OpenMP conflict on macOS
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

TRADING_AGENTS_PATH = Path(os.path.expanduser(
    os.environ.get("TRADING_AGENTS_PATH", "~/Documents/TradingAgents")
))
if TRADING_AGENTS_PATH.exists():
    sys.path.insert(0, str(TRADING_AGENTS_PATH))

try:
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG
    import requests
except ImportError as e:
    print(f"Error importing TradingAgents: {e}")
    print("Install it: git clone the TradingAgents project and `pip install -e .`,")
    print("then set TRADING_AGENTS_PATH to its location.")
    sys.exit(1)

# Configuration (all from environment)
def _try_import_backends():
    """Import ``atlas_os.backends`` (adding the repo root to sys.path if needed)."""
    try:
        from atlas_os import backends
        return backends
    except ImportError:
        pass
    for parent in Path(__file__).resolve().parents:
        if (parent / "atlas_os" / "__init__.py").exists():
            sys.path.insert(0, str(parent))
            break
    try:
        from atlas_os import backends
        return backends
    except ImportError:
        return None


def _resolve_chat() -> tuple[str, str]:
    """Resolve ``(api_base_url_with_v1, model)`` for the chat endpoint.

    ``LM_STUDIO_URL`` (or ``LM_STUDIO_HOST`` + ``LM_STUDIO_PORT``) still works
    exactly as before. When none is set we auto-detect a backend via
    :mod:`atlas_os.backends`; ``ATLAS_LLM_MODEL`` overrides the model name.
    """
    url = os.environ.get("LM_STUDIO_URL")
    host = os.environ.get("LM_STUDIO_HOST")
    port = os.environ.get("LM_STUDIO_PORT")
    model = os.environ.get("LM_STUDIO_MODEL") or os.environ.get("ATLAS_LLM_MODEL")

    if not url and (host or port):
        url = f"http://{host or 'localhost'}:{port or '5555'}/v1"

    if not url:
        backends = _try_import_backends()
        if backends is not None:
            try:
                client = backends.get_client()
                url = client.api_base
                model = model or client.model
            except backends.BackendError:
                pass

    return url or "http://localhost:5555/v1", model or "local-model"


LM_STUDIO_URL, LM_STUDIO_MODEL = _resolve_chat()

VAULT_PATH = Path(os.path.expanduser(os.environ.get("VAULT_PATH", "."))).resolve()
OUTPUT_DIR = VAULT_PATH / "wiki" / "sources"

DEFAULT_TICKERS = [
    t.strip() for t in os.environ.get("TRADING_TICKERS", "BTC-USD,ETH-USD").split(",") if t.strip()
]


def check_lm_studio() -> bool:
    """Check if the LLM endpoint is available."""
    try:
        response = requests.get(f"{LM_STUDIO_URL}/models", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def get_trading_config() -> dict:
    """Build TradingAgents configuration pointing at the local LLM endpoint."""
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "ollama"
    config["backend_url"] = LM_STUDIO_URL
    config["deep_think_llm"] = LM_STUDIO_MODEL
    config["quick_think_llm"] = LM_STUDIO_MODEL
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1
    config["data_vendors"] = {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
    }
    return config


def analyze_ticker(ta: "TradingAgentsGraph", ticker: str, date: str) -> dict:
    """Run TradingAgents analysis for a single ticker."""
    print(f"Analyzing {ticker} for {date}...")
    try:
        _, decision = ta.propagate(ticker, date)
        return {"ticker": ticker, "date": date, "success": True, "decision": decision, "error": None}
    except Exception as e:
        return {"ticker": ticker, "date": date, "success": False, "decision": None, "error": str(e)}


def format_briefing(results: list, date: str) -> str:
    """Format analysis results as a markdown briefing."""
    now = datetime.now()
    lines = [
        "---",
        f"date: {now.strftime('%Y-%m-%d')}",
        "tags: [trading, briefing]",
        "source: TradingAgents",
        f"analysis_date: {date}",
        f"generated: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        "---",
        "",
        f"# Trading Briefing - {date}",
        "",
        f"Generated by TradingAgents on {now.strftime('%Y-%m-%d at %H:%M')}",
        "",
        "> Not financial advice. Research/automation output only.",
        "",
        "## Summary",
        "",
        "| Ticker | Status | Recommendation |",
        "|--------|--------|----------------|",
    ]
    for result in results:
        status = "OK" if result["success"] else "FAILED"
        if result["success"] and result["decision"]:
            decision_text = str(result["decision"]).lower()
            if "buy" in decision_text:
                rec = "BUY"
            elif "sell" in decision_text:
                rec = "SELL"
            elif "hold" in decision_text:
                rec = "HOLD"
            else:
                rec = "See details"
        else:
            rec = (result.get("error") or "N/A")[:30]
        lines.append(f"| {result['ticker']} | {status} | {rec} |")

    lines += ["", "---", "", "## Detailed Analysis", ""]
    for result in results:
        lines.append(f"### {result['ticker']}")
        lines.append("")
        if result["success"]:
            lines.append(str(result["decision"]))
        else:
            lines.append(f"**Analysis failed:** {result['error']}")
        lines += ["", "---", ""]

    lines += [
        "## Configuration",
        "",
        "- **LLM Provider:** local endpoint (OpenAI-compatible)",
        f"- **Model:** {LM_STUDIO_MODEL}",
        f"- **Backend URL:** {LM_STUDIO_URL}",
        "- **Data Source:** yfinance",
        "",
    ]
    return "\n".join(lines)


def save_briefing(content: str, date: str) -> Path:
    """Save briefing to the vault."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"trading-briefing-{date}.md"
    output_path.write_text(content, encoding="utf-8")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate a TradingAgents briefing")
    parser.add_argument("--ticker", type=str, help="Specific ticker (e.g. BTC-USD)")
    parser.add_argument("--date", type=str, help="Analysis date YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--dry-run", action="store_true", help="Check config without running")
    args = parser.parse_args()

    analysis_date = args.date or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tickers = [args.ticker] if args.ticker else DEFAULT_TICKERS

    print("=" * 60)
    print("TradingAgents Trading Briefing Generator")
    print("=" * 60)
    print(f"Analysis Date: {analysis_date}")
    print(f"Tickers: {', '.join(tickers)}")
    print(f"LLM URL: {LM_STUDIO_URL}")
    print(f"Model: {LM_STUDIO_MODEL}\n")

    print("Checking LLM endpoint availability...")
    if not check_lm_studio():
        print(f"\nERROR: LLM endpoint not available at {LM_STUDIO_URL}")
        print("Ensure your local LLM server is running and the model is loaded.")
        sys.exit(1)
    print("LLM endpoint is available.")

    if args.dry_run:
        print("\nDry run complete. Configuration is valid.")
        return

    print("Initializing TradingAgentsGraph...")
    ta = TradingAgentsGraph(debug=True, config=get_trading_config())

    results = []
    for ticker in tickers:
        result = analyze_ticker(ta, ticker, analysis_date)
        results.append(result)
        print(f"  {ticker}: {'OK' if result['success'] else 'FAILED'}")

    print("\nGenerating briefing...")
    content = format_briefing(results, analysis_date)
    output_path = save_briefing(content, analysis_date)

    print("\n" + "=" * 60)
    print("BRIEFING COMPLETE")
    print("=" * 60)
    print(f"Output saved to: {output_path}")
    success_count = sum(1 for r in results if r["success"])
    print(f"Results: {success_count}/{len(results)} analyses completed successfully")


if __name__ == "__main__":
    if not os.environ.get("VAULT_PATH"):
        print("ERROR: VAULT_PATH environment variable is not set. See .env.example.",
              file=sys.stderr)
        sys.exit(1)
    main()
