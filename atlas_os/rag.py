"""Advanced RAG building blocks for the Atlas OS retrieval pipeline.

The original pipeline chunked on a fixed character window and ranked with raw
term-frequency. This module upgrades each stage with well-understood IR
techniques, kept as small, pure, dependency-free functions so they're easy to
test and reuse:

* **Semantic chunking** (:func:`semantic_chunk`) — split on heading and paragraph
  boundaries and pack whole paragraphs up to a token budget, instead of cutting
  mid-sentence at a fixed offset. Oversized paragraphs fall back to a windowed
  split. Every chunk still carries its nearest heading.
* **BM25** (:class:`BM25`, :func:`bm25_search`) — Okapi BM25 lexical scoring,
  which accounts for term saturation and document length far better than the
  old raw-count keyword score.
* **Hybrid fusion** (:func:`reciprocal_rank_fusion`) — Reciprocal Rank Fusion
  merges the vector ranking and the BM25 ranking by *rank*, so the two score
  scales never need to be reconciled.
* **Reranking** (:func:`tfidf_rerank`) — a cheap, local cross-encoder substitute:
  re-score the fused candidates by TF-IDF cosine against the query, no model
  download required.
* **Embedding cache** (:func:`content_hash`) — a stable per-(model, text) hash so
  unchanged chunks are never re-embedded.
* **Metadata filtering** (:func:`filter_chunks`) — narrow by folder, doc_type,
  tag, file extension, or modified-time window *before* the vector search runs.

Nothing here touches the network or the disk.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Final

# Rough token estimate shared with the embed pipeline (≈4 chars/token).
_CHARS_PER_TOKEN: Final = 4

_HEADING_RE: Final = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_PARA_SPLIT_RE: Final = re.compile(r"\n\s*\n")
_WORD_RE: Final = re.compile(r"\w+")


def approx_tokens(text: str) -> int:
    """Approximate token count of ``text`` (≈4 characters per token, min 1)."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


# ── Semantic chunking ─────────────────────────────────────────────────────────

