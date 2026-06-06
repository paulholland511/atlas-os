#!/usr/bin/env python3
"""Shared rendering toolkit for the Eidetic OS animated terminal GIFs.

A tiny, dependency-light (Pillow only) renderer that fakes a macOS terminal
session: window chrome with traffic-light dots and an "Eidetic OS Terminal"
title, a typewriter prompt effect, colour-coded output spans, animated progress
bars and spinners, and a blinking block cursor. Everything is synthetic — no
personal data — and supersampled 2× then LANCZOS-downscaled for crisp text.

The two generators (`make_demo_gif.py`, `make_doc_gifs.py`) import this module
and describe their scenes with the `Builder` API; this file owns the look.

Palette: Tokyo Night background (#1a1b26) with a Dracula-leaning accent set —
green for commands/success, cyan for info, yellow for highlights, red for
errors, and purple for the Eidetic OS branding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── canvas / geometry ─────────────────────────────────────────────────────────
WIDTH, HEIGHT = 800, 500
TITLEBAR_H = 32
PAD_X, PAD_Y = 18, 14
LINE_H = 18
FONT_SIZE = 13
SCALE = 2  # supersample for crisp text, then downscale

# ── palette ───────────────────────────────────────────────────────────────────
BG = (26, 27, 38)           # #1a1b26  Tokyo Night body
TITLEBAR = (36, 40, 59)     # #24283b  window chrome
TITLEBAR_TXT = (138, 145, 176)
FG = (248, 248, 242)        # #f8f8f2  default foreground (white)
GREEN = (80, 250, 123)      # #50fa7b  commands / success
CYAN = (139, 233, 253)      # #8be9fd  info
YELLOW = (241, 250, 140)    # #f1fa8c  highlights / scores
RED = (255, 85, 85)         # #ff5555  errors
PURPLE = (189, 147, 249)    # #bd93f9  Eidetic OS branding
PINK = (255, 121, 198)      # #ff79c6  accent
ORANGE = (255, 184, 108)    # #ffb86c  accent
BLUE = (130, 170, 255)      # #82aaff  file paths
DIM = (98, 114, 164)        # #6272a4  comments / secondary
BOLD_W = (248, 248, 242)    # bright white
CURSOR = (189, 147, 249)    # purple block cursor

TRAFFIC = [(255, 95, 86), (255, 189, 46), (39, 201, 63)]

VISIBLE_LINES = (HEIGHT - TITLEBAR_H - 2 * PAD_Y) // LINE_H


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
TITLE_FONT = _load_font(12 * SCALE)
CHAR_W = FONT.getbbox("M")[2]  # monospace cell width (already scaled)


# ── text model ────────────────────────────────────────────────────────────────
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


# A modern zsh-style prompt: dim cwd + green chevron + the typed command.
def prompt_line(cmd: str, cwd: str = "~/vault") -> Line:
    return L(
        S(f"{cwd} ", DIM),
        S("❯ ", GREEN, bold=True),
        S(cmd, BOLD_W, bold=True),
    )


# Common output line shapes shared across scenes.
def ok(*spans: Span) -> Line:
    return L(S("  ✓ ", GREEN), *spans)


def fail(*spans: Span) -> Line:
    return L(S("  ✗ ", RED), *spans)


def warn(*spans: Span) -> Line:
    return L(S("  ! ", YELLOW), *spans)


def hdr(text: str) -> Line:
    return L(S(text, BOLD_W, bold=True))


# ── frame rendering ───────────────────────────────────────────────────────────
def _draw_titlebar(d: ImageDraw.ImageDraw) -> None:
    d.rectangle([0, 0, WIDTH * SCALE, TITLEBAR_H * SCALE], fill=TITLEBAR)
    # underline the chrome with a hairline for a touch of depth
    d.rectangle(
        [0, TITLEBAR_H * SCALE - SCALE, WIDTH * SCALE, TITLEBAR_H * SCALE], fill=BG
    )
    cy = (TITLEBAR_H // 2) * SCALE
    for i, col in enumerate(TRAFFIC):
        cx = (20 + i * 20) * SCALE
        r = 6 * SCALE
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    # Centred, branded title: purple sparkle + "Eidetic OS Terminal".
    spark, rest = "✦ ", "Eidetic OS Terminal"
    sw = d.textlength(spark, font=TITLE_FONT)
    rw = d.textlength(rest, font=TITLE_FONT)
    x0 = (WIDTH * SCALE - (sw + rw)) / 2
    ty = (TITLEBAR_H * SCALE - TITLE_FONT.size) / 2 - SCALE
    d.text((x0, ty), spark, font=TITLE_FONT, fill=PURPLE)
    d.text((x0 + sw, ty), rest, font=TITLE_FONT, fill=TITLEBAR_TXT)


def render_frame(lines: list[Line], typed: int | None, show_cursor: bool) -> Image.Image:
    """Draw the visible buffer. ``typed`` truncates the last line's last span to
    that many characters (typewriter); ``show_cursor`` draws a block cursor."""
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
            if is_last and typed is not None and si == len(line.spans) - 1:
                text = text[:typed]
            d.text((x, y), text, font=FONT, fill=span.color)
            x += len(text) * CHAR_W
        if is_last and show_cursor:
            d.rectangle(
                [x, y + 2 * SCALE, x + CHAR_W - SCALE, y + LINE_H * SCALE - 3 * SCALE],
                fill=CURSOR,
            )
        y += LINE_H * SCALE

    return img.resize((WIDTH, HEIGHT), Image.LANCZOS)


# ── timeline builder ──────────────────────────────────────────────────────────
TYPE_MS = 48          # per typewriter tick
CHARS_PER_TICK = 2    # characters revealed per tick (snappy typing)
CURSOR_BLINK_MS = 360
REVEAL_MS = 52        # per output line
BLANK_MS = 24         # blank spacer lines reveal faster
SPIN_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class Builder:
    """Accumulates frames for one GIF.

    Scenes are described imperatively: ``cmd`` types a command, ``reveal`` shows
    an output line, ``bar``/``spin`` animate progress, ``hold`` pauses on a
    result, and ``end_prompt`` leaves a blinking cursor before the next scene.
    """

    def __init__(self) -> None:
        self.buffer: list[Line] = []
        self.frames: list[Image.Image] = []
        self.durations: list[int] = []

    # -- low level --
    def _frame(self, typed: int | None, cursor: bool, ms: int) -> None:
        self.frames.append(render_frame(self.buffer, typed, cursor))
        self.durations.append(ms)

    def append(self, line: Line) -> None:
        self.buffer.append(line)

    def snapshot(self) -> list[Line]:
        """Return a shallow copy of the current buffer (e.g. a persistent header)."""
        return list(self.buffer)

    def reset_to(self, lines: list[Line]) -> None:
        """Clear the screen back to ``lines`` — used to start each scene fresh so
        GIF frame-diffs stay small (only the new bottom line changes per frame)."""
        self.buffer = list(lines)

    def clear(self) -> None:
        """Wipe the screen (next command starts at the top)."""
        self.buffer = []

    # -- prompt / typing --
    def typewrite(self, ms: int = TYPE_MS, blink_before: bool = True) -> None:
        full = self.buffer[-1].spans[-1].text
        if blink_before:
            self._frame(0, True, CURSOR_BLINK_MS)
            self._frame(0, False, 180)
        for i in range(CHARS_PER_TICK, len(full) + CHARS_PER_TICK, CHARS_PER_TICK):
            self._frame(min(i, len(full)), True, ms)
        self._frame(len(full), True, 300)

    def cmd(self, command: str, cwd: str = "~/vault") -> None:
        self.append(prompt_line(command, cwd))
        self.typewrite()

    def answer(self, label_spans: list[Span], typed: str, ms: int = 60) -> None:
        """An interactive prompt with a typed-in user answer (final span)."""
        self.append(L(*label_spans, S(typed, BLUE)))
        self.typewrite(ms=ms)

    # -- output --
    def reveal(self, line: Line) -> None:
        self.append(line)
        self._frame(None, False, BLANK_MS if not line.spans else REVEAL_MS)

    def reveal_all(self, lines: list[Line]) -> None:
        for line in lines:
            self.reveal(line)

    def blank(self) -> None:
        self.reveal(L())

    def hold(self, ms: int, cursor: bool = False) -> None:
        self._frame(None, cursor, ms)

    # -- animations --
    def bar(
        self,
        label: str,
        total: float,
        unit: str = "MB",
        steps: int = 24,
        color: tuple[int, int, int] = CYAN,
        frame_ms: int = 30,
    ) -> None:
        """Animate a filling progress bar (pip download, embedding pass, …)."""
        self.reveal(L(S("  " + label, DIM)))
        self.append(L())  # placeholder bar line, rewritten each tick
        bar_w = 32
        for s in range(steps + 1):
            frac = s / steps
            filled = round(bar_w * frac)
            done = total * frac
            head = "━" * filled + ("╺" if filled < bar_w else "")
            tail = "━" * max(0, bar_w - filled - 1)
            shade = GREEN if frac >= 1.0 else color
            self.buffer[-1] = L(
                S("  ", FG),
                S(head, shade),
                S(tail, DIM),
                S(f"  {done:5.1f}/{total:.1f} {unit}", DIM),
            )
            self._frame(None, False, frame_ms)

    def spin(self, label: str, done: str, cycles: int = 2, frame_ms: int = 70) -> None:
        """A braille spinner that resolves into a green check + ``done`` text."""
        self.append(L())  # placeholder, rewritten each tick
        ticks = cycles * len(SPIN_FRAMES)
        for t in range(ticks):
            glyph = SPIN_FRAMES[t % len(SPIN_FRAMES)]
            self.buffer[-1] = L(S(f"  {glyph} ", CYAN), S(label, FG))
            self._frame(None, False, frame_ms)
        self.buffer[-1] = ok(S(done, FG))
        self._frame(None, False, 240)

    def end_prompt(self, ms: int = 1600, cwd: str = "~/vault") -> None:
        """Leave a blinking cursor at a fresh prompt to close a scene."""
        self.append(L(S(f"{cwd} ", DIM), S("❯ ", GREEN, bold=True), S("", BOLD_W)))
        self._frame(0, True, ms)
        self._frame(0, False, 260)
        self._frame(0, True, 420)
        self._frame(0, False, 260)

    # -- output --
    def save(self, out: Path) -> None:
        self.frames[0].save(
            out,
            save_all=True,
            append_images=self.frames[1:],
            duration=self.durations,
            loop=0,
            optimize=True,
            disposal=2,
        )

    @property
    def total_ms(self) -> int:
        return sum(self.durations)
