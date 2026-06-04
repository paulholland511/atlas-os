#!/usr/bin/env python3
"""Render an animated terminal demo GIF for the Atlas OS README.

Simulates a macOS-terminal session walking through four headline commands —
`atlas init`, `atlas doctor`, `atlas search`, and `atlas skills list` — with a
typewriter prompt effect, line-by-line output, and brief read-pauses between
scenes. Pure synthetic output (no personal data) generated with Pillow only.

    python3 scripts/make_demo_gif.py            # writes demo.gif in the repo root
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── canvas / theme ────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 800, 500
TITLEBAR_H = 30
PAD_X, PAD_Y = 16, 12
LINE_H = 18
FONT_SIZE = 13
SCALE = 2  # supersample for crisp text, then downscale

BG = (30, 31, 34)          # terminal body  (iTerm "Dark" style)
TITLEBAR = (44, 46, 51)
TITLEBAR_TXT = (170, 173, 180)
FG = (208, 211, 215)       # default foreground
PROMPT_SYMB = (98, 209, 150)   # green $
PROMPT_PATH = (102, 170, 255)  # blue ~/atlas-os
CURSOR = (208, 211, 215)

GREEN = (87, 200, 122)
YELLOW = (224, 190, 92)
RED = (224, 108, 108)
CYAN = (86, 182, 194)
BLUE = (102, 170, 255)
DIM = (128, 132, 140)
BOLD_W = (236, 238, 240)
MAGENTA = (197, 134, 192)

TRAFFIC = [(255, 95, 86), (255, 189, 46), (39, 201, 63)]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in (
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.ttf",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


FONT = _load_font(FONT_SIZE * SCALE)
FONT_BOLD = _load_font(FONT_SIZE * SCALE)
TITLE_FONT = _load_font(13 * SCALE)
CHAR_W = FONT.getbbox("M")[2]  # monospace cell width (already scaled)


# ── line model ────────────────────────────────────────────────────────────────
@dataclass
class Span:
    text: str
    color: tuple[int, int, int] = FG
    bold: bool = False


@dataclass
class Line:
    spans: list[Span] = field(default_factory=list)


def L(*spans: Span) -> Line:
    return Line(list(spans))


def S(text: str, color: tuple[int, int, int] = FG, bold: bool = False) -> Span:
    return Span(text, color, bold)


# A prompt line: green "$" + space + the command text (typed out char by char).
def prompt(cmd: str) -> Line:
    return L(S("$ ", PROMPT_SYMB, bold=True), S(cmd, BOLD_W))


VISIBLE_LINES = (HEIGHT - TITLEBAR_H - 2 * PAD_Y) // LINE_H


# ── scene script ──────────────────────────────────────────────────────────────
# Each scene is a list of "steps". A prompt step is typed character by character;
# every other line appears whole, one per frame tick.
def ok(text: str) -> Line:
    return L(S("  ✓ ", GREEN), S(text, FG))


def hdr(text: str) -> Line:
    return L(S(text, BOLD_W, bold=True))


SCENE_INIT = [
    prompt("atlas init"),
    L(),
    L(S("  ▲  Atlas OS — setup wizard", CYAN, bold=True)),
    L(),
    L(S("  This wizard will:", FG)),
    L(S("    • find your vault and any local LLM", DIM)),
    L(S("    • write a .env you can tweak later", DIM)),
    L(S("    • scaffold the vault (.atlas/, .rag/, wiki/)", DIM)),
    L(),
    L(S("  Vault path [~/vault]: ", FG), S("~/vault", BLUE)),
    L(),
    L(S("  Probing for a local LLM endpoint…", FG)),
    ok("LM Studio at http://localhost:5555 (qwen2.5, nomic-embed)"),
    ok("using http://localhost:5555 for embeddings + chat"),
    ok("wrote ~/atlas-os/.env"),
    L(),
    L(S("  Scaffolding the vault…", FG)),
    ok("generated skills-catalog.md"),
    ok("initialised vault git repo"),
    L(),
    L(S("  ✓ You're ready!", GREEN, bold=True)),
]


def chk(name: str, detail: str) -> Line:
    return L(S("  ✓ ", GREEN), S(f"{name:<12}", FG), S(detail, DIM))


SCENE_DOCTOR = [
    prompt("atlas doctor"),
    L(),
    hdr("Atlas OS — doctor"),
    L(),
    hdr("Config"),
    chk("VAULT_PATH", "~/vault"),
    chk(".env", "12 keys loaded"),
    L(),
    hdr("Git"),
    chk("vault repo", "clean · 3 commits"),
    L(),
    hdr("LLM"),
    chk("endpoint", "LM Studio :5555 reachable"),
    chk("embeddings", "nomic-embed-text · 768-dim"),
    L(),
    hdr("RAG"),
    chk("vector store", "21,438 chunks · sqlite-vec"),
    chk("freshness", "re-embedded 2h ago"),
    L(),
    hdr("SMTP"),
    chk("email", "smtp.gmail.com:587 configured"),
    L(),
    L(S("12 OK · 0 WARN · 0 FAIL", BOLD_W, bold=True)),
]


def result(rank: int, score: str, path: str, heading: str, snippet: str) -> list[Line]:
    return [
        L(
            S(f"{rank}. ", FG),
            S(f"[{score}] ", YELLOW),
            S(path, BLUE),
            S(f" › {heading}", MAGENTA),
        ),
        L(S(f"     {snippet}", DIM)),
        L(),
    ]


SCENE_SEARCH = [
    prompt('atlas search "meeting notes from last week"'),
    L(),
    L(S('Top 4 result(s) for "meeting notes from last week":', FG)),
    L(),
    *result(
        1, "0.847", "wiki/standup-2024-w23.md", "Action items",
        "Ship vector store migration; review RAG reranker thresholds…",
    ),
    *result(
        2, "0.812", "meetings/product-sync.md", "Decisions",
        "Agreed to ship hybrid search behind a flag; revisit BM25 weights…",
    ),
    *result(
        3, "0.778", "wiki/roadmap-review.md", "Q3 priorities",
        "Onboarding wizard, Docker image, 160+ skills catalogue…",
    ),
    *result(
        4, "0.741", "meetings/1-1-notes.md", "Follow-ups",
        "Draft the README demo GIF; close out the embedding-cache work…",
    ),
]


def skill(slug: str, cadence: str, desc: str) -> list[Line]:
    return [
        L(S(f"  {slug}", CYAN), S(f"  [{cadence}]", DIM)),
        L(S(f"    {desc}", FG)),
    ]


SCENE_SKILLS = [
    prompt("atlas skills list"),
    L(),
    L(S("Agent skills (160 skill(s)):", BOLD_W, bold=True)),
    L(),
    *skill("autoresearch", "on-demand", "Research a topic and file it as a wiki note."),
    *skill("daily-digest", "daily", "Summarise the day's notes and email a brief."),
    *skill("portfolio-report", "weekly", "Trading P&L + risk snapshot from live data."),
    *skill("vault-commit", "hourly", "Auto-commit the vault with a categorised message."),
    *skill("inbox-triage", "daily", "Sort, label, and draft replies for new mail."),
    L(),
    L(S("Run `atlas skills install <name>` to install one.", DIM)),
]

SCENES = [SCENE_INIT, SCENE_DOCTOR, SCENE_SEARCH, SCENE_SKILLS]


# ── frame rendering ───────────────────────────────────────────────────────────
def _draw_titlebar(d: ImageDraw.ImageDraw) -> None:
    d.rectangle([0, 0, WIDTH * SCALE, TITLEBAR_H * SCALE], fill=TITLEBAR)
    cy = (TITLEBAR_H // 2) * SCALE
    for i, col in enumerate(TRAFFIC):
        cx = (18 + i * 20) * SCALE
        r = 6 * SCALE
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    title = "atlas — ~/atlas-os — zsh"
    tw = d.textlength(title, font=TITLE_FONT)
    d.text(
        ((WIDTH * SCALE - tw) / 2, (TITLEBAR_H * SCALE - TITLE_FONT.size) / 2 - SCALE),
        title,
        font=TITLE_FONT,
        fill=TITLEBAR_TXT,
    )


def render_frame(lines: list[Line], typed: int | None, show_cursor: bool) -> Image.Image:
    """Draw the visible buffer. ``typed`` truncates the last line's command text
    to that many characters (typewriter); ``show_cursor`` draws a block cursor."""
    img = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), BG)
    d = ImageDraw.Draw(img)
    _draw_titlebar(d)

    view = lines[-VISIBLE_LINES:]
    y = (TITLEBAR_H + PAD_Y) * SCALE
    for li, line in enumerate(view):
        x = PAD_X * SCALE
        is_last = li == len(view) - 1
        for si, span in enumerate(line.spans):
            text = span.text
            # Typewriter only applies to the command text on the final prompt line.
            if is_last and typed is not None and si == len(line.spans) - 1:
                text = text[:typed]
            font = FONT_BOLD if span.bold else FONT
            d.text((x, y), text, font=font, fill=span.color)
            x += len(text) * CHAR_W
        if is_last and show_cursor:
            d.rectangle([x, y + 2 * SCALE, x + CHAR_W - SCALE, y + LINE_H * SCALE - 2 * SCALE], fill=CURSOR)
        y += LINE_H * SCALE

    return img.resize((WIDTH, HEIGHT), Image.LANCZOS)


# ── timeline assembly ─────────────────────────────────────────────────────────
FPS_MS = 55          # base tick used for output reveal
TYPE_MS = 55         # per-keystroke typing delay (2 chars/keystroke)
CHARS_PER_TICK = 2   # type a couple of characters per frame to keep it snappy
CURSOR_BLINK_MS = 380


def build_frames() -> tuple[list[Image.Image], list[int]]:
    frames: list[Image.Image] = []
    durations: list[int] = []

    def add(img: Image.Image, ms: int) -> None:
        frames.append(img)
        durations.append(ms)

    buffer: list[Line] = []

    for scene in SCENES:
        prompt_line = scene[0]
        cmd = prompt_line.spans[-1].text

        # Fresh screen per scene (the prompt line sits at the top).
        buffer = [prompt_line]

        # One short cursor blink before typing begins.
        add(render_frame(buffer, typed=0, show_cursor=True), CURSOR_BLINK_MS)
        add(render_frame(buffer, typed=0, show_cursor=False), 220)

        # Typewriter the command, a couple of characters per frame.
        for i in range(CHARS_PER_TICK, len(cmd) + CHARS_PER_TICK, CHARS_PER_TICK):
            add(render_frame(buffer, typed=min(i, len(cmd)), show_cursor=True), TYPE_MS)
        # Hold the completed command a beat before it "runs".
        add(render_frame(buffer, typed=len(cmd), show_cursor=True), 320)

        # Reveal output lines one tick at a time.
        for line in scene[1:]:
            buffer.append(line)
            ms = 28 if not line.spans else FPS_MS
            add(render_frame(buffer, typed=None, show_cursor=False), ms)

        # Read-pause at the end of the scene (with a steady cursor on a new line).
        buffer.append(L(S("$ ", PROMPT_SYMB, bold=True), S("", BOLD_W)))
        add(render_frame(buffer, typed=0, show_cursor=True), 1600)
        add(render_frame(buffer, typed=0, show_cursor=False), 260)

    return frames, durations


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    out = repo_root / "demo.gif"

    frames, durations = build_frames()
    total = sum(durations)
    print(f"frames: {len(frames)}  ·  duration: {total/1000:.1f}s")

    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"wrote {out}  ({out.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
