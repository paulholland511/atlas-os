"""Sleeptime memory consolidation — compress recent dialogue into a single note.

Eidetic captures Cowork session transcripts into ``$VAULT_PATH/sessions/`` twice a
day and embeds them into the vector store. Left alone, those raw logs accumulate:
hundreds of near-duplicate "ran 12 shell commands, edited 3 files" notes that bloat
retrieval context without adding signal. This module is the **sleeptime daemon** —
a lightweight background process that runs while you are offline, reads the session
logs written since its last pass, distils each one to its decisions/actions/topics,
merges them into a single consolidated note, and resolves any contradictions in
favour of the most recent statement.

Design
------
* **Heuristic by default, LLM when available.** Extraction is pure-Python regex
  heuristics so it works offline with zero dependencies. If an LLM backend is
  reachable (:mod:`eidetic_os.backends`) it is used to produce a richer summary,
  but the daemon never *requires* one.
* **Watermark, not re-scan.** The last consolidation time is tracked in
  ``.eidetic/last_consolidation.txt`` (mirroring the session-save watermark), so
  each pass only touches session logs modified since.
* **Single writer.** A pass takes the advisory :func:`eidetic_os.filelock.vault_lock`
  on ``.eidetic/consolidation`` so two daemons (or a manual run racing the
  scheduled one) can never consolidate concurrently.
* **Most-recent-wins.** Session logs are processed oldest-first; when two sessions
  make conflicting decisions about the same thing, the later one is kept and the
  contradiction is recorded in the note's frontmatter trail.
* **Graceful degradation.** A missing vault, a missing ``sessions/`` directory, or
  no new logs is a no-op that returns ``None`` — never an exception.
* **Optional facts integration (#22).** If ``eidetic_os.facts.extract_facts`` is
  present it is called per session and its output folded into the takeaways; if the
  module is not yet merged, the import fails softly and the daemon works standalone.

Usage::

    from eidetic_os.sleeptime import ConsolidationDaemon

    daemon = ConsolidationDaemon(vault_path)
    note = daemon.run_once()          # single pass (scheduler-friendly)
    daemon.start()                    # background loop every interval_hours
    daemon.stop()                     # graceful shutdown
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from eidetic_os import audit
from eidetic_os.filelock import LockTimeout, vault_lock

# The facts extractor (#22) is built in parallel — integrate it if present, but
# never hard-depend on it. ``FACTS_AVAILABLE`` lets callers/tests see the state.
try:  # pragma: no cover - exercised indirectly; depends on parallel merge state
    from eidetic_os.facts import extract_facts as _extract_facts  # type: ignore
    FACTS_AVAILABLE = True
except Exception:  # noqa: BLE001 - any import-time failure means "not available yet"
    _extract_facts = None  # type: ignore[assignment]
    FACTS_AVAILABLE = False


# ── Configuration ─────────────────────────────────────────────────────────────

DEFAULT_INTERVAL_HOURS: Final = 6.0
WATERMARK_NAME: Final = "last_consolidation.txt"
LOCK_TARGET_NAME: Final = "consolidation"
CONSOLIDATED_SUBDIR: Final = ("wiki", "consolidated")
SESSIONS_SUBDIR: Final = "sessions"

# Heuristic patterns. Each captures the *clause* after the trigger so the rendered
# takeaway reads as a sentence rather than a bare verb.
_DECISION_PATTERNS: Final = (
    r"decided\s+(?:to\s+|on\s+)?(.+)",
    r"chose\s+(?:to\s+)?(.+)",
    r"going\s+with\s+(.+)",
    r"opted\s+(?:for|to)\s+(.+)",
    r"will\s+use\s+(.+)",
    r"we['’]?ll\s+(?:go\s+with|use)\s+(.+)",
    r"let['’]?s\s+(?:go\s+with|use)\s+(.+)",
    r"settled\s+on\s+(.+)",
)
_ACTION_PATTERNS: Final = (
    # Capture the verb too — for actions the verb is the meaningful part.
    r"((?:created|built|added|implemented|wrote|fixed|updated|refactored|removed|"
    r"deleted|renamed|pushed|committed|merged|installed|configured|deployed|"
    r"migrated)\s+.+)",
)
# A path-ish token ending in a known code/doc extension.
_FILE_RE: Final = re.compile(
    r"(?<![\w/])"
    r"([\w./-]+?\."
    r"(?:py|md|txt|json|toml|yaml|yml|js|ts|tsx|jsx|sh|cfg|ini|rs|go|java|"
    r"c|cpp|h|hpp|css|html|sql|lock|cron))"
    r"(?![\w])"
)
_HEADING_RE: Final = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
_QUESTION_RE: Final = re.compile(r"([A-Z][^?.!\n]*\?)")
_CODE_FENCE_RE: Final = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE: Final = re.compile(r"`[^`]*`")
# Noise lines: tracebacks, tool dumps, log spew.
_NOISE_LINE_RE: Final = re.compile(
    r"^\s*(?:Traceback|File \"|\s{4}at |\[\d{4}-\d\d-\d\d|DEBUG|INFO|WARNING|"
    r"ERROR|stdout:|stderr:|\$ |> )",
)
# Decisions of the form "use X for Y" / "use X instead of Y", used by the
# contradiction detector to find conflicting choices for the same purpose.
_CHOICE_RE: Final = re.compile(
    r"\b(?:use|using|adopt|adopting|go(?:ing)?\s+with|chose|choose|switch(?:ing)?\s+to)"
    r"\s+(?P<choice>[\w.+#/-]+)"
    r"(?:\s+(?:for|as|to handle)\s+(?P<purpose>[\w][\w \-]*?))?"
    r"(?:\s+(?:instead\s+of|rather\s+than|over)\s+(?P<displaced>[\w.+#/-]+))?"
    r"\s*$",
    re.IGNORECASE,
)


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SessionTakeaways:
    """The distilled signal from one session log.

    ``facts`` holds statements from the optional #22 fact extractor when it is
    available; it is empty under pure-heuristic extraction.
    """

    session_file: str
    decisions: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (
            self.decisions or self.actions or self.topics
            or self.files_touched or self.questions or self.facts
        )


@dataclass(frozen=True)
class ConsolidatedNote:
    """The merged output of a single consolidation pass."""

    date: str
    sessions_processed: list[str]
    decisions: list[str]
    actions: list[str]
    topics: list[str]
    files_touched: list[str]
    summary: str
    contradictions: list[dict[str, str]] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)


# ── Pure extraction helpers ───────────────────────────────────────────────────


def _dedupe_preserving_order(items: Sequence[str]) -> list[str]:
    """De-duplicate case-insensitively while preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        norm = item.strip().casefold()
        if norm and norm not in seen:
            seen.add(norm)
            out.append(item.strip())
    return out


