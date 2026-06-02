"""
Fundamentals Agent for TradingAgents SDK.

Analyzes fundamental data (market cap, PE ratio, supply metrics) to produce
investment recommendations.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import yfinance as yf

from ..config import CRYPTO_COINGECKO_IDS
from ..core import Agent, ModelConfig, ModelUnavailable, call_model, get_lm_studio_config

logger = logging.getLogger(__name__)


@dataclass
class FundamentalsAgent(Agent):
    """
    Agent that analyzes fundamental data for assets.

    For crypto: uses CoinGecko data (market cap, rank, supply).
    For stocks: uses yfinance info (market cap, PE ratio).
    """

    name: str = "fundamentals"
    role: str = "Fundamental analyst evaluating market cap, valuation, and supply metrics"
    tools: list = field(default_factory=list)
    model_config: ModelConfig | None = field(default_factory=get_lm_studio_config)

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Analyze fundamental data for the ticker.

        Expected context keys:
            - ticker: str
            - crypto_data: dict (if crypto) with market_cap_usd, rank, etc.
            - price_history: dict with ohlcv data

        Returns standardized recommendation dict.
        """
        ticker = context.get("ticker", "UNKNOWN")
        is_crypto = ticker in CRYPTO_COINGECKO_IDS
        price_history = context.get("price_history", {})
        crypto_data = context.get("crypto_data", {})

        # Check for data errors
        if "error" in price_history:
            return self._make_output(
                ticker=ticker,
                recommendation="HOLD",
                confidence=0.1,
                reasoning=f"Insufficient price data: {price_history.get('error')}",
                extra={"data_partial": True},
            )

        if is_crypto:
            return self._analyze_crypto(ticker, crypto_data, price_history)
        else:
            return self._analyze_stock(ticker, price_history)

    def _analyze_crypto(
        self,
        ticker: str,
        crypto_data: dict[str, Any],
        price_history: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze crypto fundamentals."""
        if "error" in crypto_data:
            logger.warning(f"Crypto data error for {ticker}: {crypto_data.get('error')}")
            # Fall back to price-only analysis
            return self._deterministic_crypto_analysis(ticker, price_history, None)

        # Try LLM analysis, fall back to deterministic
        try:
            return self._llm_crypto_analysis(
                ticker, crypto_data, price_history
            )
        except ModelUnavailable as e:
            logger.info(f"LLM unavailable, using deterministic analysis: {e}")
            return self._deterministic_crypto_analysis(ticker, price_history, crypto_data)

    def _deterministic_crypto_analysis(
        self,
        ticker: str,
        price_history: dict[str, Any],
        crypto_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Rule-based fundamental analysis for crypto."""
        recommendation = "HOLD"
        confidence = 0.5
        reasoning_parts = []

        if crypto_data and "error" not in crypto_data:
            rank = crypto_data.get("rank", 999)
            market_cap = crypto_data.get("market_cap_usd", 0)
            ath = crypto_data.get("ath_usd", 0)
            current_price = crypto_data.get("price_usd", 0)
            price_change_24h = crypto_data.get("price_change_24h_pct", 0)

            # Rank analysis
            if rank <= 10:
                reasoning_parts.append(f"Top 10 by market cap (#{rank})")
                confidence += 0.1
            elif rank <= 50:
                reasoning_parts.append(f"Top 50 by market cap (#{rank})")
            else:
                reasoning_parts.append(f"Lower market cap rank (#{rank})")
                confidence -= 0.1

            # ATH distance
            if ath > 0 and current_price > 0:
                ath_pct = (current_price / ath) * 100
                if ath_pct < 30:
                    reasoning_parts.append(f"Trading at {ath_pct:.0f}% of ATH - potential value")
                    recommendation = "BUY"
                    confidence += 0.15
                elif ath_pct > 90:
                    reasoning_parts.append(f"Near ATH ({ath_pct:.0f}%) - caution advised")
                    confidence -= 0.1

            # 24h momentum
            if price_change_24h > 5:
                reasoning_parts.append(f"Strong 24h momentum (+{price_change_24h:.1f}%)")
            elif price_change_24h < -5:
                reasoning_parts.append(f"Weak 24h momentum ({price_change_24h:.1f}%)")

            # Large market cap = more stable
            if market_cap > 50_000_000_000:  # >$50B
                reasoning_parts.append("Large cap - established market position")
                confidence += 0.05
        else:
            reasoning_parts.append("Limited fundamental data available")
            confidence = 0.3

        # 90-day price performance from history
        ohlcv = price_history.get("ohlcv", [])
        if len(ohlcv) >= 30:
            first_close = ohlcv[0].get("close", 0)
            last_close = ohlcv[-1].get("close", 0)
            if first_close > 0:
                period_return = ((last_close / first_close) - 1) * 100
                reasoning_parts.append(f"Period return: {period_return:.1f}%")
                if period_return > 20:
                    confidence += 0.1
                elif period_return < -20:
                    confidence -= 0.1

        reasoning = "; ".join(reasoning_parts) if reasoning_parts else "Standard holding position"
        data_partial = crypto_data is None or "error" in (crypto_data or {})

        return self._make_output(
            ticker=ticker,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=f"[Deterministic] {reasoning}",
            extra={"data_partial": data_partial, "analysis_mode": "deterministic"},
        )

    def _llm_crypto_analysis(
        self,
        ticker: str,
        crypto_data: dict[str, Any],
        price_history: dict[str, Any],
    ) -> dict[str, Any]:
        """LLM-based fundamental analysis for crypto."""
        if self.model_config is None:
            raise ModelUnavailable("No model configured")

        system_prompt = """You are a cryptocurrency fundamental analyst.
Analyze the provided data and give a recommendation.
Respond ONLY with a JSON object in this exact format:
{"recommendation": "BUY" or "SELL" or "HOLD", "confidence": 0.0-1.0, "reasoning": "brief explanation"}"""

        user_prompt = f"""Analyze {ticker}:
Market Cap: ${crypto_data.get('market_cap_usd', 0):,.0f}
Rank: #{crypto_data.get('rank', 'N/A')}
Current Price: ${crypto_data.get('price_usd', 0):.6f}
24h Change: {crypto_data.get('price_change_24h_pct', 0):.2f}%
ATH: ${crypto_data.get('ath_usd', 0):.6f}
90-day data points: {price_history.get('days', 0)}

Give your fundamental recommendation."""

        response = call_model(self.model_config, system_prompt, user_prompt)

        # Parse LLM response
        import json
        try:
            # Try to extract JSON from response
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1])
            data = json.loads(response)
            return self._make_output(
                ticker=ticker,
                recommendation=data.get("recommendation", "HOLD").upper(),
                confidence=float(data.get("confidence", 0.5)),
                reasoning=f"[LLM] {data.get('reasoning', 'No reasoning provided')}",
                extra={"analysis_mode": "llm"},
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            # Fall back to deterministic
            return self._deterministic_crypto_analysis(ticker, price_history, crypto_data)

    def _analyze_stock(
        self,
        ticker: str,
        price_history: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze stock fundamentals using yfinance info."""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            market_cap = info.get("marketCap", 0)
            pe_ratio = info.get("trailingPE")
            forward_pe = info.get("forwardPE")
            pb_ratio = info.get("priceToBook")
            dividend_yield = info.get("dividendYield", 0)

            return self._deterministic_stock_analysis(
                ticker, price_history, market_cap, pe_ratio, forward_pe, pb_ratio, dividend_yield
            )
        except Exception as e:
            logger.error(f"Failed to fetch stock info for {ticker}: {e}")
            return self._make_output(
                ticker=ticker,
                recommendation="HOLD",
                confidence=0.2,
                reasoning=f"Unable to fetch fundamental data: {e}",
                extra={"data_partial": True},
            )

    def _deterministic_stock_analysis(
        self,
        ticker: str,
        price_history: dict[str, Any],
        market_cap: float,
        pe_ratio: float | None,
        forward_pe: float | None,
        pb_ratio: float | None,
        dividend_yield: float,
    ) -> dict[str, Any]:
        """Rule-based fundamental analysis for stocks."""
        recommendation = "HOLD"
        confidence = 0.5
        reasoning_parts = []

        # Market cap analysis
        if market_cap > 200_000_000_000:  # >$200B
            reasoning_parts.append("Mega-cap - stable, lower growth potential")
        elif market_cap > 10_000_000_000:  # >$10B
            reasoning_parts.append("Large-cap - established business")
        else:
            reasoning_parts.append("Mid/small-cap - higher growth potential but more risk")

        # PE ratio analysis
        if pe_ratio is not None:
            if pe_ratio < 15:
                reasoning_parts.append(f"Low P/E ({pe_ratio:.1f}) - potentially undervalued")
                recommendation = "BUY"
                confidence += 0.15
            elif pe_ratio > 40:
                reasoning_parts.append(f"High P/E ({pe_ratio:.1f}) - premium valuation")
                confidence -= 0.1
            else:
                reasoning_parts.append(f"P/E ratio: {pe_ratio:.1f}")
        else:
            reasoning_parts.append("P/E ratio not available")

        # Forward PE vs current
        if pe_ratio and forward_pe and forward_pe < pe_ratio:
            reasoning_parts.append("Forward P/E lower than trailing - expected earnings growth")
            confidence += 0.1

        # Dividend yield
        if dividend_yield and dividend_yield > 0.03:
            reasoning_parts.append(f"Attractive dividend yield ({dividend_yield*100:.1f}%)")
            confidence += 0.05

        reasoning = "; ".join(reasoning_parts)

        return self._make_output(
            ticker=ticker,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=f"[Deterministic] {reasoning}",
            extra={
                "analysis_mode": "deterministic",
                "market_cap": market_cap,
                "pe_ratio": pe_ratio,
            },
        )
