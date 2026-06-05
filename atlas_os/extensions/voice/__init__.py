"""The voice extension — text-to-speech as an optional module.

A placeholder for speaking Atlas OS output aloud through a local TTS engine
(e.g. an MLX TTS server on ``localhost:8800`` piped to ``afplay``). Kept out of
the core because TTS is a personal, platform-specific concern that most users
won't want, and the core has no audio dependencies.

The command surface is stubbed: ``atlas voice say`` and ``atlas voice status``
register and explain themselves, so the extension contract and CLI wiring can be
exercised end-to-end while the synthesis backend is filled in later. Install the
(currently empty) extra with ``pip install 'atlas-os[voice]'``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from atlas_os.extensions.base import AtlasExtension

if TYPE_CHECKING:
    import typer


class VoiceExtension(AtlasExtension):
    """Registers ``atlas voice`` — speak text through a local TTS engine."""

    @property
    def name(self) -> str:
        return "voice"

    @property
    def description(self) -> str:
        return "Text-to-speech for Atlas OS output via a local TTS engine (stub)."

    @property
    def version(self) -> str:
        return "0.1.0"

    def register_commands(self, cli: typer.Typer) -> None:
        import typer

        voice_app = typer.Typer(
            no_args_is_help=True,
            help="Speak Atlas OS output aloud through a local TTS engine.",
        )

        @voice_app.command("say")
        def voice_say(
            text: str = typer.Argument(..., help="Text to speak aloud."),
        ) -> None:
            """Speak the given text (placeholder — wires up a local TTS engine).

            The synthesis backend isn't implemented yet; this stub confirms the
            command is wired in. Point it at your TTS server (e.g. MLX TTS on
            localhost:8800) when the backend lands.
            """
            typer.secho(
                "  ! voice synthesis is not implemented yet — "
                "this is a placeholder command.",
                fg=typer.colors.YELLOW,
            )
            typer.echo(f'  would speak: "{text}"')

        @voice_app.command("status")
        def voice_status() -> None:
            """Report whether a local TTS backend is configured (placeholder)."""
            typer.secho(
                "  ! voice extension is a stub — no TTS backend wired up yet.",
                fg=typer.colors.YELLOW,
            )

        cli.add_typer(voice_app, name="voice")

    def register_skills(self) -> list[dict[str, Any]]:
        return []