def _clean_clause(text: str) -> str:
    """Trim a captured clause to a tidy, single-line takeaway."""
    text = text.strip().strip("-*•").strip()
    # Drop trailing punctuation noise but keep a meaningful question mark.
    text = re.sub(r"[\s.,;:]+$", "", text)
    return text


def strip_noise(text: str) -> str:
    """Remove code blocks, inline code, and obvious tool/log/traceback lines.

    The session logs interleave prose with command output and stack traces; the
    heuristics only want the human-readable narrative, so we strip the rest before
    pattern-matching. Pure and idempotent.
    """
    text = _CODE_FENCE_RE.sub(" ", text)
    text = _INLINE_CODE_RE.sub(" ", text)
    kept: list[str] = []
    seen_lines: set[str] = set()
    for line in text.splitlines():
        if _NOISE_LINE_RE.match(line):
            continue
        stripped = line.strip()
        # Collapse exact repeated prompt/echo lines.
        if stripped and stripped in seen_lines:
            continue
        if stripped:
            seen_lines.add(stripped)
        kept.append(line)
    return "\n".join(kept)


def _match_patterns(text: str, patterns: Sequence[str]) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        for pattern in patterns:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                clause = _clean_clause(m.group(1) if m.groups() else m.group(0))
                if clause:
                    out.append(clause)
                break  # one takeaway per line
    return out


def extract_decisions(text: str) -> list[str]:
    """Pull decision statements ("decided to…", "going with…", "will use…")."""
    return _dedupe_preserving_order(_match_patterns(text, _DECISION_PATTERNS))


def extract_actions(text: str) -> list[str]:
    """Pull action statements ("created…", "fixed…", "pushed…")."""
    return _dedupe_preserving_order(_match_patterns(text, _ACTION_PATTERNS))


def extract_files(text: str) -> list[str]:
    """Pull file paths by matching common code/doc extensions."""
    return _dedupe_preserving_order(
        [m.group(1) for m in _FILE_RE.finditer(text)]
    )


