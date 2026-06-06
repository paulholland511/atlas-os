#!/usr/bin/env python3
"""Render the per-topic animated terminal GIFs for the Eidetic OS README and docs.

Six focused screencasts that supplement the headline ``demo.gif``:

    install.gif      pip install → eidetic init → eidetic doctor (all green)
    setup.gif        the interactive `eidetic init` wizard, with typed answers
    search.gif       hybrid RAG search — BM25 + vector + RRF fusion, scored hits
    dashboard.gif    `eidetic dashboard` launch + panel list
    skills.gif       `eidetic skills` catalog, a sandboxed run, and `mcp serve`
    extensions.gif   install an extra, discover extensions, run `eidetic trading`

Shares the look of the hero demo via ``scripts/_gif_lib.py`` (macOS terminal
chrome, Menlo, typewriter prompts, supersampled text). Pure synthetic output —
no personal data — Pillow only.

    python3 scripts/make_doc_gifs.py            # writes the six GIFs in repo root
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
    warn,
)


# ── 1. install.gif ────────────────────────────────────────────────────────────
def build_install() -> Builder:
    b = Builder()
    b.cmd("pip install eidetic-os")
    b.reveal(L(S("Collecting eidetic-os", FG)))
    b.hold(280)
    b.bar("Downloading eidetic_os-4.0.0-py3-none-any.whl (62 kB)", 62.0,
          unit="kB", steps=26)
    b.spin("Installing collected packages…", "eidetic-os-4.0.0")
    b.reveal(L(S("Successfully installed eidetic-os-4.0.0", GREEN, bold=True)))
    b.hold(1100)

    b.clear()
    b.cmd("eidetic init")
    b.spin("Detecting vault + local LLM backends…",
           "LM Studio @ :5555 · vault @ ~/vault")
    b.reveal(ok(S("Scaffolded .eidetic/ · .rag/ · wiki/", FG)))
    b.reveal(ok(S("Wrote ~/vault/.env ", FG), S("(14 keys)", DIM)))
    b.reveal(L(S("  ✓ You're ready!", GREEN, bold=True)))
    b.hold(1100)

    b.clear()
    b.cmd("eidetic doctor")
    b.reveal(ok(S("config       ", FG), S(".env · 14 keys loaded", DIM)))
    b.reveal(ok(S("llm          ", FG), S("LM Studio :5555 reachable", DIM)))
    b.reveal(ok(S("embeddings   ", FG), S("nomic-embed-text · 768-dim", DIM)))
    b.reveal(ok(S("vector store ", FG), S("21,438 chunks · sqlite-vec", DIM)))
    b.reveal(ok(S("vault git    ", FG), S("clean · 3 commits", DIM)))
    b.reveal(L(S("  14 OK", GREEN, bold=True), S("  ·  ", DIM),
               S("0 WARN", DIM), S("  ·  ", DIM), S("0 FAIL", DIM)))
    b.end_prompt(2400)
    return b


# ── 2. setup.gif (the interactive wizard) ─────────────────────────────────────
def build_setup() -> Builder:
    b = Builder()
    b.cmd("eidetic init")
    b.reveal(L(S("  ▲  Eidetic OS — interactive setup", CYAN, bold=True)))
    b.blank()
    b.answer([S("  Vault path ", FG), S("[~/vault]", DIM), S(": ", FG)],
             "~/Documents/my-vault")
    b.hold(380)
    b.reveal(ok(S("Created ~/Documents/my-vault", FG)))
    b.blank()
    b.spin("Scanning for local LLM backends…", "found 2 endpoints")
    b.reveal(ok(S("LM Studio @ localhost:5555 ", FG), S("(qwen2.5)", DIM)))
    b.reveal(ok(S("Ollama @ localhost:11434 ", FG), S("(llama3.2)", DIM)))
    b.blank()
    b.answer([S("  Embedding model ", FG), S("[nomic-embed-text]", DIM), S(": ", FG)],
             "↵")
    b.reveal(ok(S("Embeddings: nomic-embed-text · 768-dim", FG)))
    b.blank()
    b.answer([S("  Email notifications? ", FG), S("[y/N]", DIM), S(": ", FG)], "y")
    b.answer([S("  SMTP sender ", FG), S(": ", FG)], "you@example.com")
    b.reveal(ok(S(".env written ", FG), S("(14 keys)", DIM)))
    b.blank()
    b.reveal(L(S("  ✓ Ready! ", GREEN, bold=True),
               S("Run 'eidetic doctor' to verify.", FG)))
    b.end_prompt(2600)
    return b


# ── 3. search.gif (hybrid RAG fusion) ─────────────────────────────────────────
def _hit(score: str, path: str, heading: str, fusion: str, snippet: str) -> list[L]:
    return [
        L(S(f"  [{score}] ", YELLOW), S(path, BLUE), S(f"  › {heading}", PINK)),
        L(S("         ", FG), S(fusion, DIM)),
        L(S(f'         {snippet}', DIM)),
        L(),
    ]


def build_search() -> Builder:
    b = Builder()
    b.cmd('eidetic search "what vector database did we choose"')
    b.blank()
    b.reveal(L(S("Searching ", FG), S("21,438", BOLD_W, bold=True),
               S(" chunks · fusing ", FG), S("BM25", CYAN),
               S(" + ", FG), S("vector", CYAN), S(" via ", FG),
               S("RRF", PURPLE), S("…", FG)))
    b.blank()
    b.hold(1000)
    for ln in _hit("0.94", "wiki/decisions/vector-store.md", "Why sqlite-vec",
                   "bm25 #3  ·  vector #1  →  rrf 0.94",
                   '"Chose sqlite-vec — zero-ops, embedded, scales to ~100k…"'):
        b.reveal(ln)
    b.hold(700)
    for ln in _hit("0.88", "session-logs/2026-05-20.md", "Backend comparison",
                   "bm25 #1  ·  vector #4  →  rrf 0.88",
                   '"LanceDB vs Chroma vs sqlite-vec — benchmarked recall and…"'):
        b.reveal(ln)
    b.hold(700)
    for ln in _hit("0.81", "wiki/sources/rag-notes.md", "Pluggable backends",
                   "bm25 #6  ·  vector #2  →  rrf 0.81",
                   '"A backend protocol lets you swap stores without re-indexing…"'):
        b.reveal(ln)
    b.reveal(L(S("  3 results ", BOLD_W, bold=True),
               S("· hybrid beats keyword-only & vector-only · 0.18s", DIM)))
    b.end_prompt(2600)
    return b


# ── 4. dashboard.gif ──────────────────────────────────────────────────────────
def _panel(name: str, desc: str) -> L:
    return ok(S(f"{name:<9}", FG), S(desc, DIM))


def build_dashboard() -> Builder:
    b = Builder()
    b.cmd("eidetic dashboard")
    b.reveal(L(S("  ▲  Eidetic OS Dashboard", CYAN, bold=True)))
    b.spin("Starting local Flask server…", "bound to 127.0.0.1:8501")
    b.blank()
    b.reveal(L(S("  Panels", BOLD_W, bold=True)))
    b.reveal(_panel("Health", "12 subsystem probes · all green"))
    b.reveal(_panel("Audit", "every command, who/what/when"))
    b.reveal(_panel("Tasks", "scheduled skills + cadences"))
    b.reveal(_panel("Skills", "160-skill catalog"))
    b.reveal(_panel("Vectors", "21,438 chunks · sqlite-vec"))
    b.reveal(_panel("RAG", "live hybrid search box"))
    b.reveal(_panel("Graph", "D3 force-directed note map"))
    b.blank()
    b.reveal(L(S("  ➜ Dashboard running at ", GREEN, bold=True),
               S("http://localhost:8501", BLUE)))
    b.end_prompt(2800)
    return b


# ── 5. skills.gif (catalog · sandboxed run · MCP) ─────────────────────────────
def _skill(slug: str, cadence: str, desc: str) -> L:
    return L(S(f"  {slug:<20}", CYAN), S(f"{cadence:<12}", DIM), S(desc, FG))


def build_skills() -> Builder:
    b = Builder()
    b.cmd("eidetic skills list")
    b.reveal(L(S("Agent skills ", BOLD_W, bold=True), S("(160 skills)", DIM)))
    b.blank()
    b.reveal(L(S("  Security", PURPLE, bold=True)))
    b.reveal(_skill("security-audit", "on-demand", "AST + secret scan over a repo"))
    b.reveal(_skill("threat-model", "on-demand", "STRIDE pass on a design doc"))
    b.reveal(L(S("  DevOps", PURPLE, bold=True)))
    b.reveal(_skill("k8s-review", "on-demand", "Lint manifests for footguns"))
    b.reveal(L(S("  Eidetic-native", PURPLE, bold=True)))
    b.reveal(_skill("autoresearch", "on-demand", "Research a topic → wiki note"))
    b.reveal(_skill("daily-digest", "daily", "Summarise notes, email a brief"))
    b.hold(1500)

    b.clear()
    b.cmd("eidetic skills run security-audit --target ./app")
    b.spin("AST scan (142 files)…", "3 findings")
    b.spin("Sandboxed exec (no network, read-only fs)…", "complete")
    b.reveal(warn(S("app/auth.py:88  hardcoded fallback secret", FG)))
    b.reveal(warn(S("app/api.py:31   unparameterised SQL", FG)))
    b.reveal(ok(S("report → ", FG), S("vault/audits/security-audit.md", BLUE)))
    b.hold(1500)

    b.clear()
    b.cmd("eidetic mcp serve")
    b.spin("Exposing Eidetic OS over the Model Context Protocol…", "ready")
    b.reveal(L(S("  MCP server on stdio · ", FG),
               S("7 tools", BOLD_W, bold=True),
               S(" (search, embed, skills, graph…)", DIM)))
    b.end_prompt(2400)
    return b


# ── 6. extensions.gif ─────────────────────────────────────────────────────────
def _ext(name: str, version: str, source: str, desc: str) -> list[L]:
    return [
        L(S(f"  {name:<9}", CYAN), S(f"v{version}  ", FG),
          S(f"[{source}]", DIM)),
        L(S(f"    {desc}", DIM)),
    ]


def build_extensions() -> Builder:
    b = Builder()
    b.cmd("pip install 'eidetic-os[trading]'")
    b.bar("Downloading trading extras (yfinance, TradingAgents)", 4.0,
          unit="MB", steps=24)
    b.reveal(L(S("Successfully installed eidetic-os-4.0.0 ", GREEN, bold=True),
               S("+ trading", PINK, bold=True)))
    b.hold(1100)

    b.clear()
    b.cmd("eidetic extensions list")
    b.reveal(L(S("Extensions ", BOLD_W, bold=True), S("(3 discovered)", DIM)))
    b.blank()
    for ln in _ext("trading", "1.0.0", "entry-point",
                   "Trading research briefings (TradingAgents) → vault"):
        b.reveal(ln)
    for ln in _ext("voice", "0.1.0", "built-in",
                   "Text-to-speech for Eidetic output via local TTS"):
        b.reveal(ln)
    for ln in _ext("jobs", "0.1.0", "built-in",
                   "Job-application tracking stored as vault notes"):
        b.reveal(ln)
    b.hold(1500)

    b.clear()
    b.cmd("eidetic trading --ticker NVDA")
    b.spin("Running analyst agents (local LLM)…",
           "technical · fundamentals · sentiment · news")
    b.reveal(ok(S("briefing → ", FG), S("vault/trading/NVDA-2026-06-06.md", BLUE)))
    b.reveal(L(S("  signal ", FG), S("BUY", GREEN, bold=True),
               S("  ·  confidence ", FG), S("0.72", YELLOW),
               S("  ·  ", DIM), S("not financial advice", DIM)))
    b.end_prompt(2600)
    return b


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    targets = {
        "install.gif": build_install,
        "setup.gif": build_setup,
        "search.gif": build_search,
        "dashboard.gif": build_dashboard,
        "skills.gif": build_skills,
        "extensions.gif": build_extensions,
    }
    for name, build in targets.items():
        b = build()
        out = repo_root / name
        b.save(out)
        print(
            f"{name:<16} {len(b.frames):>4} frames · "
            f"{b.total_ms / 1000:>5.1f}s · {out.stat().st_size / 1024:>6.0f} KB"
        )


if __name__ == "__main__":
    main()
