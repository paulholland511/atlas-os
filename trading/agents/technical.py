"""
Technical Agent for TradingAgents SDK.

Analyzes price patterns and technical indicators to generate trading signals.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..core import Agent, ModelConfig

logger = logging.getLogger(__name__)


@dataclass
class TechnicalAgent(Agent):
    """
    Agent that analyzes technical indicators.

    Uses RSI, MACD, Bollinger Bands, and moving averages
    to generate buy/sell/hold signals.
    """

    name: str = "technical"
    role: str = "Technical analyst evaluating price patterns and indicators"
    tools: list = field(default_factory=list)
    model_config: ModelConfig | None = None  # Pure deterministic

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Analyze technical indicators for the ticker.

        Expected context keys:
            - ticker: str
            - price_history: dict with ohlcv data
            - indicators: dict with RSI, MACD, Bollinger Bands, SMAs

        Returns standardized recommendation dict.
        """
        ticker = context.get("ticker", "UNKNOWN")
        price_history = context.get("price_history", {})
        indicators = context.get("indicators", {})

        # Check for data errors
        if "error" in price_history:
            return self._make_output(
                ticker=ticker,
                recommendation="HOLD",
                confidence=0.1,
                reasoning=f"Price data error: {price_history.get('error')}",
            )

        if "error" in indicators:
            return self._make_output(
                ticker=ticker,
                recommendation="HOLD",
                confidence=0.2,
                reasoning=f"Indicator calculation error: {indicators.get('error')} "
                f"(have {indicators.get('have', 0)}, need {indicators.get('need', 50)})",
            )

        return self._analyze_technicals(ticker, indicators, price_history)

    def _analyze_technicals(
        self,
        ticker: str,
        indicators: dict[str, Any],
        price_history: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate recommendation based on technical indicators.

        Logic:
            BUY: RSI < 35 AND price below SMA20
            SELL: RSI > 70 AND price above upper Bollinger
            HOLD: otherwise

        Confidence based on how extreme the indicators are.
        """
        rsi = indicators.get("rsi_14", 50)
        macd_line = indicators.get("macd_line", 0)
        macd_signal = indicators.get("macd_signal", 0)
        macd_histogram = indicators.get("macd_histogram", 0)
        sma_20 = indicators.get("sma_20", 0)
        sma_50 = indicators.get("sma_50", 0)
        bb_upper = indicators.get("bollinger_upper", 0)
        bb_lower = indicators.get("bollinger_lower", 0)
        latest_price = indicators.get("latest_price", 0)

        # Signal scoring
        buy_signals = 0
        sell_signals = 0
        reasoning_parts = []
        confidence_boosts = 0

        # RSI analysis
        if rsi < 30:
            buy_signals += 2
            reasoning_parts.append(f"RSI oversold ({rsi:.1f})")
            confidence_boosts += 0.15
        elif rsi < 35:
            buy_signals += 1
            reasoning_parts.append(f"RSI approaching oversold ({rsi:.1f})")
            confidence_boosts += 0.05
        elif rsi > 75:
            sell_signals += 2
            reasoning_parts.append(f"RSI overbought ({rsi:.1f})")
            confidence_boosts += 0.15
        elif rsi > 70:
            sell_signals += 1
            reasoning_parts.append(f"RSI approaching overbought ({rsi:.1f})")
            confidence_boosts += 0.05
        else:
            reasoning_parts.append(f"RSI neutral ({rsi:.1f})")

        # Price vs SMA analysis
        if latest_price > 0 and sma_20 > 0:
            pct_from_sma20 = ((latest_price / sma_20) - 1) * 100

            if latest_price < sma_20:
                buy_signals += 1
                reasoning_parts.append(f"Price below SMA20 ({pct_from_sma20:.1f}%)")
            elif latest_price > sma_20 * 1.05:
                sell_signals += 1
                reasoning_parts.append(f"Price above SMA20 (+{pct_from_sma20:.1f}%)")

        if latest_price > 0 and sma_50 > 0:
            if sma_20 > sma_50:
                buy_signals += 1
                reasoning_parts.append("SMA20 > SMA50 (bullish trend)")
            elif sma_20 < sma_50:
                sell_signals += 1
                reasoning_parts.append("SMA20 < SMA50 (bearish trend)")

        # Bollinger Bands analysis
        if latest_price > 0 and bb_upper > 0:
            if latest_price >= bb_upper:
                sell_signals += 2
                reasoning_parts.append("Price at/above upper Bollinger Band")
                confidence_boosts += 0.1
            elif latest_price <= bb_lower:
                buy_signals += 2
                reasoning_parts.append("Price at/below lower Bollinger Band")
                confidence_boosts += 0.1
            else:
                bb_position = (latest_price - bb_lower) / (bb_upper - bb_lower) if bb_upper > bb_lower else 0.5
                if bb_position > 0.8:
                    reasoning_parts.append(f"Near upper BB ({bb_position*100:.0f}%)")
                elif bb_position < 0.2:
                    reasoning_parts.append(f"Near lower BB ({bb_position*100:.0f}%)")

        # MACD analysis
        if macd_histogram > 0 and macd_line > macd_signal:
            buy_signals += 1
            reasoning_parts.append("MACD bullish (histogram positive)")
        elif macd_histogram < 0 and macd_line < macd_signal:
            sell_signals += 1
            reasoning_parts.append("MACD bearish (histogram negative)")
        else:
            reasoning_parts.append("MACD neutral")

        # Generate recommendation
        recommendation, base_confidence = self._signals_to_recommendation(
            buy_signals, sell_signals
        )

        # Adjust confidence based on signal strength
        confidence = base_confidence + confidence_boosts
        confidence = min(max(confidence, 0.1), 0.95)

        # Calculate price targets
        targets = self._calculate_targets(latest_price, bb_upper, bb_lower, sma_20, sma_50)

        reasoning = "; ".join(reasoning_parts)

        return self._make_output(
            ticker=ticker,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=f"[Deterministic] {reasoning}",
            targets=targets,
            extra={
                "buy_signals": buy_signals,
                "sell_signals": sell_signals,
                "rsi": rsi,
                "macd_histogram": macd_histogram,
            },
        )

    def _signals_to_recommendation(
        self, buy_signals: int, sell_signals: int
    ) -> tuple[str, float]:
        """Convert signal counts to recommendation and base confidence."""
        net_signal = buy_signals - sell_signals

        if net_signal >= 3:
            return "BUY", 0.7
        elif net_signal >= 1:
            return "BUY", 0.55
        elif net_signal <= -3:
            return "SELL", 0.7
        elif net_signal <= -1:
            return "SELL", 0.55
        else:
            return "HOLD", 0.5

    def _calculate_targets(
        self,
        current_price: float,
        bb_upper: float,
        bb_lower: float,
        sma_20: float,
        sma_50: float,
    ) -> dict[str, float]:
        """Calculate price targets based on technical levels."""
        targets = {}

        if current_price <= 0:
            return targets

        # Resistance levels
        resistance = []
        if bb_upper > current_price:
            resistance.append(bb_upper)
        if sma_20 > current_price:
            resistance.append(sma_20)
        if sma_50 > current_price:
            resistance.append(sma_50)

        if resistance:
            targets["resistance_1"] = round(min(resistance), 6)
            if len(resistance) > 1:
                targets["resistance_2"] = round(sorted(resistance)[1], 6)

        # Support levels
        support = []
        if bb_lower < current_price:
            support.append(bb_lower)
        if sma_20 < current_price:
            support.append(sma_20)
        if sma_50 < current_price:
            support.append(sma_50)

        if support:
            targets["support_1"] = round(max(support), 6)
            if len(support) > 1:
                targets["support_2"] = round(sorted(support, reverse=True)[1], 6)

        return targets
