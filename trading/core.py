"""
Core framework for TradingAgents SDK.

Provides base classes for Tool, Agent, and Orchestrator, plus a model router
that supports LM Studio (OpenAI-compatible) and Anthropic endpoints.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .config import (
    LM_STUDIO_ENDPOINT,
    LM_STUDIO_MODEL,
    ANTHROPIC_MODEL,
    ANTHROPIC_API_KEY,
    HTTP_TIMEOUT_SECONDS,
    HTTP_RETRY_ATTEMPTS,
)

logger = logging.getLogger(__name__)


class ModelUnavailable(Exception):
    """Raised when the model endpoint is unreachable or returns a server error."""

    pass


@dataclass(frozen=True)
class ModelConfig:
    """Configuration for a model endpoint."""

    endpoint: str
    model: str
    api_key: str
    provider: str  # "openai_compatible" or "anthropic"


def get_lm_studio_config() -> ModelConfig:
    """Return config for LM Studio."""
    return ModelConfig(
        endpoint=LM_STUDIO_ENDPOINT,
        model=LM_STUDIO_MODEL,
        api_key="",
        provider="openai_compatible",
    )


def get_anthropic_config() -> ModelConfig:
    """Return config for Anthropic."""
    return ModelConfig(
        endpoint="https://api.anthropic.com",
        model=ANTHROPIC_MODEL,
        api_key=ANTHROPIC_API_KEY,
        provider="anthropic",
    )


def call_model(
    model_config: ModelConfig,
    system_prompt: str,
    user_prompt: str,
    tools: list[dict[str, Any]] | None = None,
) -> str:
    """
    Call a model endpoint and return the text response.

    Supports:
    - provider="openai_compatible" -> POST to {endpoint}/v1/chat/completions
    - provider="anthropic" -> Anthropic Messages API

    Raises:
        ModelUnavailable: If the endpoint is unreachable or returns 5xx.
    """
    if model_config.provider == "openai_compatible":
        return _call_openai_compatible(model_config, system_prompt, user_prompt, tools)
    elif model_config.provider == "anthropic":
        return _call_anthropic(model_config, system_prompt, user_prompt, tools)
    else:
        raise ValueError(f"Unknown provider: {model_config.provider}")


def _call_openai_compatible(
    config: ModelConfig,
    system_prompt: str,
    user_prompt: str,
    tools: list[dict[str, Any]] | None = None,
) -> str:
    """Call an OpenAI-compatible endpoint (LM Studio)."""
    url = f"{config.endpoint}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    payload: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2000,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    for attempt in range(HTTP_RETRY_ATTEMPTS):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=HTTP_TIMEOUT_SECONDS * 3,  # LLM calls need more time
            )
            if response.status_code >= 400:
                raise ModelUnavailable(
                    f"HTTP error {response.status_code}: {response.text[:200]}"
                )
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.ConnectionError as e:
            if attempt == HTTP_RETRY_ATTEMPTS - 1:
                raise ModelUnavailable(f"Connection failed: {e}") from e
            logger.warning(f"Connection error, retrying... ({attempt + 1})")
        except requests.exceptions.Timeout as e:
            if attempt == HTTP_RETRY_ATTEMPTS - 1:
                raise ModelUnavailable(f"Timeout: {e}") from e
            logger.warning(f"Timeout, retrying... ({attempt + 1})")

    raise ModelUnavailable("All retry attempts exhausted")


def _call_anthropic(
    config: ModelConfig,
    system_prompt: str,
    user_prompt: str,
    tools: list[dict[str, Any]] | None = None,
) -> str:
    """Call the Anthropic Messages API."""
    url = f"{config.endpoint}/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": config.api_key,
        "anthropic-version": "2023-06-01",
    }

    payload: dict[str, Any] = {
        "model": config.model,
        "max_tokens": 2000,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    if tools:
        # Convert OpenAI tool format to Anthropic format if needed
        payload["tools"] = tools

    for attempt in range(HTTP_RETRY_ATTEMPTS):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=HTTP_TIMEOUT_SECONDS * 6,  # Anthropic may be slower
            )
            if response.status_code >= 400:
                raise ModelUnavailable(
                    f"HTTP error {response.status_code}: {response.text[:200]}"
                )
            data = response.json()
            # Extract text from content blocks
            content = data.get("content", [])
            text_parts = [
                block["text"] for block in content if block.get("type") == "text"
            ]
            return " ".join(text_parts)
        except requests.exceptions.ConnectionError as e:
            if attempt == HTTP_RETRY_ATTEMPTS - 1:
                raise ModelUnavailable(f"Connection failed: {e}") from e
            logger.warning(f"Connection error, retrying... ({attempt + 1})")
        except requests.exceptions.Timeout as e:
            if attempt == HTTP_RETRY_ATTEMPTS - 1:
                raise ModelUnavailable(f"Timeout: {e}") from e
            logger.warning(f"Timeout, retrying... ({attempt + 1})")

    raise ModelUnavailable("All retry attempts exhausted")


class Tool(ABC):
    """
    Base class for tools.

    Tools fetch data or perform computations. They return structured dicts,
    never free text.
    """

    name: str
    description: str
    input_schema: dict[str, Any]

    @abstractmethod
    def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute the tool and return structured data.

        Returns:
            A dict with the result. On failure, include "error" key.
        """
        ...


