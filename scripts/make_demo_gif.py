#!/usr/bin/env python3
"""Render the hero animated terminal demo (``demo.gif``) for the Eidetic OS README.

One continuous, scrolling terminal session that walks the whole headline
workflow — install, initialise, health-check, search, embed, and launch the
dashboard — so a first-time visitor sees what Eidetic OS does in ~25 seconds:

    pip install eidetic-os   →  eidetic init   →  eidetic doctor
    eidetic search "…"       →  eidetic embed --incremental
    eidetic dashboard

Pure synthetic output (no personal data); the shared look lives in
``scripts/_gif_lib.py``. Pillow only.

    python3 scripts/make_demo_gif.py            # writes demo.gif in the repo root
"""

from __future__ import annotations

from pathlib import Path

from _gif_lib import (
    BLUE,
    BOLD_W,
    CYAN,
    DIM,
    FG,
    GREEN,
    PINK,
    PURPLE,
    YELLOW,
    Builder,
    L,
    S,
    ok,
)


def banner(b: Builder) -> None:
    """A purple Eidetic OS wordmark + tagline at the top of the session."""
    b.reveal(
        L(
            S("  ◆ EIDETIC OS ", PURPLE, bold=True),
            S("v4.0.0", CYAN, bold=True),
            S("  ·  ", DIM),
            S("Your AI Never Forgets", BOLD_W),
        )
    )
    b.reveal(L(S("  local-first memory + hybrid RAG for Claude", DIM)))
    b.blank()


def scene_install(b: Builder) -> None:
    b.cmd("pip install eidetic-os")
    b.reveal(L(S("Collecting eidetic-os", FG)))
    b.hold(280)
    b.bar("Downloading eidetic_os-4.0.0-py3-none-any.whl (62 kB)", 62.0,
          unit="kB", steps=26)
    b.spin("Resolving dependencies (typer, pydantic, sqlite-vec)…",
           "12 dependencies satisfied")
    b.reveal(L(S("Successfully installed eidetic-os-4.0.0", GREEN, bold=True)))
    b.hold(700)
    b.blank()


def scene_init(b: Builder) -> None:
    b.cmd("eidetic init")
    b.reveal(L(S("  ▲  Eidetic OS — setup wizard", CYAN, bold=True)))
    b.blank()
    b.spin("Detecting local LLM backends…", "LM Studio @ localhost:5555 (qwen2.5)")
    b.reveal(ok(S("Ollama @ localhost:11434 ", FG), S("(llama3.2)", DIM)))
    b.reveal(ok(S("Embeddings: ", FG), S("nomic-embed-text · 768-dim", DIM)))
    b.spin("Scaffolding the vault…", "created .eidetic/ · .rag/ · wiki/")
    b.reveal(ok(S("Wrote ~/vault/.env ", FG), S("(14 keys)", DIM)))
    b.reveal(ok(S("Initialised vault git repo", FG)))
    b.reveal(L(S("  ✓ You're ready!", GREEN, bold=True)))
    b.hold(900)
    b.blank()


def _chk(name: str, detail: str) -> L:
    return ok(S(f"{name:<13}", FG), S(detail, DIM))


def scene_doctor(b: Builder) -> None:
    b.cmd("eidetic doctor")
    b.reveal(_chk("config", ".env · 14 keys loaded"))
    b.reveal(_chk("vault git", "clean · 3 commits"))
    b.reveal(_chk("llm", "LM Studio :5555 reachable"))
    b.reveal(_chk("embeddings", "nomic-embed-text · 768-dim"))
    b.reveal(_chk("vector store", "21,438 chunks · sqlite-vec"))
    b.reveal(_chk("rag", "hybrid BM25 + vector + RRF"))
    b.reveal(_chk("smtp", "smtp.gmail.com:587 configured"))
    b.reveal(L(S("  14 OK", GREEN, bold=True), S("  ·  ", DIM),
               S("0 WARN", DIM), S("  ·  ", DIM), S("0 FAIL", DIM)))
    b.hold(1100)
    b.blank()


def _result(score: str, path: str, heading: str, snippet: str) -> list[L]:
    return [
        L(S(f"  [{score}] ", YELLOW), S(path, BLUE), S(f"  › {heading}", PINK)),
        L(S(f"         {snippet}", DIM)),
        L(),
    ]


def scene_search(b: Builder) -> None:
    b.cmd('eidetic search "authentication architecture"')
    b.reveal(L(S("Searching ", FG), S("21,438", BOLD_W, bold=True),
               S(" chunks across ", FG), S("463", BOLD_W, bold=True),
               S(" files…", FG)))
    b.blank()
    b.hold(650)
    for ln in _result("0.91", "wiki/auth/oauth-design.md", "Token flow",
                      '"Short-lived access tokens + rotating refresh tokens behind…"'):
        b.reveal(ln)
    b.hold(450)
    for ln in _result("0.86", "wiki/sources/zero-trust.md", "Service identity",
                      '"mTLS between services; every call is authenticated and…"'):
        b.reveal(ln)
    b.hold(450)
    for ln in _result("0.79", "session-logs/2026-05-31.md", "Decision",
                      '"Chose JWT + JWKS rotation over opaque tokens for the…"'):
        b.reveal(ln)
    b.reveal(L(S("  3 results ", BOLD_W, bold=True),
               S("· hybrid BM25 + vector + RRF · 0.21s", DIM)))
    b.hold(1200)
    b.blank()


def scene_embed(b: Builder) -> None:
    b.cmd("eidetic embed --incremental")
    b.spin("Scanning the vault for changes…", "18 new · 7 modified · 0 deleted")
    b.bar("Embedding 25 changed chunks (nomic-embed-text)", 25.0,
          unit="chunks", steps=25, color=CYAN, frame_ms=34)
    b.reveal(ok(S("Index updated → ", FG), S("21,463", BOLD_W, bold=True),
                S(" chunks · sqlite-vec", FG)))
    b.hold(800)
    b.blank()


def scene_dashboard(b: Builder) -> None:
    b.cmd("eidetic dashboard")
    b.reveal(L(S("  ▲  Eidetic OS Dashboard", CYAN, bold=True)))
    b.spin("Starting local Flask server…", "bound to 127.0.0.1:8501")
    b.reveal(L(S("  panels: ", DIM),
               S("Health Audit Tasks Skills Vectors RAG Graph", BOLD_W)))
    b.blank()
    b.reveal(L(S("  ➜ Dashboard running at ", GREEN, bold=True),
               S("http://localhost:8501", BLUE)))
    b.hold(1700)


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    out = repo_root / "demo.gif"

    b = Builder()
    banner(b)
    header = b.snapshot()  # purple wordmark stays pinned at the top of every scene

    for scene in (
        scene_install,
        scene_init,
        scene_doctor,
        scene_search,
        scene_embed,
        scene_dashboard,
    ):
        b.reset_to(header)
        scene(b)
    b.end_prompt(1400)

    b.save(out)
    print(
        f"demo.gif         {len(b.frames):>4} frames · "
        f"{b.total_ms / 1000:>5.1f}s · {out.stat().st_size / 1024:>6.0f} KB"
    )


if __name__ == "__main__":
    main()
