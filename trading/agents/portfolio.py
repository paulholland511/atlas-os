"""
Portfolio Manager for TradingAgents SDK.

Synthesizes recommendations from all analyst agents into a final portfolio decision.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..config import AGENT_WEIGHTS
from ..core import Agent, ModelConfig

logger = logging.getLogger(__name__)


@dataclass
class PortfolioManager(Agent):
    """
    Agent that synthesizes analyst recommendations.

    Takes outputs from technical, fundamentals, sentiment, and news agents
    and produces a weighted final recommendation.

    Weights (from config.py):
        - technical: 0.35
        - fundamentals: 0.25
        - sentiment: 0.20
        - news: 0.20
    """

    name: str = "portfolio"
    role: str = "Portfolio manager synthesizing analyst recommendations"
    tools: list = field(default_factory=list)
    model_config: ModelConfig | None = None

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Synthesize analyst outputs into final recommendation.

        Expected context keys:
            - ticker: str
            - analyst_outputs: dict[str, dict] with keys matching agent names

        Returns standardized recommendation dict with additional
        'contributing_agents' field showing each analyst's vote.
        """
        ticker = context.get("ticker", "UNKNOWN")
        analyst_outputs = context.get("analyst_outputs", {})

        if not analyst_outputs:
            return self._make_output(
                ticker=ticker,
                recommendation="HOLD",
                confidence=0.1,
                reasoning="No analyst outputs to synthesize",
                extra={"contributing_agents": {}},
            )

        # Collect votes and confidences
        votes = {}
        confidences = {}
        reasoning_parts = []
        contributing_agents = {}

        for agent_name, output in analyst_outputs.items():
            if "error" in output or output.get("status") == "failed":
                logger.warning(f"Agent {agent_name} failed: {output.get('error')}")
                reasoning_parts.append(f"{agent_name}: FAILED")
                contributing_agents[agent_name] = {
                    "recommendation": "FAILED",
                    "confidence": 0,
                    "error": output.get("error"),
                }
                continue

            rec = output.get("recommendation", "HOLD").upper()
            conf = output.get("confidence", 0.5)

            votes[agent_name] = rec
            confidences[agent_name] = conf

            contributing_agents[agent_name] = {
                "recommendation": rec,
                "confidence": conf,
            }

            reasoning_parts.append(f"{agent_name}: {rec} ({conf:.0%})")

        if not votes:
            return self._make_output(
                ticker=ticker,
                recommendation="HOLD",
                confidence=0.1,
                reasoning="All analysts failed - defaulting to HOLD",
                extra={"contributing_agents": contributing_agents},
            )

        # Calculate weighted vote
        final_rec, final_conf = self._weighted_vote(votes, confidences)

        # Aggregate targets from technical agent
        targets = {}
        if "technical" in analyst_outputs and "targets" in analyst_outputs["technical"]:
            targets = analyst_outputs["technical"]["targets"]

        reasoning = f"Synthesized from: {'; '.join(reasoning_parts)}"

        return self._make_output(
            ticker=ticker,
            recommendation=final_rec,
            confidence=final_conf,
            reasoning=reasoning,
            targets=targets,
            extra={"contributing_agents": contributing_agents},
        )

    def _weighted_vote(
        self,
        votes: dict[str, str],
        confidences: dict[str, float],
    ) -> tuple[str, float]:
        """
        Calculate weighted recommendation based on agent weights.

        Converts recommendations to scores:
            BUY = +1, HOLD = 0, SELL = -1

        Final recommendation based on weighted sum of scores * confidences.
        """
        rec_to_score = {"BUY": 1.0, "HOLD": 0.0, "SELL": -1.0}

        weighted_sum = 0.0
        total_weight = 0.0
        confidence_sum = 0.0

        for agent_name, rec in votes.items():
            weight = AGENT_WEIGHTS.get(agent_name, 0.1)  # Default weight for unknown agents
            confidence = confidences.get(agent_name, 0.5)
            score = rec_to_score.get(rec, 0.0)

            # Weight by both agent importance and confidence
            effective_weight = weight * confidence
            weighted_sum += score * effective_weight
            total_weight += effective_weight
            confidence_sum += weight * confidence

        if total_weight == 0:
            return "HOLD", 0.3

        # Normalize weighted sum to [-1, 1]
        normalized_score = weighted_sum / total_weight

        # Convert score to recommendation
        if normalized_score >= 0.3:
            recommendation = "BUY"
        elif normalized_score <= -0.3:
            recommendation = "SELL"
        else:
            recommendation = "HOLD"

        # Final confidence: weighted average of agent confidences
        # Plus bonus for consensus
        consensus_bonus = self._calculate_consensus_bonus(votes)
        avg_confidence = confidence_sum / sum(AGENT_WEIGHTS.get(a, 0.1) for a in votes)
        final_confidence = min(avg_confidence + consensus_bonus, 0.95)

        return recommendation, round(final_confidence, 3)

    def _calculate_consensus_bonus(self, votes: dict[str, str]) -> float:
        """
        Calculate confidence bonus based on analyst consensus.

        Full consensus: +0.15
        3/4 agreement: +0.08
        Split: 0
        """
        if not votes:
            return 0.0

        vote_counts = {}
        for rec in votes.values():
            vote_counts[rec] = vote_counts.get(rec, 0) + 1

        total = len(votes)
        max_agreement = max(vote_counts.values())
        agreement_ratio = max_agreement / total

        if agreement_ratio >= 1.0:
            return 0.15
        elif agreement_ratio >= 0.75:
            return 0.08
        elif agreement_ratio >= 0.5:
            return 0.03
        else:
            return 0.0
