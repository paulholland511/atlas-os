"""The jobs extension — job-search tracking as an optional module.

A placeholder for a job-application tracker that lives in the vault: applications
as markdown notes, status tracking, and scheduled reminders to follow up. Kept
out of the core because job-hunting is a temporary, personal workflow rather than
part of the knowledge-management substrate.

The command surface is stubbed: ``atlas jobs list`` and ``atlas jobs add``
register and explain themselves so the extension contract and CLI wiring are
exercised while the tracker is built out. Install the (currently empty) extra
with ``pip install 'atlas-os[jobs]'``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from atlas_os.extensions.base import AtlasExtension

if TYPE_CHECKING:
    import typer


class JobsExtension(AtlasExtension):
    """Registers ``atlas jobs`` — track job applications in the vault."""

    @property
    def name(self) -> str:
        return "jobs"

    @property
    def description(self) -> str:
        return "Job-application tracking stored as vault notes (stub)."

    @property
    def version(self) -> str:
        return "0.1.0"

    def register_commands(self, cli: typer.Typer) -> None:
        import typer

        jobs_app = typer.Typer(
            no_args_is_help=True,
            help="Track job applications as notes in your vault.",
        )

        @jobs_app.command("list")
        def jobs_list() -> None:
            """List tracked job applications (placeholder — reads from the vault)."""
            typer.secho(
                "  ! job tracker is not implemented yet — this is a placeholder.",
                fg=typer.colors.YELLOW,
            )

        @jobs_app.command("add")
        def jobs_add(
            company: str = typer.Argument(..., help="Company name."),
            role: str = typer.Option(None, "--role", "-r", help="Role applied for."),
        ) -> None:
            """Record a new job application (placeholder — writes a vault note)."""
            typer.secho(
                "  ! job tracker is not implemented yet — this is a placeholder.",
                fg=typer.colors.YELLOW,
            )
            detail = f"{company}" + (f" — {role}" if role else "")
            typer.echo(f"  would record application: {detail}")

        cli.add_typer(jobs_app, name="jobs")

    def register_skills(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "daily-job-tracker-update",
                "description": "Refresh job-application statuses and surface follow-ups.",
                "cadence": "Weekday mornings",
            },
        ]

    def register_schedules(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "daily-job-tracker-update",
                "cron": "0 9 * * 1-5",
                "command": "atlas jobs list",
            },
        ]