def extract_topics(text: str) -> list[str]:
    """Pull discussion topics from markdown heading content.

    Boilerplate section headings the session-log template always emits (Summary,
    Key Actions, Files Modified) are dropped — they describe structure, not topic.
    """
    boilerplate = {"summary", "key actions", "files modified", "session"}
    topics = [
        _clean_clause(m.group(1))
        for m in _HEADING_RE.finditer(text)
    ]
    return _dedupe_preserving_order(
        [t for t in topics if t and t.casefold() not in boilerplate]
    )


def extract_questions(text: str) -> list[str]:
    """Pull interrogative sentences (capitalised … ?) from the prose.

    The match already includes the trailing ``?``; we only tidy surrounding
    whitespace, never strip it.
    """
    found = [m.group(1).strip() for m in _QUESTION_RE.finditer(text)]
    return _dedupe_preserving_order([q for q in found if len(q) > 8])


def heuristic_takeaways(text: str, session_file: str) -> SessionTakeaways:
    """Extract takeaways from one session log using only regex heuristics.

    Pure (no I/O, no LLM, no facts dependency), so it is trivially testable and is
    the offline fallback. The daemon enriches the result with :func:`facts_for`
    when the optional #22 extractor is available.
    """
    clean = strip_noise(text)
    return SessionTakeaways(
        session_file=session_file,
        decisions=extract_decisions(clean),
        actions=extract_actions(clean),
        topics=extract_topics(text),  # headings come from the raw structure
        files_touched=extract_files(text),
        questions=extract_questions(clean),
    )


def facts_for(text: str) -> list[str]:
    """Best-effort facts from the optional #22 extractor; never raises.

    Returns the human-readable fact strings, normalising whatever shape
    ``extract_facts`` returns (plain strings, or dataclasses exposing ``fact`` /
    ``text`` / ``statement``). Returns ``[]`` when the extractor is unavailable.
    """
    if _extract_facts is None:
        return []
    try:  # pragma: no cover - depends on facts.py shape, which may vary
        result = _extract_facts(text)
    except Exception:  # noqa: BLE001 - unknown/in-flux API must not break a pass
        return []
    items: list[str] = []
    for fact in result or []:
        if isinstance(fact, str):
            items.append(fact)
            continue
        for attr in ("fact", "text", "statement", "value", "content"):
            value = getattr(fact, attr, None)
            if value:
                items.append(str(value))
                break
        else:
            items.append(str(fact))
    return _dedupe_preserving_order(items)


# ── Contradiction resolution ──────────────────────────────────────────────────


def _analyze_decisions(
    ordered_decisions: Sequence[tuple[str, str]],
) -> tuple[list[dict[str, str]], set[str]]:
    """Core conflict analysis shared by detection and merging.

    Returns ``(contradictions, superseded)`` where ``superseded`` is the set of
    casefolded *full decision texts* that lost a cross-session conflict and should
    be dropped from the live decision list. Inline replacements ("use X instead of
    Y") record a contradiction but do not supersede the decision that states them.
    """
    contradictions: list[dict[str, str]] = []
    superseded: set[str] = set()
    # purpose (casefolded) → (choice, full decision text) most recently seen.
    by_purpose: dict[str, tuple[str, str]] = {}

    for _session, decision in ordered_decisions:
        m = _CHOICE_RE.search(decision)
        if not m:
            continue
        choice = (m.group("choice") or "").strip()
        purpose = (m.group("purpose") or "").strip()
        displaced = (m.group("displaced") or "").strip()

        if displaced:
            contradictions.append({
                "old_fact": displaced,
                "new_fact": choice,
                "resolution": (
                    f"adopted '{choice}' in place of '{displaced}' "
                    f"(stated in the same decision)"
                ),
            })

        if not purpose:
            continue
        key = purpose.casefold()
        prior = by_purpose.get(key)
        if prior is not None and prior[0].casefold() != choice.casefold():
            contradictions.append({
                "old_fact": f"{prior[0]} for {purpose}",
                "new_fact": f"{choice} for {purpose}",
                "resolution": (
                    f"kept '{choice}' for {purpose} (more recent) over '{prior[0]}'"
                ),
            })
            superseded.add(prior[1].casefold())  # the earlier decision loses
        by_purpose[key] = (choice, decision)

    return contradictions, superseded


