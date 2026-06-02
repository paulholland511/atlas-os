"""
News Agent for TradingAgents SDK.

Phase 1: Placeholder implementation using volatility analysis.
Phase 2 will add real news search integration.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from ..core import Agent, ModelConfig

logger = logging.getLogger(__name__)


@dataclass
class NewsAgent(Agent):
    """
    Agent that analyzes news and catalysts.

    Phase 1 Implementation:
        Uses volatility analysis as a proxy for news/catalyst activity.
        High volatility suggests significant market-moving events.
        Real news search will be added in Phase 2.

    Phase 2 (TODO):
        - Integrate news search API (NewsAPI, Google News, etc.)
        - Sentiment analysis of headlines
        - Event detection (earnings, regulatory, partnership)
    """

    name: str = "news"
    role: str = "News analyst evaluating catalysts and market-moving events"
    tools: list = field(default_factory=list)
    model_config: ModelConfig | None = None

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Analyze news/catalyst activity for the ticker.

        Phase 1: Uses volatility as a proxy for news activity.

        Expected context keys:
            - ticker: str
            - price_history: dict with ohlcv data

        Returns standardized recommendation dict.
        """
        ticker = context.get("ticker", "UNKNOWN")
        price_history = context.get("price_history", {})

        ohlcv = price_history.get("ohlcv", [])

        if len(ohlcv) < 7:
            return self._make_output(
                ticker=ticker,
                recommendation="HOLD",
                confidence=0.2,
                reasoning="Insufficient data for volatility analysis",
                extra={"catalyst_detected": False, "phase": "1-placeholder"},
            )

        # Calculate volatility metrics
        volatility_result = self._analyze_volatility(ohlcv)

        recommendation, confidence, reasoning = self._volatility_to_recommendation(
            ticker, volatility_result
        )

        return self._make_output(
            ticker=ticker,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=reasoning,
            extra={
                "volatility_7d": volatility_result.get("volatility_7d"),
                "volatility_regime": volatility_result.get("regime"),
                "catalyst_detected": volatility_result.get("catalyst_detected", False),
                "phase": "1-placeholder",
                "note": "Real news search to be added in Phase 2",
            },
        )

    def _analyze_volatility(self, ohlcv: list[dict]) -> dict[str, Any]:
        """
        Analyze price volatility as a proxy for news activity.

        Returns:
            Dict with volatility metrics and regime classification.
        """
        # Get last 7 days for recent volatility
        recent = ohlcv[-7:]
        closes = [day.get("close", 0) for day in recent if day.get("close", 0) > 0]

        if len(closes) < 2:
            return {"error": "insufficient_data", "regime": "unknown"}

        # Calculate daily returns
        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0:
                daily_return = (closes[i] / closes[i - 1]) - 1
                returns.append(daily_return)

        if not returns:
            return {"error": "no_returns", "regime": "unknown"}

        # Standard deviation of returns (volatility)
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        volatility_7d = math.sqrt(variance) * 100  # As percentage

        # Annualized volatility (rough estimate)
        annualized_vol = volatility_7d * math.sqrt(252)

        # Look for large single-day moves (potential catalysts)
        large_moves = [abs(r) for r in returns if abs(r) > 0.05]  # >5% moves
        catalyst_detected = len(large_moves) > 0

        # Regime classification
        if volatility_7d > 5:
            regime = "high_volatility_catalyst"
        elif volatility_7d > 2:
            regime = "elevated"
        elif volatility_7d > 1:
            regime = "normal"
        else:
            regime = "quiet"

        return {
            "volatility_7d": round(volatility_7d, 2),
            "annualized_vol": round(annualized_vol, 2),
            "mean_return": round(mean_return * 100, 2),
            "large_moves_count": len(large_moves),
            "catalyst_detected": catalyst_detected,
            "regime": regime,
        }

    def _volatility_to_recommendation(
        self, ticker: str, vol_result: dict[str, Any]
    ) -> tuple[str, float, str]:
        """
        Convert volatility analysis to recommendation.

        High volatility without clear direction = HOLD (wait for clarity).
        Quiet market = continue with trend from other signals.
        """
        if "error" in vol_result:
            return "HOLD", 0.2, f"Volatility analysis error: {vol_result.get('error')}"

        regime = vol_result.get("regime", "unknown")
        vol_7d = vol_result.get("volatility_7d", 0)
        mean_return = vol_result.get("mean_return", 0)
        catalyst = vol_result.get("catalyst_detected", False)

        recommendation = "HOLD"
        confidence = 0.4  # Lower confidence for proxy-based analysis
        reasoning_parts = []

        if regime == "high_volatility_catalyst":
            reasoning_parts.append(f"High volatility ({vol_7d:.1f}%) suggests active catalysts")
            if catalyst:
                reasoning_parts.append("Large single-day moves detected")
            # High vol without clear direction = wait
            if abs(mean_return) < 2:
                reasoning_parts.append("No clear directional bias - wait for clarity")
                recommendation = "HOLD"
                confidence = 0.3
            elif mean_return > 2:
                reasoning_parts.append("Positive bias with high volatility")
                recommendation = "BUY"
                confidence = 0.45
            else:
                reasoning_parts.append("Negative bias with high volatility")
                recommendation = "SELL"
                confidence = 0.45

        elif regime == "elevated":
            reasoning_parts.append(f"Elevated volatility ({vol_7d:.1f}%)")
            if mean_return > 1:
                recommendation = "BUY"
                confidence = 0.5
            elif mean_return < -1:
                recommendation = "SELL"
                confidence = 0.5
            reasoning_parts.append(f"Mean daily return: {mean_return:+.2f}%")

        elif regime == "quiet":
            reasoning_parts.append(f"Quiet market ({vol_7d:.1f}% volatility)")
            reasoning_parts.append("Low news activity - defer to other analysts")
            confidence = 0.35

        else:  # normal
            reasoning_parts.append(f"Normal volatility ({vol_7d:.1f}%)")
            confidence = 0.4

        reasoning = "; ".join(reasoning_parts)
        return recommendation, confidence, f"[Deterministic/Volatility Proxy] {reasoning}"
