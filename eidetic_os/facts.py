"""Mem0-style fact extraction and a deduplicated fact store for Eidetic OS.

Eidetic OS used to remember by appending whole session transcripts to the vault.
That preserves everything — including the noise: corrections, tangents, dead
ends, and the same preference restated five times. Retrieval then has to wade
through all of it.

This module takes the Mem0 approach instead: distil a conversation into a
handful of *discrete facts*, and store each one once. A fact is a single,
self-contained statement ("Paul prefers ``uv`` over pip", "the trading bot uses
Kelly Criterion sizing") tagged with a category, a confidence, and the source it
came from. Before a new fact is stored it is compared against what is already
known, so the store converges on a deduplicated, contradiction-resolved set of
beliefs rather than an ever-growing pile of transcript.

Two halves:

* :func:`extract_facts` turns raw text into candidate facts. It prefers a local
  LLM (whatever :mod:`eidetic_os.backends` detects — LM Studio, Ollama, …) with a
  structured extraction prompt, and falls back to a dependency-free heuristic
  extractor when no backend is reachable. The fallback is deliberately decent on
  its own: most useful facts announce themselves with decision words ("decided",
  "will use"), preference words ("prefer", "always", "never"), version/config
  mentions, or capitalised entities.

* :class:`FactStore` is a SQLite-backed store — same single-file, lazy-schema
  approach as :mod:`eidetic_os.vectordb` — that handles dedup, contradiction,
  semantic search, context selection, and time-decay. Embeddings are optional:
  given an embedder it deduplicates and searches by cosine similarity; without
  one it falls back to token-overlap similarity so the store still works fully
  offline.

Nothing here is required to touch the network — pass ``embed_fn=None`` (the
default) and the store is entirely local and synchronous.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from array import array
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

# An embedder maps a batch of texts to their vectors. Kept abstract so the store
# never depends on a particular backend — the CLI wires in one backed by the
# detected LLM, and tests pass a tiny deterministic stand-in (or None).
Embedder = Callable[[Sequence[str]], list[list[float]]]

# The fact categories we recognise. ``other`` is the catch-all so a category is
# always one of a known set (useful for `facts stats` and category filters).
CATEGORIES: Final = (
    "preference",  # how the user likes to work / what they want
    "decision",    # a choice that was made
    "technical",   # a version, config, import, or technical fact
    "person",      # a person and their attributes/relationships
    "project",     # a project, its goals, or its constraints
    "other",       # anything genuinely useful that fits none of the above
)
_DEFAULT_CATEGORY: Final = "other"

# Similarity at/above which two facts are "about the same thing" and dedup kicks
# in. Below it they are treated as independent and both kept.
DEFAULT_DEDUP_THRESHOLD: Final = 0.85
# At/above this, two facts are treated as the *same* statement (a pure duplicate)
# rather than an extension — we bump the existing row instead of merging.
_DUPLICATE_THRESHOLD: Final = 0.97


# ── Embedding (de)serialisation ───────────────────────────────────────────────
# Same little-endian float32 packing as vectordb, kept local so this module is
# self-contained (rag.py likewise carries its own cosine rather than coupling to
# vectordb's private helpers).

def _pack(vec: Sequence[float]) -> bytes:
    return array("f", vec).tobytes()


def _unpack(blob: bytes) -> list[float]:
    arr = array("f")
    arr.frombytes(blob)
    return arr.tolist()


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two equal-length vectors (0.0 if either is zero)."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


_WORD_RE: Final = re.compile(r"\w+")
# "Stop" words carry no topical signal, so they're dropped before the token-overlap
# similarity used when no embedder is available — otherwise two unrelated facts
# look similar merely for sharing "the", "is", "a", …
_STOPWORDS: Final = frozenset(
    "a an and are as at be but by for if in into is it its of on or s such t that "
    "the their then there these they this to was will with i you we he she them his "
    "her our your my me do does did has have had not no".split()
)


def _content_tokens(text: str) -> set[str]:
    return {t for t in _WORD_RE.findall(text.lower()) if t not in _STOPWORDS}


def _token_similarity(a: str, b: str) -> float:
    """Jaccard overlap of the content words of two strings (the no-embedder path)."""
    ta, tb = _content_tokens(a), _content_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── Candidate facts (extraction output) ───────────────────────────────────────

@dataclass(frozen=True)
class ExtractedFact:
    """A single candidate fact produced by :func:`extract_facts`, pre-storage."""

    fact: str
    category: str = _DEFAULT_CATEGORY
    confidence: float = 0.6

    def normalised(self) -> ExtractedFact:
        """Trimmed text, a known category, and a confidence clamped to [0, 1]."""
        category = self.category if self.category in CATEGORIES else _DEFAULT_CATEGORY
        return ExtractedFact(
            fact=" ".join(self.fact.split()),
            category=category,
            confidence=min(1.0, max(0.0, float(self.confidence))),
        )


@dataclass(frozen=True)
class StoredFact:
    """A fact as it lives in the store (a row of the ``facts`` table)."""

    id: int
    fact: str
    source: str
    created_at: str
    last_accessed: str
    access_count: int
    confidence: float
    category: str
    active: bool


# ── LLM extraction ────────────────────────────────────────────────────────────

_EXTRACTION_SYSTEM: Final = (
    "You extract durable, reusable facts from text for a personal memory system. "
    "A good fact is a single, self-contained statement that is still true and "
    "useful days later: a preference, a decision, a technical detail (version, "
    "config, tool), a fact about a person, or a fact about a project. Ignore "
    "small talk, questions, transient state, and anything that only makes sense "
    "in the moment. Resolve pronouns to concrete subjects where you can."
)

_EXTRACTION_INSTRUCTION: Final = (
    "Extract the facts from the text below. Respond with ONLY a JSON array; no "
    "prose, no code fences. Each element is an object with keys: \"fact\" (the "
    "statement, one sentence), \"category\" (one of: preference, decision, "
    "technical, person, project, other), and \"confidence\" (0.0-1.0). If there "
    "are no durable facts, respond with []."
    "\n\nText:\n"
)


def _build_extraction_messages(text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _EXTRACTION_SYSTEM},
        {"role": "user", "content": _EXTRACTION_INSTRUCTION + text},
    ]


def _extract_json_array(content: str) -> list[dict[str, Any]] | None:
    """Pull the first JSON array out of a model response (tolerant of fencing)."""
    content = content.strip()
    if content.startswith("```"):
        # Strip a ```json … ``` fence the model may have added despite instructions.
        content = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", content).strip()
    start = content.find("[")
    end = content.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def _facts_from_payload(payload: list[dict[str, Any]]) -> list[ExtractedFact]:
    out: list[ExtractedFact] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        statement = str(item.get("fact", "")).strip()
        if not statement:
            continue
        try:
            confidence = float(item.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        out.append(
            ExtractedFact(
                fact=statement,
                category=str(item.get("category", _DEFAULT_CATEGORY)).strip().lower(),
                confidence=confidence,
            ).normalised()
        )
    return out


def extract_facts_llm(
    text: str,
    client: Any,
    *,
    timeout: float = 60.0,
    max_tokens: int = 1024,
) -> list[ExtractedFact] | None:
    """Extract facts via an OpenAI-compatible chat backend, or ``None`` on failure.

    ``client`` is an :class:`eidetic_os.backends.Client` (or anything exposing
    ``chat_url``, ``headers()``, and ``model``). Returns ``None`` — rather than
    raising — if the backend is unreachable or its reply can't be parsed, so the
    caller can fall back to the heuristic extractor.
    """
    import requests  # local import: the heuristic path needs no network deps

    payload = {
        "model": getattr(client, "model", "local-model"),
        "messages": _build_extraction_messages(text),
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    try:
        resp = requests.post(
            client.chat_url, headers=client.headers(), json=payload, timeout=timeout
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None
    parsed = _extract_json_array(str(content))
    if parsed is None:
        return None
    return _facts_from_payload(parsed)


# ── Heuristic extraction (offline fallback) ───────────────────────────────────

# Cue phrases that mark a sentence as carrying a particular kind of fact. Order
# matters only for category assignment (first match wins); a sentence with no cue
# but a strong shape (a version, a capitalised entity) is still captured.
_DECISION_CUES: Final = (
    "decided", "decide to", "chose", "choosing", "will use", "going with",
    "agreed", "we'll use", "let's use", "settled on", "switching to", "migrate to",
)
_PREFERENCE_CUES: Final = (
    "prefer", "i like", "we like", "don't want", "do not want", "always",
    "never", "i'd rather", "rather than", "favou", "dislike", "hate",
)
_PERSON_CUES: Final = (
    " is the ", " works as", " is a ", " is our", " is responsible", " leads ",
    " manages ", " reports to", "'s role",
)
_PROJECT_CUES: Final = (
    "project", "milestone", "roadmap", "deadline", "sprint", "release", "goal is",
    "objective", "deliverable",
)

_VERSION_RE: Final = re.compile(
    r"\b(?:v?\d+\.\d+(?:\.\d+)?|python\s*3\.\d+|node\s*\d+)\b", re.IGNORECASE
)
_CONFIG_RE: Final = re.compile(
    r"\b(?:import|from|pip install|uv add|npm install|export|--?[a-z][\w-]+=|"
    r"localhost:\d+|\d+\.\d+\.\d+\.\d+)\b",
    re.IGNORECASE,
)
_ENTITY_RE: Final = re.compile(r"\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){1,3})\b")
_SENTENCE_SPLIT_RE: Final = re.compile(r"(?<=[.!?])\s+|\n+")
_MD_NOISE_RE: Final = re.compile(r"^[\s>#*\-\d.)\]\[]+|[\s*_`]+$")


def _clean_sentence(raw: str) -> str:
    """Strip markdown bullet/heading noise and surrounding whitespace."""
    line = raw.strip()
    line = _MD_NOISE_RE.sub("", line)
    return line.strip()


def _categorise(sentence: str) -> tuple[str, float] | None:
    """Classify a sentence, returning ``(category, confidence)`` or ``None``.

    ``None`` means "no fact here". The confidence reflects how strong the signal
    is: an explicit decision/preference cue scores higher than a bare version
    mention or a capitalised entity, which are weaker (and noisier) signals.
    """
    lowered = sentence.lower()
    if any(cue in lowered for cue in _DECISION_CUES):
        return ("decision", 0.7)
    if any(cue in lowered for cue in _PREFERENCE_CUES):
        return ("preference", 0.7)
    if _CONFIG_RE.search(sentence) or _VERSION_RE.search(sentence):
        return ("technical", 0.6)
    if any(cue in lowered for cue in _PROJECT_CUES):
        return ("project", 0.55)
    if any(cue in lowered for cue in _PERSON_CUES):
        return ("person", 0.55)
    # A multi-word proper noun with a verb is often a worthwhile relational fact.
    if _ENTITY_RE.search(sentence) and len(sentence.split()) >= 4:
        return ("other", 0.4)
    return None


def extract_facts_heuristic(text: str) -> list[ExtractedFact]:
    """Extract facts with rules only — no LLM, no network, no dependencies.

    Splits ``text`` into sentences and keeps those that look like durable facts:
    decisions, preferences, technical/config statements, project notes, person
    facts, or sentences anchored by a multi-word proper noun. Duplicate sentences
    are collapsed. Designed to degrade gracefully, not to be perfect.
    """
    seen: set[str] = set()
    facts: list[ExtractedFact] = []
    for chunk in _SENTENCE_SPLIT_RE.split(text):
        sentence = _clean_sentence(chunk)
        # Skip empties, fragments, and over-long run-ons that aren't single facts.
        if not (4 <= len(sentence.split()) <= 60):
            continue
        if sentence.endswith("?"):
            continue
        verdict = _categorise(sentence)
        if verdict is None:
            continue
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        category, confidence = verdict
        facts.append(ExtractedFact(sentence, category, confidence).normalised())
    return facts


def extract_facts(
    text: str,
    source: str = "",
    *,
    client: Any | None = None,
    use_llm: bool = True,
) -> list[ExtractedFact]:
    """Extract candidate facts from ``text`` (LLM if available, else heuristic).

    ``source`` is accepted for symmetry with the rest of the pipeline (and so
    callers can pass it positionally) but isn't needed to do the extraction — it
    is attached when the facts are stored. When ``use_llm`` is true and a
    ``client`` is given (or one can be detected), the LLM extractor runs first; if
    it is unreachable or returns nothing parseable, the heuristic extractor runs.
    """
    if not text or not text.strip():
        return []

    if use_llm:
        resolved = client or _detect_client()
        if resolved is not None:
            llm_facts = extract_facts_llm(text, resolved)
            if llm_facts:  # non-empty → trust it; empty/None → fall through
                return llm_facts
    return extract_facts_heuristic(text)


def _detect_client() -> Any | None:
    """Best-effort LLM client from the detected backend, or ``None`` if down."""
    try:
        from eidetic_os import backends
    except ImportError:
        return None
    try:
        return backends.get_client()
    except backends.BackendError:
        return None


# ── Relation classification (dedup decisions) ─────────────────────────────────

# Polarity-flipping cues — genuine grammatical negators only. Two otherwise-similar
# facts with *opposite* polarity are a contradiction (one supersedes the other),
# not a duplicate. Status words like "deprecated" are deliberately excluded: they
# describe a subject rather than negate the statement, so they must not make a
# fact and its negation ("X is deprecated" vs "X is not deprecated") read alike.
_NEGATION_CUES: Final = (
    "not", "no longer", "don't", "do not", "doesn't", "never", "stop", "stopped",
    "instead", "without", "won't", "cannot", "can't",
)


def _polarity(text: str) -> bool:
    """Coarse boolean polarity: does the statement read as negated?"""
    lowered = f" {text.lower()} "
    return any(f" {cue} " in lowered or lowered.startswith(f"{cue} ")
               for cue in _NEGATION_CUES)


@dataclass(frozen=True)
class DedupResult:
    """The outcome of comparing a new fact against the store.

    ``action`` is one of ``"insert"`` (no near-match — store as new),
    ``"duplicate"`` (a near-identical fact exists — bump it), ``"supersede"`` (a
    contradicting fact exists — deactivate it and store the new one), or
    ``"merge"`` (an overlapping fact exists — combine them). ``match_id`` is the
    existing fact involved (``None`` for ``insert``), and ``similarity`` is the
    cosine/token score that drove the decision.
    """

    action: str
    match_id: int | None
    similarity: float
    merged_text: str | None = None


def classify_relation(
    new_text: str, existing_text: str, similarity: float
) -> str:
    """Decide how a new fact relates to a near-duplicate existing one.

    Returns ``"duplicate"``, ``"supersede"``, or ``"merge"``. Assumes the caller
    has already established the two are similar enough to be "about the same
    thing"; this only distinguishes *how*.
    """
    if _polarity(new_text) != _polarity(existing_text):
        return "supersede"
    if similarity >= _DUPLICATE_THRESHOLD:
        return "duplicate"
    a, b = new_text.strip().lower(), existing_text.strip().lower()
    if a == b:
        return "duplicate"
    # One statement fully contains the other → the longer extends the shorter.
    if a in b or b in a:
        return "merge"
    return "merge"


def _merge_text(new_text: str, existing_text: str) -> str:
    """Combine two overlapping facts, preferring the more informative (longer) one."""
    new_t, existing_t = new_text.strip(), existing_text.strip()
    if new_t.lower() in existing_t.lower():
        return existing_t
    if existing_t.lower() in new_t.lower():
        return new_t
    return f"{existing_t} ({new_t})"


# ── The store ─────────────────────────────────────────────────────────────────

class FactStore:
    """A SQLite store of discrete, deduplicated facts.

    Open one with ``FactStore(path)`` (a ``.db`` file, or ``":memory:"`` for
    tests). Pass ``embed_fn`` to enable semantic dedup and search; omit it and the
    store falls back to token-overlap similarity, staying fully offline. The
    schema is created lazily, so opening against a fresh path just works.
    """

    def __init__(self, path: str | Path, *, embed_fn: Embedder | None = None) -> None:
        self.path = str(path)
        self.embed_fn = embed_fn
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> FactStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── schema ────────────────────────────────────────────────────────────────
    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS facts (
                id            INTEGER PRIMARY KEY,
                fact          TEXT NOT NULL,
                source        TEXT DEFAULT '',
                created_at    TIMESTAMP NOT NULL,
                last_accessed TIMESTAMP NOT NULL,
                access_count  INTEGER NOT NULL DEFAULT 0,
                confidence    REAL NOT NULL DEFAULT 0.6,
                category      TEXT NOT NULL DEFAULT 'other',
                embedding     BLOB,
                active        INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_facts_active ON facts(active);
            CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
            """
        )
        self._conn.commit()

    # ── embedding helper ──────────────────────────────────────────────────────
    def _embed_one(self, text: str) -> list[float] | None:
        """Embed a single string, or ``None`` if no embedder / it failed."""
        if self.embed_fn is None:
            return None
        try:
            vectors = self.embed_fn([text])
        except Exception:
            return None
        return vectors[0] if vectors else None

    # ── writes ────────────────────────────────────────────────────────────────
    def add_fact(
        self,
        fact: str,
        source: str = "",
        *,
        category: str = _DEFAULT_CATEGORY,
        confidence: float = 0.6,
        embedding: Sequence[float] | None = None,
    ) -> int:
        """Insert a fact unconditionally (no dedup). Returns the new row id.

        Most callers want :meth:`ingest`, which deduplicates first; this is the
        low-level primitive it (and tests) build on.
        """
        if category not in CATEGORIES:
            category = _DEFAULT_CATEGORY
        if embedding is None:
            embedding = self._embed_one(fact)
        now = _now_iso()
        cur = self._conn.execute(
            "INSERT INTO facts(fact, source, created_at, last_accessed, "
            "access_count, confidence, category, embedding, active) "
            "VALUES(?, ?, ?, ?, 0, ?, ?, ?, 1)",
            (
                " ".join(fact.split()), source, now, now,
                min(1.0, max(0.0, confidence)), category,
                _pack(embedding) if embedding is not None else None,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid or 0)

    def touch(self, fact_id: int) -> None:
        """Record an access: bump ``access_count`` and ``last_accessed``."""
        self._conn.execute(
            "UPDATE facts SET access_count = access_count + 1, last_accessed = ? "
            "WHERE id = ?",
            (_now_iso(), fact_id),
        )
        self._conn.commit()

    def deactivate(self, fact_id: int) -> None:
        """Soft-delete a fact (mark it superseded) without removing the row."""
        self._conn.execute("UPDATE facts SET active = 0 WHERE id = ?", (fact_id,))
        self._conn.commit()

    def update_text(self, fact_id: int, text: str, embedding: Sequence[float] | None) -> None:
        """Replace a fact's statement (and embedding), used by the merge path."""
        self._conn.execute(
            "UPDATE facts SET fact = ?, embedding = ?, last_accessed = ? WHERE id = ?",
            (
                " ".join(text.split()),
                _pack(embedding) if embedding is not None else None,
                _now_iso(),
                fact_id,
            ),
        )
        self._conn.commit()

    # ── dedup ─────────────────────────────────────────────────────────────────
    def deduplicate(
        self,
        new_fact: str,
        *,
        embedding: Sequence[float] | None = None,
        threshold: float = DEFAULT_DEDUP_THRESHOLD,
    ) -> DedupResult:
        """Compare ``new_fact`` against active facts and decide what to do.

        Returns a :class:`DedupResult` describing the action — but does **not**
        apply it; :meth:`ingest` does that. Similarity is cosine over embeddings
        when both sides have one, else token overlap. The closest active fact
        above ``threshold`` drives the decision.
        """
        candidates = self._active_rows_with_embeddings()
        best_id: int | None = None
        best_text = ""
        best_sim = 0.0
        for row in candidates:
            other = row["fact"]
            if embedding is not None and row["embedding"] is not None:
                sim = _cosine(embedding, _unpack(row["embedding"]))
            else:
                sim = _token_similarity(new_fact, other)
            if sim > best_sim:
                best_sim, best_id, best_text = sim, row["id"], other

        if best_id is None or best_sim < threshold:
            return DedupResult("insert", None, best_sim)

        relation = classify_relation(new_fact, best_text, best_sim)
        if relation == "merge":
            return DedupResult(
                "merge", best_id, best_sim, merged_text=_merge_text(new_fact, best_text)
            )
        return DedupResult(relation, best_id, best_sim)

    def ingest(
        self,
        facts: Iterable[ExtractedFact],
        source: str = "",
        *,
        threshold: float = DEFAULT_DEDUP_THRESHOLD,
    ) -> dict[str, int]:
        """Store extracted facts, deduplicating each against the live store.

        Returns a tally keyed by the action taken: ``inserted``, ``duplicate``,
        ``superseded``, ``merged``. Facts are processed in turn, so a new fact can
        dedup against one inserted earlier in the same call.
        """
        tally = {"inserted": 0, "duplicate": 0, "superseded": 0, "merged": 0}
        for candidate in facts:
            candidate = candidate.normalised()
            if not candidate.fact:
                continue
            embedding = self._embed_one(candidate.fact)
            result = self.deduplicate(
                candidate.fact, embedding=embedding, threshold=threshold
            )
            if result.action == "insert":
                self.add_fact(
                    candidate.fact, source,
                    category=candidate.category, confidence=candidate.confidence,
                    embedding=embedding,
                )
                tally["inserted"] += 1
            elif result.action == "duplicate" and result.match_id is not None:
                self.touch(result.match_id)
                tally["duplicate"] += 1
            elif result.action == "supersede" and result.match_id is not None:
                self.deactivate(result.match_id)
                self.add_fact(
                    candidate.fact, source,
                    category=candidate.category, confidence=candidate.confidence,
                    embedding=embedding,
                )
                tally["superseded"] += 1
            elif result.action == "merge" and result.match_id is not None:
                merged = result.merged_text or candidate.fact
                self.update_text(result.match_id, merged, self._embed_one(merged))
                self.touch(result.match_id)
                tally["merged"] += 1
        return tally

    def extract_and_ingest(
        self,
        text: str,
        source: str = "",
        *,
        client: Any | None = None,
        use_llm: bool = True,
        threshold: float = DEFAULT_DEDUP_THRESHOLD,
    ) -> dict[str, int]:
        """Convenience: :func:`extract_facts` then :meth:`ingest` in one call."""
        extracted = extract_facts(text, source, client=client, use_llm=use_llm)
        return self.ingest(extracted, source, threshold=threshold)

    # ── reads ─────────────────────────────────────────────────────────────────
    def _active_rows_with_embeddings(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT id, fact, embedding FROM facts WHERE active = 1"
        ).fetchall()

    @staticmethod
    def _row_to_fact(row: sqlite3.Row) -> StoredFact:
        return StoredFact(
            id=int(row["id"]),
            fact=row["fact"],
            source=row["source"] or "",
            created_at=row["created_at"],
            last_accessed=row["last_accessed"],
            access_count=int(row["access_count"]),
            confidence=float(row["confidence"]),
            category=row["category"],
            active=bool(row["active"]),
        )

    def count(self, *, active_only: bool = True) -> int:
        """Number of facts (active only by default)."""
        sql = "SELECT COUNT(*) FROM facts"
        if active_only:
            sql += " WHERE active = 1"
        return int(self._conn.execute(sql).fetchone()[0])

    def get(self, fact_id: int) -> StoredFact | None:
        row = self._conn.execute(
            "SELECT * FROM facts WHERE id = ?", (fact_id,)
        ).fetchone()
        return self._row_to_fact(row) if row else None

    def list_facts(
        self,
        *,
        category: str | None = None,
        limit: int = 50,
        active_only: bool = True,
    ) -> list[StoredFact]:
        """List facts, newest first, optionally filtered by category."""
        clauses: list[str] = []
        params: list[Any] = []
        if active_only:
            clauses.append("active = 1")
        if category:
            clauses.append("category = ?")
            params.append(category)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM facts{where} ORDER BY id DESC LIMIT ?", params
        ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def query_facts(
        self,
        query: str,
        *,
        limit: int = 10,
        record_access: bool = True,
    ) -> list[tuple[StoredFact, float]]:
        """Semantic search over active facts. Returns ``(fact, score)`` best-first.

        Scores are cosine similarity when an embedder is configured, else token
        overlap. Returned facts are ``touch``-ed (access recorded) unless
        ``record_access`` is false — searching for a fact is using it.
        """
        query_embedding = self._embed_one(query)
        rows = self._conn.execute(
            "SELECT * FROM facts WHERE active = 1"
        ).fetchall()
        scored: list[tuple[StoredFact, float]] = []
        for row in rows:
            if query_embedding is not None and row["embedding"] is not None:
                score = _cosine(query_embedding, _unpack(row["embedding"]))
            else:
                score = _token_similarity(query, row["fact"])
            if score > 0:
                scored.append((self._row_to_fact(row), score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        top = scored[:limit]
        if record_access:
            for fact, _ in top:
                self.touch(fact.id)
        return top

    def get_facts_for_context(
        self,
        *,
        categories: Sequence[str] | None = None,
        limit: int = 50,
    ) -> list[StoredFact]:
        """Most relevant active facts for context injection.

        Ranked by a simple salience proxy — confidence weighted by how often the
        fact has been accessed — so confident, frequently-used facts surface
        first. Optionally restricted to ``categories``.
        """
        clauses = ["active = 1"]
        params: list[Any] = []
        if categories:
            placeholders = ",".join("?" for _ in categories)
            clauses.append(f"category IN ({placeholders})")
            params.extend(categories)
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM facts WHERE {' AND '.join(clauses)} "
            f"ORDER BY confidence * (1 + access_count) DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    # ── maintenance ───────────────────────────────────────────────────────────
    def decay_scores(
        self,
        *,
        half_life_days: float = 30.0,
        min_confidence: float = 0.05,
        now: datetime | None = None,
    ) -> int:
        """Apply time-based confidence decay to active facts.

        Each active fact's confidence is multiplied by ``0.5 ** (age / half_life)``
        where ``age`` is *whole days* since it was last accessed — so a fact
        untouched for one half-life loses half its confidence. Age is floored to a
        day because decay is a coarse maintenance pass (driven by the sleeptime
        daemon) and timestamps are stored at second precision; a fact accessed in
        the same run is age 0 and never decays. Facts that fall below
        ``min_confidence`` are deactivated (forgotten). Returns the number of
        facts whose confidence changed; ``now`` is injectable for testing.
        """
        reference = now or datetime.now(timezone.utc)
        rows = self._conn.execute(
            "SELECT id, confidence, last_accessed FROM facts WHERE active = 1"
        ).fetchall()
        changed = 0
        for row in rows:
            accessed = _parse_iso(row["last_accessed"])
            if accessed is None:
                continue
            age_days = math.floor(max(0.0, (reference - accessed).total_seconds() / 86400.0))
            if age_days == 0:
                continue
            factor = 0.5 ** (age_days / half_life_days)
            new_conf = float(row["confidence"]) * factor
            if new_conf < min_confidence:
                self._conn.execute(
                    "UPDATE facts SET confidence = ?, active = 0 WHERE id = ?",
                    (new_conf, row["id"]),
                )
            else:
                self._conn.execute(
                    "UPDATE facts SET confidence = ? WHERE id = ?",
                    (new_conf, row["id"]),
                )
            changed += 1
        self._conn.commit()
        return changed

    def stats(self) -> dict[str, Any]:
        """Aggregate counts for ``facts stats`` — totals, per-category, top sources."""
        total = self.count(active_only=False)
        active = self.count(active_only=True)
        per_category = {
            row["category"]: int(row["n"])
            for row in self._conn.execute(
                "SELECT category, COUNT(*) AS n FROM facts WHERE active = 1 "
                "GROUP BY category ORDER BY n DESC"
            )
        }
        sources = {
            row["source"]: int(row["n"])
            for row in self._conn.execute(
                "SELECT source, COUNT(*) AS n FROM facts WHERE active = 1 "
                "AND source != '' GROUP BY source ORDER BY n DESC LIMIT 10"
            )
        }
        avg_conf_row = self._conn.execute(
            "SELECT AVG(confidence) AS c FROM facts WHERE active = 1"
        ).fetchone()
        avg_conf = float(avg_conf_row["c"]) if avg_conf_row["c"] is not None else 0.0
        return {
            "total": total,
            "active": active,
            "superseded": total - active,
            "by_category": per_category,
            "by_source": sources,
            "avg_confidence": avg_conf,
            "has_embeddings": self.embed_fn is not None,
        }

    def clear(self) -> None:
        """Remove every fact (used by tests and a full reset)."""
        self._conn.execute("DELETE FROM facts")
        self._conn.commit()


# ── Embedder wiring + store location ──────────────────────────────────────────

def make_embedder(client: Any, *, timeout: float = 30.0) -> Embedder:
    """Build an :data:`Embedder` backed by an OpenAI-compatible embeddings API.

    ``client`` is an :class:`eidetic_os.backends.Client`. The returned callable
    batches texts in one request and returns vectors in input order. It raises on
    failure — :meth:`FactStore._embed_one` catches that and degrades to the
    token-overlap path, so a transient backend outage never breaks ingestion.
    """
    import requests

    def embed(texts: Sequence[str]) -> list[list[float]]:
        payload = {"model": client.embed_model, "input": list(texts)}
        resp = requests.post(
            client.embeddings_url, headers=client.headers(),
            json=payload, timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        ordered = sorted(data, key=lambda item: item["index"])
        return [item["embedding"] for item in ordered]

    return embed


def default_embedder() -> Embedder | None:
    """An embedder for the detected backend, or ``None`` if none is reachable."""
    client = _detect_client()
    return make_embedder(client) if client is not None else None


def facts_db_path() -> Path:
    """Resolve the facts DB path from the environment.

    Order: ``EIDETIC_FACTS_PATH`` → ``$VAULT_PATH/.eidetic/facts.db`` →
    ``./.eidetic/facts.db`` — mirroring how the audit log is located.
    """
    import os

    override = os.environ.get("EIDETIC_FACTS_PATH")
    if override:
        return Path(os.path.expanduser(override))
    vault = os.environ.get("VAULT_PATH")
    base = Path(os.path.expanduser(vault)) if vault else Path.cwd()
    return base / ".eidetic" / "facts.db"


def open_store(*, with_embedder: bool = True) -> FactStore:
    """Open (creating if needed) the conventional fact store.

    When ``with_embedder`` is set, the detected LLM backend's embeddings endpoint
    is wired in for semantic dedup/search; if no backend is reachable the store
    still opens and operates in offline token-overlap mode.
    """
    path = facts_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    embed_fn = default_embedder() if with_embedder else None
    return FactStore(path, embed_fn=embed_fn)
