#!/usr/bin/env python3
"""
Atlas OS System Health Check
============================

Probes every Atlas OS subsystem and prints a status report. Intended to be
invoked from the `weekly-system-health-check` scheduled task, or run manually.

Uses *endpoint-aware* probes: each HTTP service has a known-good URL and an
`accept` range. Anything in the accept range is "up"; anything outside (or a
connection error / timeout) is "down". This avoids false negatives for backends
whose root path returns 404 by design.

Configuration is read from the environment — no hardcoded hosts, paths, or
addresses. See `.env.example`.

Environment variables:
    VAULT_PATH        Absolute path to the vault (required)
    RAG_DIR           Vector store dir       (default: $VAULT_PATH/.rag)
    SCHEDULED_DIR     Scheduled tasks dir    (default: ~/Documents/Claude/Scheduled)
    EMBED_HOST        Embeddings host        (default: localhost)
    EMBED_PORT        Embeddings port        (default: 5555)
    TTS_HOST          TTS host               (default: localhost)
    TTS_PORT          TTS port               (default: 8800)
    DASHBOARD_FRONTEND_PORT   (default: 3000)
    DASHBOARD_BACKEND_PORT    (default: 5001)

Usage:
    python3 health_check.py             # human-readable report
    python3 health_check.py --json      # machine-readable JSON
    python3 health_check.py --quiet     # exit code only (0 = all up)
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Callable
from urllib import request, error

from _bootstrap import ensure_atlas_os

ensure_atlas_os()
from atlas_os import scriptkit  # noqa: E402

VAULT = Path(os.path.expanduser(os.environ.get("VAULT_PATH", "."))).resolve()
RAG_DIR = Path(os.path.expanduser(os.environ.get("RAG_DIR", str(VAULT / ".rag"))))
SCHEDULED_DIR = Path(os.path.expanduser(
    os.environ.get("SCHEDULED_DIR", "~/Documents/Claude/Scheduled")
))

TTS_HOST   = os.environ.get("TTS_HOST", "localhost")
TTS_PORT   = os.environ.get("TTS_PORT", "8800")
FRONTEND_PORT = os.environ.get("DASHBOARD_FRONTEND_PORT", "3000")
BACKEND_PORT  = os.environ.get("DASHBOARD_BACKEND_PORT", "5001")


# ─────────────────────────────────────────────────────────── helpers ──────────


def probe_http(url: str, accept: range = range(200, 500), timeout: float = 3.0) -> tuple[bool, str]:
    """Return (is_up, detail). Treats any status in `accept` as up."""
    try:
        req = request.Request(url, method="GET")
        with request.urlopen(req, timeout=timeout) as r:
            code = r.status
            return (code in accept, f"HTTP {code}")
    except error.HTTPError as e:
        return (e.code in accept, f"HTTP {e.code}")
    except (error.URLError, socket.timeout, ConnectionError, TimeoutError) as e:
        return (False, f"unreachable: {type(e).__name__}")


def probe_path(path: Path, max_age_hours: float | None = None) -> tuple[bool, str]:
    if not path.exists():
        return (False, f"missing: {path}")
    if max_age_hours is None:
        return (True, "exists")
    age_h = (time.time() - path.stat().st_mtime) / 3600
    fresh = age_h <= max_age_hours
    return (fresh, f"age {age_h:.1f}h (limit {max_age_hours}h)")


# ─────────────────────────────────────────────────── status records ───────────


@dataclass
class Result:
    name: str
    status: str  # "up" | "degraded" | "down"
    detail: str = ""
    checks: list[dict] = field(default_factory=list)

    @property
    def icon(self) -> str:
        return {"up": "✅", "degraded": "⚠️ ", "down": "❌"}.get(self.status, "·")


def combine(name: str, checks: list[tuple[str, bool, str]]) -> Result:
    up_count = sum(1 for _, ok, _ in checks if ok)
    if up_count == len(checks):
        status = "up"
    elif up_count == 0:
        status = "down"
    else:
        status = "degraded"
    return Result(
        name=name,
        status=status,
        detail=f"{up_count}/{len(checks)} checks passed",
        checks=[{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    )


# ─────────────────────────────────────────────────────────── checks ──────────


def check_vault() -> Result:
    md_count = len(list(VAULT.rglob("*.md")))
    files = [
        VAULT / ".claude-index.md",
        VAULT / "wiki" / "index.md",
        VAULT / "wiki" / "hot.md",
        VAULT / "wiki" / "log.md",
    ]
    checks = [(f"{md_count} markdown files", md_count > 0, f"{md_count}")]
    for f in files:
        ok, d = probe_path(f, max_age_hours=24 * 14)
        checks.append((f.name, ok, d))
    return combine("Vault", checks)


def _try_import_backends():
    """Import ``atlas_os.backends`` (adding the repo root to sys.path if needed)."""
    try:
        from atlas_os import backends
        return backends
    except ImportError:
        pass
    for parent in Path(__file__).resolve().parents:
        if (parent / "atlas_os" / "__init__.py").exists():
            sys.path.insert(0, str(parent))
            break
    try:
        from atlas_os import backends
        return backends
    except ImportError:
        return None


def _embeddings_models_url() -> tuple[str, str]:
    """Resolve ``(models_url, label)`` for the embeddings backend.

    Explicit ``EMBED_*`` env wins; otherwise auto-detect a running backend so the
    health report reflects whichever of LM Studio / Ollama / llama.cpp is up.
    """
    url = os.environ.get("EMBED_URL")
    if url:
        base = url.rsplit("/v1/", 1)[0]
        return f"{base}/v1/models", base.split("://", 1)[-1]
    host = os.environ.get("EMBED_HOST")
    port = os.environ.get("EMBED_PORT")
    if host or port:
        host = host or "localhost"
        port = port or "5555"
        return f"http://{host}:{port}/v1/models", f"{host}:{port}"
    backends = _try_import_backends()
    if backends is not None:
        backend = backends.detect_backend()
        if backend is not None:
            return backend.models_url, f"{backend.label} {backend.base_url}"
    return "http://localhost:5555/v1/models", "localhost:5555"


def check_rag() -> Result:
    vectors = RAG_DIR / "vectors.json"
    last_embed = RAG_DIR / "last_embed.txt"
    lm_url, lm_label = _embeddings_models_url()
    lm_ok, lm_detail = probe_http(lm_url, timeout=3.0)
    p_ok, p_detail = probe_path(vectors)
    if p_ok:
        size_mb = vectors.stat().st_size / 1024 / 1024
        p_detail = f"{vectors.name} {size_mb:.1f} MB"
    return combine(
        "RAG Pipeline",
        [
            ("vectors file", p_ok, p_detail),
            ("last_embed.txt", *probe_path(last_embed, max_age_hours=24 * 7)),
            (f"embeddings @ {lm_label}", lm_ok, lm_detail),
        ],
    )


def check_tts() -> Result:
    ok, d = probe_http(f"http://{TTS_HOST}:{TTS_PORT}/", accept=range(200, 500), timeout=3.0)
    return combine(f"TTS ({TTS_HOST}:{TTS_PORT})", [("root", ok, d)])


def check_email() -> Result:
    sender = Path(__file__).parent / "send_email.py"
    pw_present = bool(os.environ.get("SMTP_APP_PASSWORD"))
    return combine(
        "Email (SMTP)",
        [
            ("send_email.py", *probe_path(sender)),
            ("SMTP_APP_PASSWORD env", pw_present, "set" if pw_present else "not set"),
        ],
    )


def check_git() -> Result:
    git_dir = VAULT / ".git"
    checks: list[tuple[str, bool, str]] = []
    # Detect any stale git lock (index.lock / HEAD.lock / ref locks) — each one
    # blocks the next git operation until cleared.
    present_locks = [
        name for name in ("index.lock", "HEAD.lock")
        if (git_dir / name).exists()
    ]
    if (git_dir / "refs").is_dir():
        present_locks.extend(str(p.relative_to(git_dir)) for p in (git_dir / "refs").rglob("*.lock"))
    if present_locks:
        checks.append(("git locks", False, f"stale: {', '.join(present_locks)}"))
    else:
        checks.append(("git locks", True, "none"))
    r = subprocess.run(
        ["git", "-C", str(VAULT), "status", "--porcelain"],
        capture_output=True, text=True, timeout=10,
    )
    dirty_count = len([line for line in r.stdout.splitlines() if line.strip()])
    checks.append(("working tree", dirty_count == 0, f"{dirty_count} changed paths"))
    r2 = subprocess.run(
        ["git", "-C", str(VAULT), "log", "-1", "--format=%h %s"],
        capture_output=True, text=True, timeout=10,
    )
    checks.append(("last commit", r2.returncode == 0, r2.stdout.strip()[:80]))
    return combine("Git", checks)


def check_scheduled() -> Result:
    if not SCHEDULED_DIR.exists():
        return combine("Scheduled Tasks", [("dir", False, "missing")])
    tasks = [p for p in SCHEDULED_DIR.iterdir() if p.is_dir() and (p / "SKILL.md").exists()]
    return combine(
        "Scheduled Tasks",
        [
            ("dir", True, str(SCHEDULED_DIR)),
            ("SKILL.md files", len(tasks) >= 1, f"{len(tasks)} tasks"),
        ],
    )


def check_dashboard() -> Result:
    fe_ok, fe_d = probe_http(f"http://localhost:{FRONTEND_PORT}/", accept=range(200, 500))
    be_root_ok, be_root_d = probe_http(f"http://localhost:{BACKEND_PORT}/", accept=range(200, 500))
    be_api_ok, be_api_d = probe_http(f"http://localhost:{BACKEND_PORT}/api/health", accept=range(200, 300))
    return combine(
        "Dashboard",
        [
            (f"frontend :{FRONTEND_PORT}", fe_ok, fe_d),
            (f"backend :{BACKEND_PORT} root", be_root_ok, be_root_d),
            ("backend api (/api/health)", be_api_ok, be_api_d),
        ],
    )


def check_schemas() -> Result:
    schemas = VAULT / ".schemas"
    enforce = Path(__file__).parent.parent / "schemas" / "enforce_schemas.py"
    return combine(
        "Frontmatter Schemas",
        [
            (".schemas/", *probe_path(schemas)),
            ("enforce_schemas.py", *probe_path(enforce)),
        ],
    )


def check_wiki() -> Result:
    wiki = VAULT / "wiki"
    return combine(
        "Wiki System",
        [
            ("wiki/", *probe_path(wiki)),
            ("wiki/index.md", *probe_path(wiki / "index.md", max_age_hours=24 * 14)),
            ("wiki/hot.md", *probe_path(wiki / "hot.md", max_age_hours=24 * 14)),
            ("wiki/log.md", *probe_path(wiki / "log.md", max_age_hours=24 * 14)),
        ],
    )


# ───────────────────────────────────────────────────────────── main ──────────

CHECKS: list[tuple[str, Callable[[], Result]]] = [
    ("vault", check_vault),
    ("rag", check_rag),
    ("tts", check_tts),
    ("email", check_email),
    ("git", check_git),
    ("scheduled", check_scheduled),
    ("dashboard", check_dashboard),
    ("schemas", check_schemas),
    ("wiki", check_wiki),
]


def run_all() -> list[Result]:
    return [fn() for _, fn in CHECKS]


def format_human(results: list[Result]) -> str:
    lines = ["Atlas OS Health Check — " + time.strftime("%Y-%m-%d %H:%M:%S")]
    lines.append("=" * 60)
    for r in results:
        lines.append(f"{r.icon} {r.name:<32} {r.status.upper():<9} {r.detail}")
        for c in r.checks:
            mark = "  ✓" if c["ok"] else "  ✗"
            lines.append(f"   {mark} {c['name']:<28} {c['detail']}")
    up = sum(1 for r in results if r.status == "up")
    deg = sum(1 for r in results if r.status == "degraded")
    down = sum(1 for r in results if r.status == "down")
    lines.append("-" * 60)
    lines.append(f"Summary: {up} up · {deg} degraded · {down} down")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--quiet", action="store_true", help="suppress output; exit code only")
    args = ap.parse_args()

    results = run_all()
    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2))
    elif not args.quiet:
        print(format_human(results))

    return 0 if all(r.status != "down" for r in results) else 1


if __name__ == "__main__":
    with scriptkit.error_boundary(json_mode=scriptkit.json_mode_requested()):
        sys.exit(main())