def detect_contradictions(
    ordered_decisions: Sequence[tuple[str, str]],
) -> list[dict[str, str]]:
    """Find conflicting choices across sessions; keep the most recent.

    ``ordered_decisions`` is ``(session_file, decision)`` pairs in **chronological
    order** (oldest first). Two kinds of contradiction are detected:

    * **Inline replacement** — a single decision phrased as "use X instead of Y"
      records X-supersedes-Y directly.
    * **Cross-session conflict** — two decisions choosing a *different* thing for
      the *same* stated purpose ("use SQLite for storage" then later "use Postgres
      for storage"); the later choice wins.

    Each contradiction is ``{old_fact, new_fact, resolution}``.
    """
    return _analyze_decisions(ordered_decisions)[0]


# ── Merge + render ────────────────────────────────────────────────────────────


def _heuristic_summary(takeaways: Sequence[SessionTakeaways]) -> str:
    """A plain-language one-paragraph summary derived from the counts."""
    n = len(takeaways)
    decisions = sum(len(t.decisions) for t in takeaways)
    actions = sum(len(t.actions) for t in takeaways)
    files = len({f for t in takeaways for f in t.files_touched})
    topics = _dedupe_preserving_order([t for tk in takeaways for t in tk.topics])
    topic_phrase = (
        f" Topics spanned {', '.join(topics[:5])}." if topics else ""
    )
    return (
        f"Consolidated {n} session{'s' if n != 1 else ''}: "
        f"{decisions} decision(s), {actions} action(s) across {files} file(s)."
        f"{topic_phrase}"
    )


def merge_takeaways(
    takeaways: Sequence[SessionTakeaways],
    *,
    date: str,
    summary: str | None = None,
) -> ConsolidatedNote:
    """Merge per-session takeaways into a single :class:`ConsolidatedNote`.

    ``takeaways`` must be in chronological order so contradiction resolution keeps
    the most recent statement. ``summary`` overrides the heuristic summary (e.g. an
    LLM-generated one). Pure — no I/O.
    """
    ordered_decisions = [
        (t.session_file, d) for t in takeaways for d in t.decisions
    ]
    contradictions, superseded = _analyze_decisions(ordered_decisions)

    def keep(decision: str) -> bool:
        return decision.casefold() not in superseded

    return ConsolidatedNote(
        date=date,
        sessions_processed=[t.session_file for t in takeaways],
        decisions=[d for d in _dedupe_preserving_order(
            [d for _s, d in ordered_decisions]) if keep(d)],
        actions=_dedupe_preserving_order(
            [a for t in takeaways for a in t.actions]),
        topics=_dedupe_preserving_order(
            [tp for t in takeaways for tp in t.topics]),
        files_touched=_dedupe_preserving_order(
            [f for t in takeaways for f in t.files_touched]),
        summary=summary or _heuristic_summary(takeaways),
        contradictions=contradictions,
        questions=_dedupe_preserving_order(
            [q for t in takeaways for q in t.questions]),
        facts=_dedupe_preserving_order(
            [f for t in takeaways for f in t.facts]),
    )


def _yaml_list(items: Sequence[str]) -> str:
    """Render a YAML inline list, quoting nothing simple (tags are slugs)."""
    return "[" + ", ".join(items) + "]"


def render_note(note: ConsolidatedNote) -> str:
    """Render a :class:`ConsolidatedNote` to Markdown with YAML frontmatter.

    The frontmatter carries ``type: consolidated`` and a ``date`` that passes
    :mod:`eidetic_os.frontmatter` validation, so the note survives the automated
    commit gate and is indexed like any other vault note.
    """
    lines: list[str] = [
        "---",
        f'title: "Consolidated Memory: {note.date}"',
        f"date: {note.date}",
        "tags: [consolidated, memory, sleeptime]",
        "type: consolidated",
        f"sessions_processed: {len(note.sessions_processed)}",
        "---",
        "",
        f"# Consolidated Memory — {note.date}",
        "",
        "## Summary",
        note.summary,
        "",
    ]

    def section(title: str, items: Sequence[str], *, code: bool = False) -> None:
        lines.append(f"## {title}")
        if items:
            for item in items:
                lines.append(f"- `{item}`" if code else f"- {item}")
        else:
            lines.append("- _None recorded._")
        lines.append("")

    section("Decisions", note.decisions)
    section("Actions", note.actions)
    section("Topics", note.topics)
    section("Files Touched", note.files_touched, code=True)
    section("Open Questions", note.questions)
    if note.facts:
        section("Key Facts", note.facts)

    lines.append("## Contradictions Resolved")
    if note.contradictions:
        for c in note.contradictions:
            lines.append(
                f"- **{c['old_fact']}** → **{c['new_fact']}** — {c['resolution']}"
            )
    else:
        lines.append("- _None detected._")
    lines.append("")

    lines.append("## Sessions Processed")
    for session in note.sessions_processed:
        lines.append(f"- `{session}`")
    lines.append("")
    return "\n".join(lines)