@dataclass
class Agent(ABC):
    """
    Base class for agents.

    Agents analyze data using tools and optionally LLMs to produce
    structured recommendations.
    """

    name: str
    role: str
    tools: list[Tool] = field(default_factory=list)
    model_config: ModelConfig | None = None
    memory_cache_path: Path | None = None

    @abstractmethod
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Run the agent's analysis.

        Args:
            context: Dict containing pre-fetched data (price_history, indicators, etc.)

        Returns:
            Structured dict with keys:
                - agent: str (agent name)
                - ticker: str
                - recommendation: str ("BUY", "SELL", "HOLD")
                - confidence: float (0.0 to 1.0)
                - reasoning: str
                - targets: dict (optional price targets)
                - timestamp: str (ISO format)
        """
        ...

    def _make_output(
        self,
        ticker: str,
        recommendation: str,
        confidence: float,
        reasoning: str,
        targets: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Helper to construct standardized output."""
        output = {
            "agent": self.name,
            "ticker": ticker,
            "recommendation": recommendation,
            "confidence": round(min(max(confidence, 0.0), 1.0), 3),
            "reasoning": reasoning,
            "targets": targets or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            output.update(extra)
        return output


class Orchestrator:
    """
    Orchestrates parallel execution of multiple agents.

    Uses ThreadPoolExecutor to run agents concurrently with per-agent timeouts.
    On error or timeout, returns error dict for that agent without crashing.
    """

    def __init__(self, max_workers: int = 8):
        self.max_workers = max_workers
        self.logger = logging.getLogger(f"{__name__}.Orchestrator")

    def dispatch(
        self,
        agents: list[Agent],
        context: dict[str, Any],
        timeout_per_agent: float = 60.0,
    ) -> dict[str, dict[str, Any]]:
        """
        Run multiple agents in parallel.

        Args:
            agents: List of Agent instances to run.
            context: Shared context dict with pre-fetched data.
            timeout_per_agent: Max seconds to wait for each agent.

        Returns:
            Dict keyed by agent name, each value is the agent's output dict
            or an error dict if the agent failed/timed out.
        """
        results: dict[str, dict[str, Any]] = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_agent = {
                executor.submit(agent.run, context): agent for agent in agents
            }

            for future in future_to_agent:
                agent = future_to_agent[future]
                try:
                    result = future.result(timeout=timeout_per_agent)
                    results[agent.name] = result
                    self.logger.info(f"Agent {agent.name} completed successfully")
                except FuturesTimeoutError:
                    self.logger.error(f"Agent {agent.name} timed out")
                    results[agent.name] = {
                        "agent": agent.name,
                        "error": f"Timeout after {timeout_per_agent}s",
                        "status": "failed",
                    }
                except Exception as e:
                    self.logger.error(f"Agent {agent.name} failed: {e}")
                    results[agent.name] = {
                        "agent": agent.name,
                        "error": str(e),
                        "status": "failed",
                    }

        return results
