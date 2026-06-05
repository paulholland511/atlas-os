"""Tests for the extension system — discovery, loading, and CLI registration.

These are hermetic: they exercise the discovery/loading machinery and the Typer
app in-process via ``CliRunner``, and never touch the network or the underlying
pipeline scripts.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import typer
from typer.testing import CliRunner

from atlas_os import extensions as ext
from atlas_os.cli import app
from atlas_os.extensions.base import AtlasExtension
from atlas_os.extensions.jobs import JobsExtension
from atlas_os.extensions.trading import TradingExtension
from atlas_os.extensions.voice import VoiceExtension

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clean_extension_state() -> Iterator[None]:
    """Reset the module-global registry around each test so they don't leak."""
    ext._reset_for_tests()
    yield
    ext._reset_for_tests()


# ── Discovery ─────────────────────────────────────────────────────────────────
def test_builtins_are_discovered() -> None:
    names = {e.name for e in ext.list_extensions()}
    assert {"trading", "voice", "jobs"} <= names


def test_discovered_extensions_are_sorted() -> None:
    names = [e.name for e in ext.list_extensions()]
    assert names == sorted(names)


def test_builtin_targets_resolve_to_subclasses() -> None:
    for discovered in ext.list_extensions():
        if discovered.source != "built-in":
            continue
        cls = ext._resolve_target(discovered.target)
        assert issubclass(cls, AtlasExtension)


# ── Loading ───────────────────────────────────────────────────────────────────
def test_load_extension_returns_instance() -> None:
    instance = ext.load_extension("trading")
    assert isinstance(instance, TradingExtension)
    assert instance.name == "trading"


def test_load_extension_is_idempotent() -> None:
    first = ext.load_extension("trading")
    second = ext.load_extension("trading")
    assert first is second


def test_load_unknown_extension_raises() -> None:
    with pytest.raises(ext.ExtensionNotFoundError):
        ext.load_extension("does-not-exist")


def test_get_extension_before_load_raises() -> None:
    with pytest.raises(ext.ExtensionNotFoundError):
        ext.get_extension("voice")


def test_get_extension_after_load_returns_it() -> None:
    loaded = ext.load_extension("voice")
    assert ext.get_extension("voice") is loaded


def test_unload_extension_runs_hook() -> None:
    ext.load_extension("jobs")
    ext.unload_extension("jobs")
    with pytest.raises(ext.ExtensionNotFoundError):
        ext.get_extension("jobs")


def test_unload_unloaded_extension_raises() -> None:
    with pytest.raises(ext.ExtensionNotFoundError):
        ext.unload_extension("trading")


def test_load_all_extensions_returns_builtins() -> None:
    loaded = ext.load_all_extensions()
    names = {e.name for e in loaded}
    assert {"trading", "voice", "jobs"} <= names


# ── Command registration ──────────────────────────────────────────────────────
def test_extensions_register_commands_onto_a_fresh_app() -> None:
    fresh = typer.Typer()
    ext.load_all_extensions(fresh)
    # trading is a top-level command; voice and jobs are sub-apps. Drive the
    # fresh app to confirm each surface registered, rather than introspecting
    # Typer's internals.
    assert runner.invoke(fresh, ["trading", "--help"]).exit_code == 0
    assert runner.invoke(fresh, ["voice", "--help"]).exit_code == 0
    assert runner.invoke(fresh, ["jobs", "--help"]).exit_code == 0


def test_core_app_works_without_extensions() -> None:
    """A core command renders even when no extension is loaded.

    Simulates a bare core by registering only a core command on a fresh app and
    confirming it runs — extensions are additive, never required.
    """
    core = typer.Typer()

    @core.command()
    def ping() -> None:
        typer.echo("pong")

    # A second command keeps this a multi-command group (Typer collapses a
    # single-command app into one that takes no subcommand name).
    @core.command()
    def noop() -> None:
        typer.echo("noop")

    result = runner.invoke(core, ["ping"])
    assert result.exit_code == 0
    assert "pong" in result.stdout


# ── Fault tolerance ───────────────────────────────────────────────────────────
def test_bad_extension_is_skipped_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    """A built-in pointing at a missing target is recorded, not raised."""
    monkeypatch.setitem(ext.BUILTIN_EXTENSIONS, "broken", "atlas_os.nope:Missing")
    ext._discover.cache_clear()

    loaded = ext.load_all_extensions()
    names = {e.name for e in loaded}
    assert "broken" not in names
    assert "broken" in ext.discovery_errors()
    # The healthy built-ins still loaded.
    assert {"trading", "voice", "jobs"} <= names


def test_resolve_malformed_target_raises() -> None:
    with pytest.raises(ext.ExtensionLoadError):
        ext._resolve_target("not-a-valid-target")


def test_resolve_non_extension_target_raises() -> None:
    with pytest.raises(ext.ExtensionLoadError):
        ext._resolve_target("atlas_os.cli:app")


# ── The base contract ─────────────────────────────────────────────────────────
def test_base_class_is_abstract() -> None:
    with pytest.raises(TypeError):
        AtlasExtension()  # type: ignore[abstract]


def test_default_hooks_are_noops() -> None:
    """A minimal extension only implements name/description; the rest default."""

    class Minimal(AtlasExtension):
        @property
        def name(self) -> str:
            return "minimal"

        @property
        def description(self) -> str:
            return "a minimal extension"

    m = Minimal()
    assert m.version == "0.0.0"
    assert m.register_skills() == []
    assert m.register_schedules() == []
    assert m.on_load() is None
    assert m.on_unload() is None


@pytest.mark.parametrize("cls", [TradingExtension, VoiceExtension, JobsExtension])
def test_builtin_metadata_is_well_formed(cls: type[AtlasExtension]) -> None:
    instance = cls()
    assert instance.name and instance.name.islower()
    assert instance.description
    assert instance.version


# ── CLI surface ───────────────────────────────────────────────────────────────
def test_extensions_list_command() -> None:
    result = runner.invoke(app, ["extensions", "list"])
    assert result.exit_code == 0
    for name in ("trading", "voice", "jobs"):
        assert name in result.stdout


def test_extensions_info_command() -> None:
    result = runner.invoke(app, ["extensions", "info", "trading"])
    assert result.exit_code == 0
    assert "trading" in result.stdout


def test_extensions_info_unknown_exits_2() -> None:
    result = runner.invoke(app, ["extensions", "info", "nope"])
    assert result.exit_code == 2


def test_trading_command_provided_by_extension() -> None:
    """The trading command moved out of core into the bundled extension."""
    result = runner.invoke(app, ["trading", "--help"])
    assert result.exit_code == 0


def test_voice_and_jobs_subcommands_registered() -> None:
    assert runner.invoke(app, ["voice", "--help"]).exit_code == 0
    assert runner.invoke(app, ["jobs", "--help"]).exit_code == 0
