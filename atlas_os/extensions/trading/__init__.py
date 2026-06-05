"""The trading extension — market-research briefings as an optional module.

This wraps ``scripts/trading_briefing.py`` (a multi-agent TradingAgents analysis
against a local LLM, written back into the vault) behind ``atlas trading``. It is
deliberately an *extension* rather than core: most Atlas OS users don't trade, it
pulls in the optional ``yfinance`` dependency and a third-party ``TradingAgents``
package, and nothing in the core (vault, RAG, git, dashboard) depends on it.

Install the extra with ``pip install 'atlas-os[trading]'``. Without it the
command still registers, but the underlying script will report the missing
dependency when run.

NOTHING HERE IS FINANCIAL ADVICE — it is a research/automation template.
"""

from __future__ import annotations

from typing import Any

import typer

from atlas_os.extensions.base import AtlasExtension


class TradingExtension(AtlasExtension):
    """Registers ``atlas trading`` — generate a trading research briefing."""

    @property
    def name(self) -> str:
        return "trading"

    @property
    def description(self) -> str:
        return "Trading research briefings (TradingAgents) written into the vault."

    @property
    def version(self) -> str:
        return "1.0.0"

    def register_commands(self, cli: typer.Typer) -> None:
        # Imported here, not at module top, so the core never pulls in the CLI's
        # audited-run machinery just to discover this extension. By the time
        # register_commands runs, atlas_os.cli is fully loaded.
        from atlas_os import cli as _cli
        from atlas_os._paths import scripts_dir

        @cli.command(context_settings=_cli._PASSTHROUGH)  # pyright: ignore[reportPrivateUsage]
        def trading(ctx: typer.Context) -> None:
            """Generate a trading research briefing (--ticker | --date | --dry-run).

            Optional extension — needs the third-party TradingAgents package and a
            running local LLM endpoint. Reads VAULT_PATH and LM_STUDIO_* from the env.
            Install with ``pip install 'atlas-os[trading]'``.
            """
            _cli._require_env("VAULT_PATH")  # pyright: ignore[reportPrivateUsage]
            _cli._run_audited(  # pyright: ignore[reportPrivateUsage]
                "trading",
                scripts_dir() / "trading_briefing.py",
                ctx.args,
                _cli._context_for("trading", ctx.args),  # pyright: ignore[reportPrivateUsage]
            )

    def register_skills(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "daily-trading-report",
                "description": "Generate and email a daily trading research briefing.",
                "cadence": "Daily (~13:00)",
            },
        ]

    def register_schedules(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "daily-trading-report",
                "cron": "0 13 * * *",
                "command": "atlas trading",
            },
        ]
