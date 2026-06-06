"""Tests for eidetic_os.setup_wizard — the interactive onboarding wizard (#25).

Everything runs offline: vault detection is driven against a temp ``home``,
backend probing against a real in-process mock HTTP server (the ``llm_server``
fixture from conftest), config generation is pure, and the full ``run_wizard``
flow is driven with scripted prompt/confirm/select callables and a recording UI.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from eidetic_os import config, setup_wizard
from eidetic_os._probe import Endpoint
from eidetic_os.setup_wizard import (
    Profile,
    build_config,
    collect_profile,
    detect_vault,
    embedding_models,
    probe_backends,
    run_wizard,
    select_embedding_model,
)


# ── A recording UI so flow tests can assert on what was shown ────────────────────
class RecordingUI:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def banner(self, version: str) -> None:
        self.lines.append(f"banner:{version}")

    def rule(self, text: str) -> None:
        self.lines.append(f"rule:{text}")

    def panel(self, title: str, lines) -> None:
        self.lines.append(f"panel:{title}")

    def success(self, text: str) -> None:
        self.lines.append(f"ok:{text}")

    def warn(self, text: str) -> None:
        self.lines.append(f"warn:{text}")

    def info(self, text: str) -> None:
        self.lines.append(f"info:{text}")

    def table(self, title, columns, rows) -> None:
        self.lines.append(f"table:{title}:{len(rows)}")


# ── Vault detection ──────────────────────────────────────────────────────────────
class TestDetectVault:
    def test_env_var_wins(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VAULT_PATH", str(tmp_path / "explicit"))
        assert detect_vault(home=tmp_path) == tmp_path / "explicit"

    def test_direct_vault_with_obsidian_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("VAULT_PATH", raising=False)
        vault = tmp_path / "Obsidian"
        (vault / ".obsidian").mkdir(parents=True)
        assert detect_vault(["~/Obsidian"], home=tmp_path) == vault

    def test_picks_first_subvault(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("VAULT_PATH", raising=False)
        holder = tmp_path / "Documents" / "Obsidian"
        sub = holder / "Atlas"
        sub.mkdir(parents=True)
        (sub / "note.md").write_text("# hi", encoding="utf-8")
        assert detect_vault(["~/Documents/Obsidian"], home=tmp_path) == sub

    def test_detects_markdown_in_place(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("VAULT_PATH", raising=False)
        vault = tmp_path / "Notes"
        vault.mkdir()
        (vault / "a.md").write_text("# a", encoding="utf-8")
        assert detect_vault(["~/Notes"], home=tmp_path) == vault

    def test_none_when_nothing_matches(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("VAULT_PATH", raising=False)
        assert detect_vault(["~/Obsidian", "~/vault"], home=tmp_path) is None


# ── Backend probing (mocked HTTP) ───────────────────────────────────────────────
class TestProbeBackends:
    def test_finds_a_running_backend(self, llm_server) -> None:
        base = llm_server(("local-chat", "text-embedding-nomic-embed-text-v1.5"))
        endpoints = probe_backends(
            [("LM Studio", base, "/v1/models")], timeout=2.0
        )
        assert len(endpoints) == 1
        assert endpoints[0].base_url == base
        assert "text-embedding-nomic-embed-text-v1.5" in endpoints[0].models

    def test_unreachable_is_skipped(self) -> None:
        # An almost-certainly-closed port — connection refused → empty result.
        endpoints = probe_backends(
            [("LM Studio", "http://127.0.0.1:9", "/v1/models")], timeout=0.5
        )
        assert endpoints == []

    def test_dedupes_by_host_port(self, llm_server) -> None:
        base = llm_server(("m1",))
        endpoints = probe_backends(
            [("LM Studio", base, "/v1/models"), ("Other", base, "/api/tags")],
            timeout=2.0,
        )
        assert len(endpoints) == 1

    def test_embedding_models_filter(self) -> None:
        ep = Endpoint(
            label="LM Studio", base_url="http://x", host="x", port=1,
            models=("chat-7b", "text-embedding-foo", "nomic-embed-bar"),
        )
        assert embedding_models(ep) == ["text-embedding-foo", "nomic-embed-bar"]


# ── Config generation ────────────────────────────────────────────────────────────
class TestBuildConfig:
    def test_minimal_config(self, tmp_path: Path) -> None:
        doc = build_config(
            vault_path=tmp_path / "v", endpoint=None, embed_model=None,
            profile=Profile(),
        )
        assert doc["vault_path"] == str(tmp_path / "v")
        assert "backend" not in doc  # nothing detected
        assert "profile" not in doc  # empty profile omitted
        assert doc["memory"] == config.DEFAULT_MEMORY

    def test_full_config(self, tmp_path: Path) -> None:
        ep = Endpoint(
            label="LM Studio", base_url="http://localhost:5555",
            host="localhost", port=5555, models=("m",),
        )
        doc = build_config(
            vault_path=tmp_path, endpoint=ep, embed_model="text-embedding-x",
            profile=Profile(name="Paul", role="founder", style="terse"),
        )
        assert doc["backend"]["port"] == 5555
        assert doc["backend"]["embed_model"] == "text-embedding-x"
        assert doc["profile"]["name"] == "Paul"
        assert doc["memory"]["decay_lambda"] == config.DEFAULT_MEMORY["decay_lambda"]

    def test_write_and_reload_roundtrips(self, tmp_path: Path) -> None:
        doc = build_config(
            vault_path=tmp_path, endpoint=None, embed_model=None, profile=Profile(),
        )
        path = setup_wizard.write_config(doc, tmp_path / ".eidetic" / "config.yaml")
        assert path.is_file()
        assert config.load_config(path) == doc


# ── Selection helpers ────────────────────────────────────────────────────────────
class TestSelection:
    def _ep(self, *models: str) -> Endpoint:
        return Endpoint(
            label="LM Studio", base_url="http://x", host="x", port=1, models=models,
        )

    def test_single_model_auto_selected(self) -> None:
        ep = self._ep("chat", "text-embedding-only")
        assert select_embedding_model(
            RecordingUI(), ep, interactive=True
        ) == "text-embedding-only"

    def test_non_interactive_takes_first(self) -> None:
        ep = self._ep("text-embedding-a", "text-embedding-b")
        assert select_embedding_model(
            RecordingUI(), ep, interactive=False
        ) == "text-embedding-a"

    def test_interactive_uses_selector(self) -> None:
        ep = self._ep("text-embedding-a", "text-embedding-b")
        picked = select_embedding_model(
            RecordingUI(), ep, interactive=True,
            select=lambda q, opts, default: 1,  # choose the second
        )
        assert picked == "text-embedding-b"

    def test_no_embedding_models_returns_none(self) -> None:
        assert select_embedding_model(RecordingUI(), self._ep("chat"), interactive=True) is None


class TestProfile:
    def test_non_interactive_is_empty(self) -> None:
        assert collect_profile(RecordingUI(), interactive=False).is_empty

    def test_declined_is_empty(self) -> None:
        prof = collect_profile(
            RecordingUI(), interactive=True,
            confirm=lambda q, default: False,
        )
        assert prof.is_empty

    def test_collected_profile(self) -> None:
        answers = iter(["Paul", "Founder", "terse"])
        prof = collect_profile(
            RecordingUI(), interactive=True,
            confirm=lambda q, default: True,
            prompt=lambda q, default: next(answers),
        )
        assert prof == Profile(name="Paul", role="Founder", style="terse")


# ── Full flow ────────────────────────────────────────────────────────────────────
class TestRunWizard:
    def test_full_flow_with_scripted_input(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EIDETIC_CONFIG_PATH", str(tmp_path / ".eidetic" / "config.yaml"))
        ui = RecordingUI()
        vault = tmp_path / "myvault"
        ep = Endpoint(
            label="LM Studio", base_url="http://localhost:5555",
            host="localhost", port=5555,
            models=("chat", "text-embedding-a", "text-embedding-b"),
        )
        prompts = iter([str(vault), "Paul", "Founder", "terse"])
        result = run_wizard(
            version="4.0.0",
            interactive=True,
            ui=ui,
            prompt=lambda q, default: next(prompts),
            confirm=lambda q, default: True,  # yes to profile
            select=lambda q, opts, default: 1,  # second embedding model
            probe=lambda: [ep],
        )

        assert result.vault_path == vault.resolve()
        assert result.embed_model == "text-embedding-b"
        assert result.profile == Profile(name="Paul", role="Founder", style="terse")
        # Config was written to the EIDETIC_CONFIG_PATH location.
        written = config.load_config()
        assert written["backend"]["base_url"] == "http://localhost:5555"
        assert written["profile"]["name"] == "Paul"
        assert written["memory"]["reinforcement_beta"] == config.DEFAULT_MEMORY["reinforcement_beta"]
        assert "banner:4.0.0" in ui.lines

    def test_non_interactive_no_backend(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EIDETIC_CONFIG_PATH", str(tmp_path / ".eidetic" / "config.yaml"))
        result = run_wizard(
            version="4.0.0",
            vault=tmp_path / "v",
            interactive=False,
            ui=RecordingUI(),
            probe=lambda: [],
            write=False,
        )
        assert result.endpoint is None
        assert result.embed_model is None
        assert result.profile.is_empty
        # write=False → nothing on disk.
        assert not (tmp_path / ".eidetic" / "config.yaml").exists()


# ── UI fallback ──────────────────────────────────────────────────────────────────
class TestUI:
    def test_plain_ui_emits_lines(self) -> None:
        captured: list[str] = []
        ui = setup_wizard.PlainUI(echo=captured.append)
        ui.banner("4.0.0")
        ui.success("done")
        assert any("4.0.0" in line for line in captured)
        assert any("done" in line for line in captured)

    def test_make_ui_returns_something_usable(self) -> None:
        ui = setup_wizard.make_ui(plain=True)
        assert isinstance(ui, setup_wizard.PlainUI)