def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split ``text`` into ``(heading, body)`` sections at markdown headings.

    Content before the first heading is returned with an empty heading. Each
    heading line itself is dropped from the body (it's carried in the tuple).
    """
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [("", text)]

    sections: list[tuple[str, str]] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.append(("", preamble))

    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        sections.append((heading, body))
    return sections


def _window_paragraph(paragraph: str, target_chars: int, overlap_chars: int) -> list[str]:
    """Hard-split a single oversized paragraph into overlapping char windows."""
    pieces: list[str] = []
    start = 0
    length = len(paragraph)
    while start < length:
        end = min(start + target_chars, length)
        piece = paragraph[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= length:
            break
        start = end - overlap_chars
    return pieces


def semantic_chunk(
    text: str,
    filename: str,
    vault_dir: str | Path,
    *,
    target_tokens: int = 500,
    overlap_tokens: int = 50,
    max_tokens: int = 800,
) -> list[dict[str, str]]:
    """Chunk ``text`` on heading/paragraph boundaries up to a token budget.

    Returns a list of ``{"file", "heading", "chunk_text"}`` dicts, where ``file``
    is ``filename`` made relative to ``vault_dir``. Paragraphs are packed whole
    into chunks of about ``target_tokens``; a paragraph larger than ``max_tokens``
    is windowed. Consecutive chunks within a section overlap by roughly
    ``overlap_tokens`` (a trailing paragraph is carried forward) to preserve
    context across the boundary.
    """
    try:
        rel = str(Path(filename).relative_to(vault_dir))
    except ValueError:
        rel = str(Path(filename).name)

    target_chars = target_tokens * _CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * _CHARS_PER_TOKEN
    max_chars = max_tokens * _CHARS_PER_TOKEN

    chunks: list[dict[str, str]] = []

    def emit(heading: str, body: str) -> None:
        body = body.strip()
        if body:
            chunks.append({"file": rel, "heading": heading, "chunk_text": body})

    for heading, body in _split_sections(text):
        if not body.strip():
            continue
        paragraphs = [p.strip() for p in _PARA_SPLIT_RE.split(body) if p.strip()]
        current = ""
        for para in paragraphs:
            if len(para) > max_chars:
                # Flush what we have, then window the oversized paragraph.
                if current:
                    emit(heading, current)
                    current = ""
                for piece in _window_paragraph(para, target_chars, overlap_chars):
                    emit(heading, piece)
                continue

            candidate = f"{current}\n\n{para}".strip() if current else para
            if current and len(candidate) > target_chars:
                emit(heading, current)
                # Carry a trailing overlap from the chunk we just flushed.
                tail = current[-overlap_chars:] if overlap_chars else ""
                current = f"{tail}\n\n{para}".strip() if tail else para
            else:
                current = candidate
        if current:
            emit(heading, current)

    return chunks


# ── BM25 lexical scoring ──────────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    """Lowercase word tokenisation used by BM25 and TF-IDF."""
    return _WORD_RE.findall(text.lower())


class BM25:
    """Okapi BM25 over a fixed corpus of pre-tokenised documents.

    ``k1`` controls term-frequency saturation and ``b`` the document-length
    normalisation — the standard defaults (1.5 / 0.75) work well for prose.
    """

    def __init__(
        self,
        corpus_tokens: Sequence[Sequence[str]],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.corpus_tokens = corpus_tokens
        self.doc_len = [len(doc) for doc in corpus_tokens]
        self.n_docs = len(corpus_tokens)
        self.avgdl = (sum(self.doc_len) / self.n_docs) if self.n_docs else 0.0

        # Document frequency per term, then the BM25 idf (with +1 smoothing so it
        # is always positive — avoids negative scores for very common terms).
        df: Counter[str] = Counter()
        for doc in corpus_tokens:
            df.update(set(doc))
        self.idf: dict[str, float] = {
            term: math.log(1 + (self.n_docs - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }
        self._tf: list[Counter[str]] = [Counter(doc) for doc in corpus_tokens]

    def scores(self, query_tokens: Sequence[str]) -> list[float]:
        """BM25 score of every corpus document against ``query_tokens``."""
        scores = [0.0] * self.n_docs
        if not self.avgdl:
            return scores
        for term in query_tokens:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, tf in enumerate(self._tf):
                freq = tf.get(term, 0)
                if not freq:
                    continue
                denom = freq + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl)
                scores[i] += idf * (freq * (self.k1 + 1)) / denom
        return scores


def _dense_cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two dense vectors (0.0 if either is zero-length)."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def vector_rank(
    query_vector: Sequence[float],
    candidates: Sequence[dict[str, Any]],
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """Rank ``candidates`` (each carrying an ``embedding``) by cosine to the query.

    The brute-force counterpart to the store's KNN index, used when a query
    pre-filters the candidate set (by date or file type) in a way the index can't
    express. Returns ``file``/``heading``/``text``/``score`` dicts, best first.
    """
    scored: list[dict[str, Any]] = []
    for c in candidates:
        emb = c.get("embedding")
        if not emb:
            continue
        scored.append({
            "file": c.get("file", ""),
            "heading": c.get("heading", ""),
            "text": c.get("chunk_text", c.get("text", "")),
            "score": _dense_cosine(query_vector, emb),
        })
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_k]


def bm25_search(
    query: str,
    chunks: Sequence[dict[str, Any]],
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """Rank ``chunks`` by BM25 against ``query``; scores normalised to 0–1.

    Mirrors the shape of the legacy keyword search: each result is a dict with
    ``file``, ``heading``, ``text``, and ``score``. Chunks scoring zero are
    dropped so callers only see genuine lexical matches.
    """
    query_tokens = tokenize(query)
    if not query_tokens or not chunks:
        return []

    corpus = [tokenize(c.get("chunk_text", c.get("text", ""))) for c in chunks]
    bm25 = BM25(corpus)
    raw = bm25.scores(query_tokens)

    scored = [
        {
            "file": c["file"],
            "heading": c.get("heading", ""),
            "text": c.get("chunk_text", c.get("text", "")),
            "score": s,
        }
        for c, s in zip(chunks, raw)
        if s > 0
    ]
    scored.sort(key=lambda r: r["score"], reverse=True)
    top = scored[:top_k]

    max_score = top[0]["score"] if top else 1.0
    for r in top:
        r["score"] = r["score"] / max_score if max_score else 0.0
    return top


# ── Hybrid fusion + reranking ─────────────────────────────────────────────────

def result_key(result: dict[str, Any]) -> str:
    """Stable identity for a retrieved chunk, used to align rankings."""
    text = result.get("text", result.get("chunk_text", ""))
    return f"{result.get('file', '')}::{result.get('heading', '')}::{text[:60]}"


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[dict[str, Any]]],
    *,
    k: int = 60,
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """Merge several ranked result lists by Reciprocal Rank Fusion.

    Each input list is assumed already sorted best-first. A chunk's fused score
    is ``Σ 1 / (k + rank)`` across the lists it appears in (rank is 0-based), so
    agreement between rankers is rewarded without having to reconcile their
    score scales. Returns the top ``top_k`` fused chunks, each carrying its
    ``score`` (the RRF score).
    """
    fused: dict[str, dict[str, Any]] = {}
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, result in enumerate(ranking):
            key = result_key(result)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in fused:
                fused[key] = {
                    "file": result.get("file", ""),
                    "heading": result.get("heading", ""),
                    "text": result.get("text", result.get("chunk_text", "")),
                    "score": 0.0,
                }
    for key, result in fused.items():
        result["score"] = scores[key]
    merged = sorted(fused.values(), key=lambda r: r["score"], reverse=True)
    return merged[:top_k]


def _tfidf_vector(tokens: Sequence[str], idf: dict[str, float]) -> dict[str, float]:
    tf = Counter(tokens)
    return {term: count * idf.get(term, 0.0) for term, count in tf.items()}


def _sparse_cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def tfidf_rerank(
    query: str,
    candidates: Sequence[dict[str, Any]],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Rerank ``candidates`` by TF-IDF cosine similarity to ``query``.

    A lightweight, fully-local stand-in for a cross-encoder: build a TF-IDF space
    over just the candidate set, then score each candidate's cosine against the
    query vector. Returns the top ``top_k`` with a ``rerank_score`` added and the
    list re-sorted by it. Ties (and the all-zero case) preserve the input order,
    so a reranker that finds no lexical signal never *worsens* fusion's ranking.
    """
    if not candidates:
        return []

    docs_tokens = [tokenize(c.get("text", c.get("chunk_text", ""))) for c in candidates]
    n = len(docs_tokens)
    df: Counter[str] = Counter()
    for tokens in docs_tokens:
        df.update(set(tokens))
    idf = {term: math.log(1 + n / (freq + 0.5)) for term, freq in df.items()}

    query_vec = _tfidf_vector(tokenize(query), idf)
    reranked: list[dict[str, Any]] = []
    for c, tokens in zip(candidates, docs_tokens):
        sim = _sparse_cosine(query_vec, _tfidf_vector(tokens, idf))
        reranked.append({**c, "rerank_score": sim})

    # Stable sort by rerank score (descending) keeps fusion order on ties.
    ordered = sorted(
        enumerate(reranked), key=lambda pair: (-pair[1]["rerank_score"], pair[0])
    )
    return [r for _, r in ordered][:top_k]


# ── Embedding cache ───────────────────────────────────────────────────────────

def content_hash(text: str, model: str = "") -> str:
    """Stable hash of ``text`` for an embedding cache, scoped to ``model``.

    Scoping by model means switching embedding models naturally misses the cache
    (the old vectors live in a different space) instead of returning stale,
    dimension-mismatched embeddings.
    """
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(text.encode("utf-8"))
    return h.hexdigest()


# ── Metadata filtering ────────────────────────────────────────────────────────

def filter_chunks(
    chunks: Iterable[dict[str, Any]],
    *,
    folders: Sequence[str] | None = None,
    doc_types: Sequence[str] | None = None,
    tags: Sequence[str] | None = None,
    file_types: Sequence[str] | None = None,
    since: float | None = None,
    until: float | None = None,
) -> list[dict[str, Any]]:
    """Filter chunks by metadata *before* the (more expensive) vector search.

    A criterion is ignored when ``None``. Within a criterion the match is "any
    of" (e.g. ``folders=["research", "wiki"]`` keeps chunks in either), and a
    chunk must satisfy *every* supplied criterion. ``since`` / ``until`` bound the
    chunk's ``modified_time`` (unix seconds); ``file_types`` match the file's
    extension with or without a leading dot (``"md"`` or ``".md"``).
    """
    folder_set = {f.lower() for f in folders} if folders else None
    doctype_set = {d.lower() for d in doc_types} if doc_types else None
    tag_set = {t.lower() for t in tags} if tags else None
    ext_set = {("." + e.lstrip(".")).lower() for e in file_types} if file_types else None

    out: list[dict[str, Any]] = []
    for c in chunks:
        if folder_set is not None and str(c.get("folder", "")).lower() not in folder_set:
            continue
        if doctype_set is not None and str(c.get("doc_type", "")).lower() not in doctype_set:
            continue
        if tag_set is not None:
            chunk_tags = {str(t).lower() for t in c.get("tags", [])}
            if not (chunk_tags & tag_set):
                continue
        if ext_set is not None and Path(str(c.get("file", ""))).suffix.lower() not in ext_set:
            continue
        if since is not None or until is not None:
            mtime = float(c.get("modified_time", 0) or 0)
            if since is not None and mtime < since:
                continue
            if until is not None and mtime > until:
                continue
        out.append(c)
    return out
