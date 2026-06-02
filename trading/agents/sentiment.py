"""
Sentiment Agent for TradingAgents SDK.

Analyzes market sentiment using Fear & Greed Index and price momentum.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..core import Agent, ModelConfig

logger = logging.getLogger(__name__)


@dataclass
class SentimentAgent(Agent):
    """
    Agent that analyzes market sentiment.

    Uses the global Fear & Greed Index plus 7-day price momentum
    from the asset's price history.
    """

    name: str = "sentiment"
    role: str = "Sentiment analyst evaluating market fear/greed and momentum"
    tools: list = field(default_factory=list)
    model_config: ModelConfig | None = None  # Pure deterministic for sentiment

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Analyze sentiment for the ticker.

        Expected context keys:
            - ticker: str
            - fear_greed: dict with value, classification
            - price_history: dict with ohlcv data

        Returns standardized recommendation dict.
        """
        ticker = context.get("ticker", "UNKNOWN")
        fear_greed = context.get("fear_greed", {})
        price_history = context.get("price_history", {})

        # Extract Fear & Greed data
        fng_value = fear_greed.get("value", 50)
        fng_class = fear_greed.get("classification", "Neutral")
        fng_error = fear_greed.get("error")

        # Calculate 7-day momentum
        ohlcv = price_history.get("ohlcv", [])
        momentum_7d = self._calculate_momentum(ohlcv, days=7)
        momentum_30d = self._calculate_momentum(ohlcv, days=30)

        # Deterministic sentiment analysis
        recommendation, confidence, reasoning = self._analyze_sentiment(
            ticker, fng_value, fng_class, fng_error, momentum_7d, momentum_30d
        )

        return self._make_output(
            ticker=ticker,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=reasoning,
            extra={
                "fear_greed_value": fng_value,
                "fear_greed_class": fng_class,
                "momentum_7d": momentum_7d,
                "momentum_30d": momentum_30d,
            },
        )

    def _calculate_momentum(self, ohlcv: list[dict], days: int) -> float | None:
        """
        Calculate price momentum as percentage change over N days.

        Returns None if insufficient data.
        """
        if len(ohlcv) < days:
            return None

        recent = ohlcv[-days:]
        if not recent:
            return None

        start_price = recent[0].get("close", 0)
        end_price = recent[-1].get("close", 0)

        if start_price <= 0:
            return None

        return ((end_price / start_price) - 1) * 100

    def _analyze_sentiment(
        self,
        ticker: str,
        fng_value: int,
        fng_class: str,
        fng_error: str | None,
        momentum_7d: float | None,
        momentum_30d: float | None,
    ) -> tuple[str, float, str]:
        """
        Determine recommendation based on sentiment indicators.

        Uses contrarian logic: extreme fear = buying opportunity,
        extreme greed = selling opportunity.

        Returns (recommendation, confidence, reasoning).
        """
        recommendation = "HOLD"
        confidence = 0.5
        reasoning_parts = []

        # Fear & Greed analysis (contrarian)
        if fng_error:
            reasoning_parts.append(f"Fear & Greed unavailable: {fng_error}")
            confidence -= 0.1
        else:
            reasoning_parts.append(f"Fear & Greed: {fng_value} ({fng_class})")

            if fng_value <= 20:
                # Extreme fear - contrarian buy signal
                reasoning_parts.append("Extreme fear historically a buying opportunity")
                recommendation = "BUY"
                confidence += 0.25
            elif fng_value <= 35:
                # Fear - mild buy signal
                reasoning_parts.append("Fear levels suggest accumulation zone")
                recommendation = "BUY"
                confidence += 0.1
            elif fng_value >= 80:
                # Extreme greed - contrarian sell signal
                reasoning_parts.append("Extreme greed historically precedes corrections")
                recommendation = "SELL"
                confidence += 0.2
            elif fng_value >= 65:
                # Greed - caution
                reasoning_parts.append("Elevated greed levels - exercise caution")
                confidence -= 0.05

        # 7-day momentum analysis
        if momentum_7d is not None:
            if momentum_7d > 15:
                reasoning_parts.append(f"Strong 7d momentum (+{momentum_7d:.1f}%)")
                # Strong momentum in extreme greed = more confidence in SELL
                # Strong momentum in fear = wait for confirmation
                if recommendation == "SELL":
                    confidence += 0.1
                elif fng_value < 40:
                    reasoning_parts.append("Momentum diverges from sentiment - mixed signal")
            elif momentum_7d > 5:
                reasoning_parts.append(f"Positive 7d momentum (+{momentum_7d:.1f}%)")
            elif momentum_7d < -15:
                reasoning_parts.append(f"Strong 7d selling pressure ({momentum_7d:.1f}%)")
                # Capitulation in extreme fear = stronger buy
                if recommendation == "BUY" and fng_value <= 25:
                    confidence += 0.1
                    reasoning_parts.append("Capitulation + fear = stronger contrarian buy")
            elif momentum_7d < -5:
                reasoning_parts.append(f"Negative 7d momentum ({momentum_7d:.1f}%)")
        else:
            reasoning_parts.append("Insufficient data for 7d momentum")

        # 30-day momentum context
        if momentum_30d is not None:
            if momentum_30d > 30:
                reasoning_parts.append(f"Strong 30d trend (+{momentum_30d:.1f}%)")
            elif momentum_30d < -30:
                reasoning_parts.append(f"Severe 30d decline ({momentum_30d:.1f}%)")

        reasoning = "; ".join(reasoning_parts)
        return recommendation, confidence, f"[Deterministic] {reasoning}"