# ── The daemon ────────────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConsolidationDaemon:
    """Background consolidation of recent session logs into a daily merged note.

    The daemon is safe to construct against a non-existent vault; every method
    degrades gracefully. ``run_once`` is the unit of work (call it from a
    scheduler); ``start``/``stop`` wrap it in a simple interruptible loop for
    standalone background operation.
    """

    def __init__(
        self,
        vault_path: Path | str,
        interval_hours: float = DEFAULT_INTERVAL_HOURS,
        *,
        use_llm: bool = True,
        llm_client: Any | None = None,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.vault_path = Path(os.path.expanduser(str(vault_path)))
        self.interval_hours = interval_hours
        self.use_llm = use_llm
        self._llm_client = llm_client
        self._now = now
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ── Paths ──────────────────────────────────────────────────────────────────

    @property
    def sessions_dir(self) -> Path:
        return self.vault_path / SESSIONS_SUBDIR

    @property
    def consolidated_dir(self) -> Path:
        return self.vault_path.joinpath(*CONSOLIDATED_SUBDIR)

    @property
    def watermark_path(self) -> Path:
        return self.vault_path / ".eidetic" / WATERMARK_NAME

    @property
    def _lock_target(self) -> Path:
        return self.vault_path / ".eidetic" / LOCK_TARGET_NAME

    # ── Watermark ──────────────────────────────────────────────────────────────

    def read_last_consolidation(self) -> datetime | None:
        """Last consolidation time, or ``None`` if there has never been one."""
        try:
            raw = self.watermark_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not raw:
            return None
        try:
            stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)

    def write_last_consolidation(self, when: datetime) -> None:
        """Persist the consolidation watermark atomically-ish."""
        self.watermark_path.parent.mkdir(parents=True, exist_ok=True)
        self.watermark_path.write_text(when.isoformat(), encoding="utf-8")

    # ── Scan ───────────────────────────────────────────────────────────────────

    def scan_recent_sessions(self) -> list[Path]:
        """Session logs modified since the last consolidation, oldest first.

        Returns ``[]`` if the sessions directory is absent. With no prior
        watermark, every session log is returned (the first-ever pass).
        """
        if not self.sessions_dir.is_dir():
            return []
        last = self.read_last_consolidation()
        cutoff = last.timestamp() if last else None
        logs = [
            p for p in self.sessions_dir.glob("session-log-*.md") if p.is_file()
        ]
        if cutoff is not None:
            logs = [p for p in logs if p.stat().st_mtime > cutoff]
        logs.sort(key=lambda p: p.stat().st_mtime)
        return logs

    # ── Extraction (LLM with heuristic fallback) ───────────────────────────────

    def _resolve_llm_client(self) -> Any | None:
        if not self.use_llm:
            return None
        if self._llm_client is not None:
            return self._llm_client
        try:  # backends is optional at runtime; never let detection crash a pass
            from eidetic_os import backends as llm_backends

            self._llm_client = llm_backends.get_client()
        except Exception:  # noqa: BLE001 - no backend reachable is the common case
            self._llm_client = None
        return self._llm_client

    def extract_session(self, path: Path) -> SessionTakeaways:
        """Extract takeaways from one session log, enriched with #22 facts if present.

        Heuristic extraction is always run; when the optional fact extractor is
        available its output is attached as ``facts`` (kept separate from the
        decision list so contradiction resolution stays clean).
        """
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return SessionTakeaways(session_file=path.name)
        takeaways = heuristic_takeaways(text, path.name)
        facts = facts_for(text) if FACTS_AVAILABLE else []
        return replace(takeaways, facts=facts) if facts else takeaways

    # ── The pass ───────────────────────────────────────────────────────────────

    def run_once(self) -> ConsolidatedNote | None:
        """Run a single consolidation pass; return the note, or ``None`` if no-op.

        Steps: take the single-writer lock → scan for new session logs → extract
        each → merge (resolving contradictions, most-recent-wins) → write the
        consolidated note → advance the watermark → audit. A missing vault, no new
        logs, or a lock held by another run all return ``None`` without raising.
        """
        trigger = os.environ.get("EIDETIC_TRIGGER", "cli")
        if not self.vault_path.is_dir():
            audit.log_action(
                "consolidate", trigger, "skipped",
                context=f"consolidate {self.vault_path}",
                error="vault path does not exist",
            )
            return None

        self._lock_target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with vault_lock(self._lock_target, timeout=1.0):
                return self._run_locked(trigger)
        except LockTimeout:
            audit.log_action(
                "consolidate", trigger, "skipped",
                context=f"consolidate {self.vault_path}",
                error="another consolidation run holds the lock",
            )
            return None

    def _decay_facts(self) -> None:
        """Refresh fact relevance scores as a side effect of consolidation (#27).

        Best-effort and fully optional: opens the conventional fact store at this
        vault, runs a :class:`~eidetic_os.memory_scoring.MemoryScorer.decay_all`
        pass, and records the outcome in the audit trail. Any failure — the facts
        module absent, the store missing, a bad config — is swallowed so a decay
        hiccup can never derail a consolidation run.
        """
        try:
            from eidetic_os.facts import FactStore
            from eidetic_os.memory_scoring import MemoryScorer
        except Exception:  # noqa: BLE001 - facts/scoring not present → skip silently
            return
        db_path = self.vault_path / ".eidetic" / "facts.db"
        if not db_path.exists():
            return
        try:
            store = FactStore(db_path)
        except Exception:  # noqa: BLE001 - unreadable store → skip
            return
        try:
            summary = MemoryScorer(store).decay_all(now=self._now())
        except Exception as exc:  # noqa: BLE001 - a bad pass must not break consolidation
            audit.log_action(
                "memory-decay", os.environ.get("EIDETIC_TRIGGER", "scheduled"),
                "error", context=f"decay {db_path}",
                error=f"{type(exc).__name__}: {exc}",
            )
            return
        finally:
            store.close()
        if summary.scored:
            audit.log_action(
                "memory-decay", os.environ.get("EIDETIC_TRIGGER", "scheduled"),
                "success",
                changes=[
                    f"{summary.scored} fact(s) rescored",
                    f"{summary.deactivated} deactivated",
                ],
                context=f"decay {db_path}",
            )

    def _compact_tiers(self) -> None:
        """Rebalance the tiered-memory hierarchy each pass (#31).

        Best-effort and fully optional, mirroring :meth:`_decay_facts`: opens the
        conventional fact store at this vault, runs a
        :meth:`~eidetic_os.memory_tiers.TieredMemory.compact` pass (re-tier by the
        freshly decayed relevance scores, then enforce the Core/Recall size
        limits), and records the outcome in the audit trail. Any failure — the
        module absent, the store missing, a bad config — is swallowed so a tiering
        hiccup can never derail a consolidation run.
        """
        try:
            from eidetic_os.facts import FactStore
            from eidetic_os.memory_tiers import TieredMemory
        except Exception:  # noqa: BLE001 - tiers module not present → skip silently
            return
        db_path = self.vault_path / ".eidetic" / "facts.db"
        if not db_path.exists():
            return
        try:
            store = FactStore(db_path)
        except Exception:  # noqa: BLE001 - unreadable store → skip
            return
        try:
            result = TieredMemory(store=store).compact()
        except Exception as exc:  # noqa: BLE001 - a bad pass must not break consolidation
            audit.log_action(
                "memory-compact", os.environ.get("EIDETIC_TRIGGER", "scheduled"),
                "error", context=f"compact {db_path}",
                error=f"{type(exc).__name__}: {exc}",
            )
            return
        finally:
            store.close()
        counts = result.stats.counts
        audit.log_action(
            "memory-compact", os.environ.get("EIDETIC_TRIGGER", "scheduled"),
            "success",
            changes=[
                f"{result.retiered} re-tiered",
                f"{result.demoted_core + result.demoted_recall} demoted (limits)",
                f"core={counts.get('core', 0)} recall={counts.get('recall', 0)} "
                f"archival={counts.get('archival', 0)}",
            ],
            context=f"compact {db_path}",
        )

    def _run_locked(self, trigger: str) -> ConsolidatedNote | None:
        started = self._now()
        # Refresh fact relevance every pass, independent of new session content.
        self._decay_facts()
        # Then rebalance the memory tiers against those fresh relevance scores.
        self._compact_tiers()
        sessions = self.scan_recent_sessions()
        if not sessions:
            # Still advance the watermark so an empty pass isn't repeated forever.
            self.write_last_consolidation(started)
            audit.log_action(
                "consolidate", trigger, "skipped",
                context=f"consolidate {self.vault_path}",
                error="no new session logs since last consolidation",
            )
            return None

        takeaways = [self.extract_session(p) for p in sessions]
        takeaways = [t for t in takeaways if not t.is_empty] or takeaways
        date = started.astimezone().strftime("%Y-%m-%d")
        summary = self._maybe_llm_summary(takeaways)
        note = merge_takeaways(takeaways, date=date, summary=summary)

        out_path = self._write_note(note)
        self.write_last_consolidation(started)
        audit.log_action(
            "consolidate", trigger, "success",
            changes=[
                f"{len(sessions)} session(s)",
                f"{len(note.decisions)} decision(s)",
                f"{len(note.contradictions)} contradiction(s)",
                f"wrote {out_path.name}",
            ],
            context=f"consolidate {self.vault_path}",
        )
        return note

    def _maybe_llm_summary(
        self, takeaways: Sequence[SessionTakeaways]
    ) -> str | None:
        """Ask the LLM for a prose summary; fall back to ``None`` (heuristic)."""
        client = self._resolve_llm_client()
        if client is None:
            return None
        try:  # pragma: no cover - requires a live backend
            from eidetic_os import backends as llm_backends

            bullets = "\n".join(
                f"- {d}" for t in takeaways for d in (t.decisions + t.actions)
            )[:4000]
            prompt = (
                "Summarise these consolidated session takeaways in 2-3 sentences "
                "of plain prose, no preamble:\n\n" + bullets
            )
            result = llm_backends.run_inference(client, prompt, max_tokens=200)
            if result.ok and result.content.strip():
                return result.content.strip()
        except Exception:  # noqa: BLE001 - any backend failure → heuristic summary
            return None
        return None

    def _write_note(self, note: ConsolidatedNote) -> Path:
        """Write the consolidated note under ``wiki/consolidated/`` (lock-guarded)."""
        self.consolidated_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.consolidated_dir / f"{note.date}.md"
        with vault_lock(out_path):
            out_path.write_text(render_note(note), encoding="utf-8")
        return out_path

    # ── Background loop ─────────────────────────────────────────────────────────

    def _loop(self) -> None:
        interval_seconds = max(1.0, self.interval_hours * 3600.0)
        # Run once immediately, then on the interval until stopped.
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:  # noqa: BLE001 - a bad pass must not kill the loop
                audit.log_action(
                    "consolidate", "scheduled", "error",
                    context=f"consolidate {self.vault_path}",
                    error=f"{type(exc).__name__}: {exc}",
                )
            # Interruptible sleep: stop() wakes us immediately.
            self._stop.wait(interval_seconds)

    def start(self) -> None:
        """Start the background consolidation loop (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="eidetic-consolidation", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        """Signal the loop to stop and wait for the thread to finish."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


def consolidation_status(vault_path: Path | str) -> dict[str, Any]:
    """Inspect consolidation state without running a pass (for ``--status``).

    Returns the last consolidation time, the count of session logs pending, and
    how many consolidated notes already exist — all read-only.
    """
    daemon = ConsolidationDaemon(vault_path)
    last = daemon.read_last_consolidation()
    pending = daemon.scan_recent_sessions()
    consolidated = (
        sorted(daemon.consolidated_dir.glob("*.md"))
        if daemon.consolidated_dir.is_dir() else []
    )
    return {
        "vault_path": str(daemon.vault_path),
        "vault_exists": daemon.vault_path.is_dir(),
        "last_consolidation": last.isoformat() if last else None,
        "sessions_pending": len(pending),
        "pending_files": [p.name for p in pending],
        "consolidated_notes": len(consolidated),
        "latest_note": consolidated[-1].name if consolidated else None,
        "facts_integration": FACTS_AVAILABLE,
    }
