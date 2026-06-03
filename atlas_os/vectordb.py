"""A SQLite-backed vector store for the Atlas OS RAG pipeline.

The original RAG store was a single ``vectors.json`` file: every chunk, its
metadata, and its full embedding held in one JSON array, rewritten in full on
every embed. That is simple and dependency-free, but it does not scale —
the file is re-read and re-serialised wholesale, a crash mid-write can corrupt
it, and similarity search is a Python loop over every vector.

This module replaces that with a single SQLite database:

* **One row per chunk** in a ``chunks`` table — content, metadata, and the
  embedding (packed ``float32``) live together, so updates are incremental
  (insert/delete by file) instead of a full rewrite.
* **Vector search via `sqlite-vec`** when the extension is available: a ``vec0``
  virtual table does the k-nearest-neighbour scan in C. When the extension is
  *not* available (a Python built without ``enable_load_extension``, or
  ``sqlite-vec`` not installed) the store transparently falls back to a
  brute-force cosine scan — NumPy-accelerated if NumPy is present, otherwise
  pure Python. Either way the public API is identical.

The store is a drop-in replacement for the JSON helpers in ``embed_vault.py``:
:meth:`VectorStore.add_vectors` takes the same chunk dicts the pipeline already
produces, and :meth:`VectorStore.read_from_json` / :meth:`import_from_json`
migrate an existing ``vectors.json`` in place.

Nothing here touches the network and the schema is created on demand, so opening
a store against a fresh path just works.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
from array import array
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Final

# The metadata fields carried alongside every chunk. Kept in sync with the
# dicts produced by ``scripts/embed_vault.py`` so the store is a drop-in.
_META_FIELDS: Final = ("file", "chunk_text", "heading", "modified_time",
                        "folder", "doc_type", "tags")

# sqlite-vec partitions a vec0 table at a *fixed* dimension chosen at creation
# time. We learn the dimension from the first vector added and persist it in the
# meta table, so reopening the DB knows how to build the vec table.
_DIM_KEY: Final = "embedding_dim"


def _pack(vec: Sequence[float]) -> bytes:
    """Serialise a vector to little-endian ``float32`` bytes (sqlite-vec's format)."""
    return array("f", vec).tobytes()


def _unpack(blob: bytes) -> list[float]:
    """Inverse of :func:`_pack`."""
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


def _try_load_vec(conn: sqlite3.Connection) -> bool:
    """Best-effort load of the sqlite-vec extension. Returns whether it loaded.

    Two things can prevent it: the Python ``sqlite3`` module compiled without
    extension-loading support (``enable_load_extension`` missing or raising), or
    the ``sqlite_vec`` package not being installed. Setting
    ``ATLAS_VECTORDB_NO_VEC=1`` forces the brute-force backend regardless. Either
    way we degrade to the brute-force backend rather than failing.
    """
    if os.environ.get("ATLAS_VECTORDB_NO_VEC"):
        return False
    if not hasattr(conn, "enable_load_extension"):
        return False
    try:
        import sqlite_vec  # type: ignore[import-not-found]
    except ImportError:
        return False
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except (sqlite3.OperationalError, AttributeError):
        return False
    return True


class VectorStore:
    """A SQLite vector store: content, metadata, and embeddings in one DB.

    Open one with ``VectorStore(path)`` (an on-disk ``.db`` file, or
    ``":memory:"`` for tests). The schema is created lazily, the ``sqlite-vec``
    extension is loaded if available, and all of :meth:`add_vectors`,
    :meth:`search`, :meth:`delete_by_file`, :meth:`count`, and :meth:`clear`
    behave the same whether or not the extension is present.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self.vec_enabled = _try_load_vec(self._conn)
        self._dim: int | None = None
        self._init_schema()

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> VectorStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── schema ────────────────────────────────────────────────────────────────
    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                rowid         INTEGER PRIMARY KEY,
                id            TEXT UNIQUE,
                file          TEXT NOT NULL,
                chunk_text    TEXT NOT NULL,
                heading       TEXT DEFAULT '',
                embedding     BLOB NOT NULL,
                modified_time REAL DEFAULT 0,
                folder        TEXT DEFAULT '',
                doc_type      TEXT DEFAULT '',
                tags          TEXT DEFAULT '[]'
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file);
            CREATE INDEX IF NOT EXISTS idx_chunks_folder ON chunks(folder);
            CREATE INDEX IF NOT EXISTS idx_chunks_doctype ON chunks(doc_type);
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            -- Persistent embedding cache, keyed by a (model, text) content hash.
            -- Deliberately NOT wiped by clear(), so a full re-embed reuses the
            -- embeddings of unchanged content instead of re-calling the model.
            CREATE TABLE IF NOT EXISTS embedding_cache (
                content_hash TEXT PRIMARY KEY,
                embedding    BLOB NOT NULL
            );
            """
        )
        self._conn.commit()
        stored = self._get_meta(_DIM_KEY)
        if stored is not None:
            self._dim = int(stored)
            self._ensure_vec_table(self._dim)

    def _get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def _ensure_vec_table(self, dim: int) -> None:
        """Create the sqlite-vec virtual table at ``dim`` dimensions (idempotent)."""
        if not self.vec_enabled:
            return
        # distance_metric=cosine makes vec0's reported distance a true cosine
        # distance (1 − cosine similarity), so the KNN path and the brute-force
        # path produce identical scores.
        self._conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0("
            f"embedding float[{dim}] distance_metric=cosine)"
        )
        self._conn.commit()

    @property
    def _vec_ready(self) -> bool:
        """True once the sqlite-vec table actually exists (created on first add)."""
        return self.vec_enabled and self._dim is not None

    def _set_dim(self, dim: int) -> None:
        """Record the embedding dimension the first time we see a vector."""
        if self._dim is None:
            self._dim = dim
            self._set_meta(_DIM_KEY, str(dim))
            self._ensure_vec_table(dim)
            self._conn.commit()

    # ── writes ────────────────────────────────────────────────────────────────
    def add_vectors(self, entries: Iterable[dict[str, Any]]) -> int:
        """Insert chunk entries. Returns the number added.

        Each entry needs at least ``file``, ``chunk_text``, and ``embedding``;
        ``id``, ``heading``, ``modified_time``, ``folder``, ``doc_type``, and
        ``tags`` are optional. An entry whose ``id`` already exists is replaced,
        so re-embedding a file after :meth:`delete_by_file` never duplicates.
        """
        added = 0
        for entry in entries:
            embedding = entry.get("embedding")
            if not embedding:
                continue
            self._set_dim(len(embedding))
            file = entry["file"]
            entry_id = entry.get("id") or f"{file}::{added}"
            tags = entry.get("tags", [])
            tags_json = tags if isinstance(tags, str) else json.dumps(tags)
            blob = _pack(embedding)

            cur = self._conn.execute(
                "INSERT INTO chunks(id, file, chunk_text, heading, embedding, "
                "modified_time, folder, doc_type, tags) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "file=excluded.file, chunk_text=excluded.chunk_text, "
                "heading=excluded.heading, embedding=excluded.embedding, "
                "modified_time=excluded.modified_time, folder=excluded.folder, "
                "doc_type=excluded.doc_type, tags=excluded.tags",
                (
                    entry_id, file, entry["chunk_text"], entry.get("heading", ""),
                    blob, float(entry.get("modified_time", 0) or 0),
                    entry.get("folder", ""), entry.get("doc_type", ""), tags_json,
                ),
            )
            rowid = cur.lastrowid
            if self._vec_ready and rowid is not None:
                # Keep the vec index in lockstep with the canonical row.
                self._conn.execute("DELETE FROM vec_chunks WHERE rowid = ?", (rowid,))
                self._conn.execute(
                    "INSERT INTO vec_chunks(rowid, embedding) VALUES(?, ?)",
                    (rowid, blob),
                )
            added += 1
        self._conn.commit()
        return added

    def delete_by_file(self, file: str) -> int:
        """Delete every chunk belonging to ``file``. Returns the count removed."""
        rows = self._conn.execute(
            "SELECT rowid FROM chunks WHERE file = ?", (file,)
        ).fetchall()
        if not rows:
            return 0
        rowids = [r["rowid"] for r in rows]
        placeholders = ",".join("?" for _ in rowids)
        if self._vec_ready:
            self._conn.execute(
                f"DELETE FROM vec_chunks WHERE rowid IN ({placeholders})", rowids
            )
        self._conn.execute(
            f"DELETE FROM chunks WHERE rowid IN ({placeholders})", rowids
        )
        self._conn.commit()
        return len(rowids)

    def clear(self) -> None:
        """Remove every chunk (used by a ``--full`` re-embed)."""
        self._conn.execute("DELETE FROM chunks")
        if self._vec_ready:
            self._conn.execute("DELETE FROM vec_chunks")
        self._conn.commit()

    # ── reads ─────────────────────────────────────────────────────────────────
    def count(self) -> int:
        """Number of chunks in the store."""
        return int(self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])

    def files(self) -> set[str]:
        """The distinct file paths currently in the store."""
        return {r["file"] for r in self._conn.execute("SELECT DISTINCT file FROM chunks")}

    def _row_to_chunk(self, row: sqlite3.Row, *, with_embedding: bool) -> dict[str, Any]:
        chunk: dict[str, Any] = {
            "id":            row["id"],
            "file":          row["file"],
            "chunk_text":    row["chunk_text"],
            "heading":       row["heading"],
            "modified_time": row["modified_time"],
            "folder":        row["folder"],
            "doc_type":      row["doc_type"],
            "tags":          json.loads(row["tags"] or "[]"),
        }
        if with_embedding:
            chunk["embedding"] = _unpack(row["embedding"])
        return chunk

    def all_chunks(self, *, with_embedding: bool = False) -> list[dict[str, Any]]:
        """Every chunk as a dict. Embeddings are omitted unless asked for.

        Used by keyword / hybrid search, which only need the text and metadata.
        """
        rows = self._conn.execute("SELECT * FROM chunks").fetchall()
        return [self._row_to_chunk(r, with_embedding=with_embedding) for r in rows]

    def search(
        self,
        query_vector: Sequence[float],
        top_k: int = 5,
        filters: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the ``top_k`` chunks most similar to ``query_vector``.

        Each result is a dict with ``file``, ``heading``, ``text``, and a
        ``score`` in ``0.0–1.0`` (cosine similarity). When ``filters`` is given,
        only chunks whose folder, doc_type, or a tag matches *every* filter term
        are considered. Uses the sqlite-vec index when available and unfiltered;
        otherwise a brute-force cosine scan over the candidate rows.
        """
        if self.count() == 0:
            return []

        # sqlite-vec's KNN doesn't compose cleanly with arbitrary metadata
        # predicates, so the fast path is the unfiltered case. Filtered queries
        # take the brute-force route over the (already narrowed) candidate set.
        if self._vec_ready and not filters:
            return self._knn_search(query_vector, top_k)
        return self._brute_force_search(query_vector, top_k, filters)

    def _knn_search(self, query_vector: Sequence[float], top_k: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT c.file, c.heading, c.chunk_text, v.distance "
            "FROM vec_chunks v JOIN chunks c ON c.rowid = v.rowid "
            "WHERE v.embedding MATCH ? AND k = ? ORDER BY v.distance",
            (_pack(query_vector), top_k),
        ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            # The vec table uses distance_metric=cosine, so distance is
            # (1 − cosine similarity); invert it back to a similarity score.
            results.append({
                "file":    row["file"],
                "heading": row["heading"],
                "text":    row["chunk_text"],
                "score":   1.0 - float(row["distance"]),
            })
        return results

    def _brute_force_search(
        self,
        query_vector: Sequence[float],
        top_k: int,
        filters: list[str] | None,
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT file, heading, chunk_text, embedding, folder, doc_type, tags FROM chunks"
        ).fetchall()
        scored: list[dict[str, Any]] = []
        scorer = _make_scorer(query_vector)
        for row in rows:
            if filters and not _row_matches_filters(row, filters):
                continue
            scored.append({
                "file":    row["file"],
                "heading": row["heading"],
                "text":    row["chunk_text"],
                "score":   scorer(_unpack(row["embedding"])),
            })
        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:top_k]

    # ── embedding cache ───────────────────────────────────────────────────────
    def cached_embeddings(self, hashes: Sequence[str]) -> dict[str, list[float]]:
        """Return the cached embeddings for the given content hashes (cache hits)."""
        if not hashes:
            return {}
        placeholders = ",".join("?" for _ in hashes)
        rows = self._conn.execute(
            f"SELECT content_hash, embedding FROM embedding_cache "
            f"WHERE content_hash IN ({placeholders})",
            list(hashes),
        ).fetchall()
        return {r["content_hash"]: _unpack(r["embedding"]) for r in rows}

    def cache_embeddings(self, items: Iterable[tuple[str, Sequence[float]]]) -> int:
        """Store ``(content_hash, embedding)`` pairs in the persistent cache."""
        count = 0
        for content_hash, embedding in items:
            self._conn.execute(
                "INSERT INTO embedding_cache(content_hash, embedding) VALUES(?, ?) "
                "ON CONFLICT(content_hash) DO NOTHING",
                (content_hash, _pack(embedding)),
            )
            count += 1
        self._conn.commit()
        return count

    def cache_size(self) -> int:
        """Number of cached embeddings."""
        return int(self._conn.execute("SELECT COUNT(*) FROM embedding_cache").fetchone()[0])

    def clear_cache(self) -> None:
        """Empty the embedding cache (forces a clean re-embed of everything)."""
        self._conn.execute("DELETE FROM embedding_cache")
        self._conn.commit()

    # ── migration ─────────────────────────────────────────────────────────────
    @staticmethod
    def read_from_json(path: str | Path) -> list[dict[str, Any]]:
        """Load the legacy ``vectors.json`` array. Returns ``[]`` if absent/corrupt."""
        p = Path(path)
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return data if isinstance(data, list) else []

    def import_from_json(self, path: str | Path) -> int:
        """Import every entry from a legacy ``vectors.json`` into this store."""
        return self.add_vectors(self.read_from_json(path))


def _make_scorer(query_vector: Sequence[float]):
    """Return a function scoring a candidate vector against ``query_vector``.

    Uses NumPy for the dot/norm if it's importable (much faster over a large
    store), else a pure-Python cosine. Either way the result is plain cosine
    similarity, so the two paths are numerically interchangeable.
    """
    try:
        import numpy as np  # type: ignore[import-not-found]
    except ImportError:
        return lambda candidate: _cosine(query_vector, candidate)

    q = np.asarray(query_vector, dtype=np.float32)
    q_norm = float(np.linalg.norm(q))
    if q_norm == 0.0:
        return lambda candidate: 0.0

    def score(candidate: Sequence[float]) -> float:
        c = np.asarray(candidate, dtype=np.float32)
        c_norm = float(np.linalg.norm(c))
        if c_norm == 0.0:
            return 0.0
        return float(np.dot(q, c) / (q_norm * c_norm))

    return score


def _row_matches_filters(row: sqlite3.Row, filters: list[str]) -> bool:
    """True if ALL filter terms match the row's folder, doc_type, or tags."""
    folder = (row["folder"] or "").lower()
    doc_type = (row["doc_type"] or "").lower()
    try:
        tags = [t.lower() for t in json.loads(row["tags"] or "[]")]
    except (json.JSONDecodeError, TypeError):
        tags = []
    for term in filters:
        fl = term.lower()
        if fl not in (folder, doc_type) and fl not in tags:
            return False
    return True


# Default store filename inside the RAG dir.
DB_FILENAME: Final = "vectors.db"


def default_db_path(rag_dir: str | Path) -> Path:
    """The conventional vector-store path inside a RAG directory."""
    return Path(rag_dir) / DB_FILENAME


def open_store(
    rag_dir: str | Path,
    *,
    auto_migrate: bool = True,
) -> VectorStore:
    """Open (creating if needed) the vector store for a RAG directory.

    When ``auto_migrate`` is set and the SQLite DB does not yet exist but a
    legacy ``vectors.json`` does, its contents are imported on first open — so an
    existing install upgrades transparently the next time it embeds.
    """
    rag = Path(rag_dir)
    db_path = default_db_path(rag)
    legacy = rag / "vectors.json"
    needs_migration = auto_migrate and not db_path.exists() and legacy.exists()
    store = VectorStore(db_path)
    if needs_migration:
        store.import_from_json(legacy)
    return store
