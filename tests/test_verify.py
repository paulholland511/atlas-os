"""Tests for the structured verification gates (``eidetic_os.verify``).

The five tiers — syntax, imports, tests, runtime, diff — are exercised both in
isolation and as a full pipeline. Blocking behaviour (the pipeline halts at the
first blocking gate that fails) gets its own coverage, as does JSON output and
the ``eidetic verify`` CLI surface.

All tests are hermetic: code is written into ``tmp_path`` and the audit log is
redirected to a temp file via ``EIDETIC_AUDIT_PATH`` so nothing touches the real
vault.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from eidetic_os import verify
from eidetic_os.cli import app
from eidetic_os.verify import Tier

runner = CliRunner()


# ── helpers ───────────────────────────────────────────────────────────────────
def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _isolated_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the audit trail at a throwaway file for every test in this module."""
    monkeypatch.setenv("EIDETIC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))


def _result(report: verify.VerificationReport, tier: Tier) -> verify.TierResult:
    return next(r for r in report.tiers if r.tier is tier)


# ══════════════════════════════════════════════════════════════════════════════
# Tier selection / parsing
# ══════════════════════════════════════════════════════════════════════════════
def test_parse_tiers_orders_and_dedupes() -> None:
    assert verify.parse_tiers("imports, syntax, imports") == (Tier.SYNTAX, Tier.IMPORTS)


def test_parse_tiers_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown tier"):
        verify.parse_tiers("syntax,bogus")


def test_parse_tiers_rejects_empty() -> None:
    with pytest.raises(ValueError, match="no tiers"):
        verify.parse_tiers("  ,  ")


# ══════════════════════════════════════════════════════════════════════════════
# SYNTAX tier
# ══════════════════════════════════════════════════════════════════════════════
def test_syntax_tier_passes_on_valid_code(tmp_path: Path) -> None:
    src = _write(tmp_path / "ok.py", "x = 1 + 1\n")
    report = verify.verify(src, tiers=[Tier.SYNTAX], log=False)
    assert report.passed
    assert _result(report, Tier.SYNTAX).passed


def test_syntax_tier_blocks_on_parse_error(tmp_path: Path) -> None:
    src = _write(tmp_path / "broken.py", "def oops(:\n")
    report = verify.verify(src, tiers=[Tier.SYNTAX], log=False)
    assert not report.passed
    assert report.blocked_at == "syntax"
    syntax = _result(report, Tier.SYNTAX)
    assert not syntax.passed and syntax.blocking


# ══════════════════════════════════════════════════════════════════════════════
# IMPORTS tier
# ══════════════════════════════════════════════════════════════════════════════
def test_imports_tier_passes_on_stdlib_only(tmp_path: Path) -> None:
    src = _write(tmp_path / "clean.py", "import json\nimport os\nprint(json.dumps({}))\n")
    report = verify.verify(src, tiers=[Tier.IMPORTS], log=False)
    assert report.passed


def test_imports_tier_blocks_on_dangerous_call(tmp_path: Path) -> None:
    src = _write(tmp_path / "danger.py", "import os\nos.system('whoami')\n")
    report = verify.verify(src, tiers=[Tier.IMPORTS], log=False)
    assert not report.passed
    imports = _result(report, Tier.IMPORTS)
    assert imports.blocking
    blocks = imports.data["blocks"]
    assert isinstance(blocks, list) and blocks


def test_imports_tier_blocks_on_missing_dependency(tmp_path: Path) -> None:
    src = _write(tmp_path / "needs.py", "import totally_not_a_real_pkg_xyz\n")
    report = verify.verify(src, tiers=[Tier.IMPORTS], log=False)
    assert not report.passed
    imports = _result(report, Tier.IMPORTS)
    assert imports.blocking
    assert "totally_not_a_real_pkg_xyz" in imports.data["missing_imports"]


def test_imports_tier_ignores_local_sibling_modules(tmp_path: Path) -> None:
    _write(tmp_path / "helper.py", "VALUE = 1\n")
    src = _write(tmp_path / "main.py", "import helper\nprint(helper.VALUE)\n")
    report = verify.verify(src, tiers=[Tier.IMPORTS], log=False)
    assert report.passed  # `helper` is a sibling, not a missing dependency.


# ══════════════════════════════════════════════════════════════════════════════
# TESTS tier
# ══════════════════════════════════════════════════════════════════════════════
def test_tests_tier_skips_when_no_tests(tmp_path: Path) -> None:
    src = _write(tmp_path / "lib.py", "def add(a, b):\n    return a + b\n")
    report = verify.verify(src, tiers=[Tier.TESTS], log=False)
    assert report.passed
    assert _result(report, Tier.TESTS).data["found"] is False


def test_tests_tier_passes_when_tests_pass(tmp_path: Path) -> None:
    _write(tmp_path / "calc.py", "def add(a, b):\n    return a + b\n")
    _write(
        tmp_path / "test_calc.py",
        """
        from calc import add

        def test_add():
            assert add(1, 2) == 3
        """,
    )
    report = verify.verify(tmp_path / "calc.py", tiers=[Tier.TESTS], log=False)
    assert report.passed
    counts = _result(report, Tier.TESTS).data["counts"]
    assert isinstance(counts, dict) and counts["passed"] == 1


def test_tests_tier_fails_but_does_not_block(tmp_path: Path) -> None:
    _write(tmp_path / "calc.py", "def add(a, b):\n    return a + b\n")
    _write(
        tmp_path / "test_calc.py",
        """
        from calc import add

        def test_add():
            assert add(1, 2) == 999
        """,
    )
    report = verify.verify(tmp_path / "calc.py", tiers=[Tier.TESTS], log=False)
    assert not report.passed
    tests = _result(report, Tier.TESTS)
    assert not tests.passed
    assert not tests.blocking  # failing tests are reported, not gated
    assert report.blocked_at is None


# ══════════════════════════════════════════════════════════════════════════════
# RUNTIME tier
# ══════════════════════════════════════════════════════════════════════════════
def test_runtime_tier_passes_on_clean_exit(tmp_path: Path) -> None:
    src = _write(tmp_path / "hello.py", "print('hello from sandbox')\n")
    report = verify.verify(src, tiers=[Tier.RUNTIME], log=False)
    assert report.passed
    runtime = _result(report, Tier.RUNTIME)
    assert runtime.data["exit_code"] == 0


def test_runtime_tier_blocks_on_nonzero_exit(tmp_path: Path) -> None:
    src = _write(tmp_path / "boom.py", "import sys\nsys.exit(3)\n")
    report = verify.verify(src, tiers=[Tier.RUNTIME], log=False)
    assert not report.passed
    runtime = _result(report, Tier.RUNTIME)
    assert runtime.blocking
    assert runtime.data["exit_code"] == 3


def test_runtime_tier_blocks_on_timeout(tmp_path: Path) -> None:
    src = _write(tmp_path / "slow.py", "import time\ntime.sleep(10)\n")
    report = verify.verify(src, tiers=[Tier.RUNTIME], runtime_timeout=1, log=False)
    assert not report.passed
    runtime = _result(report, Tier.RUNTIME)
    assert runtime.blocking
    assert runtime.data["timed_out"] is True


# ══════════════════════════════════════════════════════════════════════════════
# DIFF tier
# ══════════════════════════════════════════════════════════════════════════════
def test_diff_tier_skips_outside_git_repo(tmp_path: Path) -> None:
    src = _write(tmp_path / "loose.py", "x = 1\n")
    report = verify.verify(src, tiers=[Tier.DIFF], log=False)
    assert report.passed
    assert _result(report, Tier.DIFF).data["git"] is False


# ══════════════════════════════════════════════════════════════════════════════
# Full pipeline + blocking behaviour
# ══════════════════════════════════════════════════════════════════════════════
def test_full_pipeline_passes_on_clean_file(tmp_path: Path) -> None:
    src = _write(tmp_path / "good.py", "import json\nprint(json.dumps({'ok': True}))\n")
    report = verify.verify(src, log=False)
    ran = {r.tier for r in report.tiers}
    assert ran == set(Tier)  # all five gates ran
    assert report.passed
    assert report.blocked_at is None


def test_pipeline_stops_at_first_blocking_failure(tmp_path: Path) -> None:
    # A syntax error must halt before the imports gate ever runs.
    src = _write(tmp_path / "broken.py", "def oops(:\n")
    report = verify.verify(src, log=False)
    assert report.blocked_at == "syntax"
    assert [r.tier for r in report.tiers] == [Tier.SYNTAX]  # nothing after syntax ran


def test_pipeline_imports_block_skips_runtime(tmp_path: Path) -> None:
    # Dangerous code blocks at IMPORTS; RUNTIME must never execute it.
    src = _write(tmp_path / "danger.py", "import os\nos.system('echo pwned')\n")
    report = verify.verify(src, log=False)
    assert report.blocked_at == "imports"
    tiers_run = [r.tier for r in report.tiers]
    assert Tier.RUNTIME not in tiers_run
    assert tiers_run == [Tier.SYNTAX, Tier.IMPORTS]


# ══════════════════════════════════════════════════════════════════════════════
# JSON output + audit logging
# ══════════════════════════════════════════════════════════════════════════════
def test_report_to_json_round_trips(tmp_path: Path) -> None:
    src = _write(tmp_path / "ok.py", "x = 1\n")
    report = verify.verify(src, tiers=[Tier.SYNTAX], log=False)
    payload = json.loads(report.to_json())
    assert payload["passed"] is True
    assert payload["target"].endswith("ok.py")
    assert payload["tiers"][0]["tier"] == "syntax"
    assert "duration_ms" in payload["tiers"][0]


def test_verify_appends_audit_entry(tmp_path: Path) -> None:
    from eidetic_os import audit

    src = _write(tmp_path / "ok.py", "x = 1\n")
    verify.verify(src, tiers=[Tier.SYNTAX])  # log=True (default)
    entries = audit.read_audit(action="verify")
    assert entries
    assert entries[-1]["status"] == "success"


def test_verify_raises_on_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        verify.verify(tmp_path / "nope.py", log=False)


# ══════════════════════════════════════════════════════════════════════════════
# CLI surface
# ══════════════════════════════════════════════════════════════════════════════
def test_cli_verify_passes(tmp_path: Path) -> None:
    src = _write(tmp_path / "ok.py", "import json\nprint(json.dumps({}))\n")
    result = runner.invoke(app, ["verify", str(src), "--tier", "syntax,imports"])
    assert result.exit_code == 0
    assert "PASS" in result.stdout


def test_cli_verify_fails_with_exit_1(tmp_path: Path) -> None:
    src = _write(tmp_path / "broken.py", "def oops(:\n")
    result = runner.invoke(app, ["verify", str(src)])
    assert result.exit_code == 1
    assert "FAIL" in result.stdout


def test_cli_verify_json_output(tmp_path: Path) -> None:
    src = _write(tmp_path / "ok.py", "x = 1\n")
    result = runner.invoke(app, ["verify", str(src), "--tier", "syntax", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True


def test_cli_verify_unknown_tier_errors(tmp_path: Path) -> None:
    src = _write(tmp_path / "ok.py", "x = 1\n")
    result = runner.invoke(app, ["verify", str(src), "--tier", "nope"])
    assert result.exit_code == 2


def test_cli_verify_missing_path_errors() -> None:
    result = runner.invoke(app, ["verify", "/nonexistent/path/xyz.py"])
    assert result.exit_code == 2
