#!/usr/bin/env python3
"""
RAG pipeline for an Obsidian (or any markdown) vault.

Embeds .md (and optionally .pdf) files via an OpenAI-compatible embeddings
endpoint and stores the vectors in a local JSON store. Designed for a
local-first setup (e.g. LM Studio, Ollama, or any server exposing
`/v1/embeddings`), so your notes never leave your machine.

Configuration is read entirely from environment variables — there are no
hardcoded paths, hosts, or credentials. See `.env.example`.

Environment variables:
    VAULT_PATH        Absolute path to the vault to embed (required)
    RAG_DIR           Where to write the vector store
                      (default: $VAULT_PATH/.rag)
    EMBED_HOST        Embeddings host        (default: localhost)
    EMBED_PORT        Embeddings port        (default: 5555)
    EMBED_MODEL       Model name             (default: text-embedding-nomic-embed-text-v1.5)
    EMBED_API_KEY     Bearer token, if any   (default: "")

Usage:
    python3 embed_vault.py --full          # re-embed everything
    python3 embed_vault.py --incremental   # only files modified since last run
    python3 embed_vault.py --test N        # embed first N files (smoke test)
    python3 embed_vault.py --folder NAME   # embed only files in a top-level folder
"""

import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from _bootstrap import ensure_atlas_os

ensure_atlas_os()
from atlas_os import netio, rag, vectordb  # noqa: E402
from atlas_os import retry as retrylib  # noqa: E402
from atlas_os import scriptkit  # noqa: E402

try:
    import pdfplumber  # type: ignore[import-untyped]
    _PDFPLUMBER_AVAILABLE = True
except ImportError:
    _PDFPLUMBER_AVAILABLE = False

# ── Config (all from environment) ───────────────────────────────────────────────
VAULT_DIR = Path(os.path.expanduser(os.environ.get("VAULT_PATH", "."))).resolve()
RAG_DIR = Path(os.path.expanduser(os.environ.get("RAG_DIR", str(VAULT_DIR / ".rag"))))
RAG_DIR.mkdir(parents=True, exist_ok=True)

VECTORS_FILE    = RAG_DIR / "vectors.json"          # legacy store (migration source)
VECTORS_DB      = vectordb.default_db_path(RAG_DIR)  # SQLite store (current)
LAST_EMBED      = RAG_DIR / "last_embed.txt"
CHECKPOINT_FILE = RAG_DIR / "embed_checkpoint.json"

API_KEY = os.environ.get("EMBED_API_KEY", "")


def _try_import_backends():
    """Import ``atlas_os.backends``, adding the repo root to sys.path if needed.

    This script runs standalone (``python3 embed_vault.py``), so the package
    isn't necessarily importable. Returns the module, or ``None`` if unavailable.
    """
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


def _resolve_embeddings() -> tuple[str, str]:
    """Resolve ``(embeddings_url, model)``.

    Explicit ``EMBED_*`` env vars always win, so existing setups are unaffected.
    Only when no embeddings endpoint is configured do we ask
    :mod:`atlas_os.backends` to auto-detect a running backend (LM Studio,
    Ollama, llama.cpp, …) — that's the one path that touches the network.
    """
    url = os.environ.get("EMBED_URL")
    model = os.environ.get("EMBED_MODEL")
    host = os.environ.get("EMBED_HOST")
    port = os.environ.get("EMBED_PORT")

    if not url and (host or port):
        url = f"http://{host or 'localhost'}:{port or '5555'}/v1/embeddings"

    if not url:
        backends = _try_import_backends()
        if backends is not None:
            try:
                client = backends.get_client()
                url = client.embeddings_url
                model = model or client.embed_model
            except backends.BackendError:
                pass

    return (
        url or "http://localhost:5555/v1/embeddings",
        model or "text-embedding-nomic-embed-text-v1.5",
    )


EMBED_URL, EMBED_MODEL = _resolve_embeddings()

SKIP_DIRS = {".obsidian", ".git", ".rag", ".claude"}

CHUNK_TOKENS     = 500   # target chunk size in (approximate) tokens
OVERLAP_TOKENS   = 50    # overlap between consecutive chunks
CHARS_PER_TOK    = 4     # rough approximation
INTER_CALL_DELAY = 0.05  # seconds between embedding calls

# Maps first-level folder name → doc_type. Adjust to match your own vault.
DOC_TYPE_MAP: dict[str, str] = {
    "research":         "research",
    "research-archive": "research",
    "code-solutions":   "code",
    "memory":           "memory",
    "memory-archive":   "memory",
    "system":           "system",
    "wiki":             "wiki",
    "daily":            "daily",
    "decisions":        "decision",
    "guides":           "guide",
    "projects":         "project",
    "learning":         "learning",
    "archive":          "archive",
    "templates":        "template",
    "inbox":            "inbox",
    "skills":           "skill",
}


# ── Text helpers ──────────────────────────────────────────────────────────────

def approx_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOK)


def extract_frontmatter_tags(text: str) -> list[str]:
    """Extract tags from YAML frontmatter, supporting inline [a, b] and block - item forms."""
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return []
    fm = fm_match.group(1)

    inline = re.search(r"^tags:\s*\[([^\]]*)\]", fm, re.MULTILINE)
    if inline:
        return [t.strip().strip("\"'") for t in inline.group(1).split(",") if t.strip()]

    block = re.search(r"^tags:\s*\n((?:[ \t]+-[^\n]*\n?)+)", fm, re.MULTILINE)
    if block:
        return [re.sub(r"^[ \t]+-\s*", "", line).strip()
                for line in block.group(1).splitlines() if line.strip()]
    return []


def get_folder(rel_path: str) -> str:
    """Return first-level folder name, or '' for vault-root files."""
    parts = Path(rel_path).parts
    return parts[0] if len(parts) > 1 else ""


def get_doc_type(folder: str) -> str:
    return DOC_TYPE_MAP.get(folder, "misc")


def chunk_text(text: str, filename: str) -> list[dict]:
    """Split text into semantic chunks, each carrying its nearest heading.

    Delegates to :func:`atlas_os.rag.semantic_chunk`, which splits on heading and
    paragraph boundaries and packs whole paragraphs up to the token budget
    instead of cutting at a fixed character offset. ``file`` is made relative to
    the vault root.
    """
    return rag.semantic_chunk(
        text, filename, VAULT_DIR,
        target_tokens=CHUNK_TOKENS, overlap_tokens=OVERLAP_TOKENS,
    )


# ── PDF extraction ────────────────────────────────────────────────────────────

def extract_pdf_text(filepath: Path) -> str:
    """Extract all text from a PDF. Returns '' for scanned/unreadable PDFs."""
    if not _PDFPLUMBER_AVAILABLE:
        raise RuntimeError("pdfplumber not installed")
    import logging
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    try:
        with pdfplumber.open(filepath) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n\n".join(pages)
    except Exception as e:
        print(f"  PDF extraction failed for {filepath.name}: {e}", file=sys.stderr)
        return ""


# ── Embedding ─────────────────────────────────────────────────────────────────

# Five tries with 1s → 16s exponential backoff. ``retry_on`` is every requests
# error so the ``should_retry`` predicate can make the per-status decision.
_EMBED_RETRY_POLICY = retrylib.RetryPolicy(
    attempts=5,
    base_delay=1.0,
    backoff=2.0,
    max_delay=30.0,
    retry_on=(requests.exceptions.RequestException,),
)


def _should_retry_embed(exc: BaseException) -> bool:
    """Retry connection/timeout errors and retryable HTTP statuses (429/5xx)."""
    if isinstance(exc, requests.exceptions.HTTPError):
        resp = getattr(exc, "response", None)
        return resp is not None and resp.status_code in netio.RETRY_STATUS_CODES
    return True  # connection reset, timeout, etc.


def embed(texts: list[str]) -> list[list[float]]:
    """Call the embeddings endpoint with timeouts + retries. Returns vectors.

    Raises :class:`atlas_os.netio.EndpointUnreachable` (connection failed) or
    :class:`atlas_os.netio.HTTPStatusError` (persistent bad status) with a clear,
    host-aware message instead of bubbling a raw ``requests`` traceback.
    """
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    payload = {"model": EMBED_MODEL, "input": texts}

    def _post() -> requests.Response:
        r = requests.post(EMBED_URL, headers=headers, json=payload, timeout=netio.DEFAULT_TIMEOUT)
        r.raise_for_status()
        return r

    def _on_retry(exc: BaseException, attempt: int, delay: float) -> None:
        print(
            f"  Embedding attempt {attempt} failed ({exc}); retrying in {delay:.0f}s…",
            file=sys.stderr,
        )

    try:
        r = retrylib.retry_call(
            _post,
            policy=_EMBED_RETRY_POLICY,
            should_retry=_should_retry_embed,
            on_retry=_on_retry,
        )
    except requests.exceptions.HTTPError as exc:
        resp = getattr(exc, "response", None)
        code = resp.status_code if resp is not None else 0
        raise netio.HTTPStatusError(
            f"Embeddings endpoint at {netio.endpoint_label(EMBED_URL)} returned HTTP "
            f"{code or '?'} after retries.",
            url=EMBED_URL,
            status_code=code,
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise netio.EndpointUnreachable(
            netio.unreachable_message(EMBED_URL, "Embeddings endpoint"), url=EMBED_URL
        ) from exc

    data = r.json()
    items = sorted(data["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in items]


# ── Vector store ──────────────────────────────────────────────────────────────
#
# Vectors live in a SQLite database (``vectors.db``) via :mod:`atlas_os.vectordb`,
# which scales past the old single-file ``vectors.json`` and supports incremental
# insert/delete. An existing ``vectors.json`` is auto-migrated the first time the
# DB is opened, so upgrades are transparent. The helpers below keep their old
# signatures (list-of-dicts in/out) so search and the tests are unaffected.

def open_store() -> vectordb.VectorStore:
    """Open the SQLite vector store, auto-migrating a legacy ``vectors.json``."""
    return vectordb.open_store(RAG_DIR)


def load_vectors() -> list[dict]:
    """Return every chunk (with its embedding) from the store, as plain dicts.

    Kept for the keyword/hybrid search paths and backward compatibility. A
    missing store simply yields an empty list — a full re-embed — rather than
    raising.
    """
    try:
        with open_store() as store:
            return store.all_chunks(with_embedding=True)
    except Exception:
        return []


def save_vectors(vectors: list[dict]) -> None:
    """Replace the store's contents with ``vectors`` (full rewrite).

    Incremental embeds add per-file rather than rewriting wholesale; this is the
    bulk path used by migration and tests.
    """
    with open_store() as store:
        store.clear()
        store.add_vectors(vectors)
    print(f"Saved {len(vectors)} vectors to {VECTORS_DB}")


# ── File discovery ────────────────────────────────────────────────────────────

def iter_md_files() -> list[Path]:
    files = []
    for root, dirs, filenames in os.walk(VAULT_DIR):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".md"):
                files.append(Path(root) / fn)
    return sorted(files)


def iter_pdf_files() -> list[Path]:
    files = []
    for root, dirs, filenames in os.walk(VAULT_DIR):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".pdf"):
                files.append(Path(root) / fn)
    return sorted(files)


LAST_EMBED_FALLBACK = RAG_DIR / "last_embed_fallback.txt"


def last_embed_time() -> float:
    if LAST_EMBED.exists():
        try:
            return float(LAST_EMBED.read_text().strip())
        except (ValueError, OSError):
            pass
    if LAST_EMBED_FALLBACK.exists():
        try:
            return float(LAST_EMBED_FALLBACK.read_text().strip())
        except (ValueError, OSError):
            pass
    return 0.0


def save_last_embed_time() -> None:
    ts = str(time.time())
    try:
        LAST_EMBED_FALLBACK.write_text(ts)
    except OSError:
        pass
    try:
        LAST_EMBED.write_text(ts)
    except OSError:
        pass


# ── Checkpoint ────────────────────────────────────────────────────────────────

def load_checkpoint() -> dict | None:
    if not CHECKPOINT_FILE.exists():
        return None
    try:
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def save_checkpoint(files_completed: set[str], chunks_embedded: int,
                    chunks_total: int, last_file: str) -> None:
    data = {
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "files_completed": sorted(files_completed),
        "chunks_embedded": chunks_embedded,
        "chunks_total":    chunks_total,
        "last_file":       last_file,
    }
    tmp = CHECKPOINT_FILE.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, CHECKPOINT_FILE)


def delete_checkpoint() -> None:
    if CHECKPOINT_FILE.exists():
        try:
            CHECKPOINT_FILE.unlink()
        except PermissionError:
            try:
                CHECKPOINT_FILE.chmod(0o644)
                CHECKPOINT_FILE.unlink()
            except Exception:
                try:
                    CHECKPOINT_FILE.write_text("")
                except Exception:
                    pass


# ── Search ────────────────────────────────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def keyword_search(query: str, chunks: list[dict], top_k: int = 20) -> list[dict]:
    """Score chunks by term frequency of query words, normalized to 0–1."""
    tokens = re.findall(r"\w+", query.lower())
    if not tokens:
        return []

    scored = []
    for v in chunks:
        text_lower = v["chunk_text"].lower()
        tf = sum(text_lower.count(t) for t in tokens)
        scored.append({
            "file":    v["file"],
            "heading": v.get("heading", ""),
            "text":    v["chunk_text"],
            "score":   float(tf),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:top_k]

    max_score = top[0]["score"] if top and top[0]["score"] > 0 else 1.0
    for r in top:
        r["score"] = r["score"] / max_score

    return top


def chunk_matches_filters(v: dict, filters: list[str]) -> bool:
    """Return True if ALL filter terms match the chunk's folder, doc_type, or tags."""
    folder   = v.get("folder", "")
    doc_type = v.get("doc_type", "")
    tags     = [t.lower() for t in v.get("tags", [])]
    for f in filters:
        fl = f.lower()
        if fl not in (folder.lower(), doc_type.lower()) and fl not in tags:
            return False
    return True


def search(query: str, top_k: int = 5, mode: str = "hybrid",
           filters: list[str] | None = None, rerank: bool = True) -> list[dict]:
    """Retrieve the ``top_k`` chunks for ``query``.

    Modes:

    * ``keyword`` — BM25 lexical scoring only (no embedding call).
    * ``vector`` — semantic similarity via the store's KNN index.
    * ``hybrid`` (default) — fuse the vector and BM25 rankings with Reciprocal
      Rank Fusion, then (optionally) rerank the fused candidates by TF-IDF cosine
      to the query.

    ``filters`` is a list of folder / doc_type / tag terms, all of which must
    match. See :func:`scripts.rag_search` for richer date / file-type filtering.
    """
    # Keyword mode is pure lexical scoring — no embedding call, no vector index.
    if mode == "keyword":
        vectors = load_vectors()
        if not vectors:
            print("No vectors found. Run embed_vault.py --full first.")
            return []
        if filters:
            vectors = [v for v in vectors if chunk_matches_filters(v, filters)]
            if not vectors:
                print(f"No chunks matched filters: {filters}")
                return []
        return rag.bm25_search(query, vectors, top_k=top_k)

    q_vec = embed([query])[0]
    store = open_store()
    try:
        if store.count() == 0:
            print("No vectors found. Run embed_vault.py --full first.")
            return []

        # Vector similarity is delegated to the store, which uses the sqlite-vec
        # KNN index when available and a cosine scan otherwise.
        top_vec = store.search(q_vec, top_k=max(top_k, 20), filters=filters)
        if filters and not top_vec:
            print(f"No chunks matched filters: {filters}")
            return []
        if mode == "vector":
            return top_vec[:top_k]

        # Hybrid: BM25 over the same (optionally filtered) candidate set.
        chunks = store.all_chunks()
        if filters:
            chunks = [c for c in chunks if chunk_matches_filters(c, filters)]
        top_kw = rag.bm25_search(query, chunks, top_k=max(top_k, 20))
    finally:
        store.close()

    # Fuse the two rankings by rank (RRF), then optionally rerank by TF-IDF.
    fused = rag.reciprocal_rank_fusion([top_vec, top_kw], top_k=max(top_k, 20))
    if rerank:
        return rag.tfidf_rerank(query, fused, top_k=top_k)
    return fused[:top_k]


def advanced_search(
    query: str,
    top_k: int = 5,
    mode: str = "hybrid",
    *,
    folders: list[str] | None = None,
    doc_types: list[str] | None = None,
    tags: list[str] | None = None,
    file_types: list[str] | None = None,
    since: float | None = None,
    until: float | None = None,
    rerank: bool = True,
) -> list[dict]:
    """Search with rich metadata pre-filtering, then hybrid retrieval + rerank.

    Unlike :func:`search`, this loads the candidate set and narrows it with
    :func:`atlas_os.rag.filter_chunks` (folder / doc_type / tag / file extension /
    modified-time window) *before* ranking — filters the vector index can't
    express. Ranking is the same hybrid pipeline: vector + BM25 fused by RRF, then
    an optional TF-IDF rerank. This backs the ``atlas search`` utility.
    """
    store = open_store()
    try:
        candidates = store.all_chunks(with_embedding=True)
    finally:
        store.close()
    if not candidates:
        print("No vectors found. Run embed_vault.py --full first.")
        return []

    candidates = rag.filter_chunks(
        candidates, folders=folders, doc_types=doc_types, tags=tags,
        file_types=file_types, since=since, until=until,
    )
    if not candidates:
        return []

    if mode == "keyword":
        return rag.bm25_search(query, candidates, top_k=top_k)

    q_vec = embed([query])[0]
    top_vec = rag.vector_rank(q_vec, candidates, top_k=max(top_k, 20))
    if mode == "vector":
        return top_vec[:top_k]

    top_kw = rag.bm25_search(query, candidates, top_k=max(top_k, 20))
    fused = rag.reciprocal_rank_fusion([top_vec, top_kw], top_k=max(top_k, 20))
    if rerank:
        return rag.tfidf_rerank(query, fused, top_k=top_k)
    return fused[:top_k]


# ── Main ──────────────────────────────────────────────────────────────────────

def run_embed(mode: str, test_limit: int = 0, folder_filter: str = "",
              pdfs_only: bool = False, checkpoint_interval: int = 50,
              batch_size: int = 40) -> None:
    if pdfs_only:
        all_files = iter_pdf_files()
        print(f"PDFs-only mode: found {len(all_files)} PDF files")
    else:
        all_files = iter_md_files() + iter_pdf_files()

    if mode == "incremental" and not pdfs_only:
        cutoff = last_embed_time()
        files = [f for f in all_files if f.stat().st_mtime > cutoff]
        print(f"Incremental mode: {len(files)}/{len(all_files)} files modified since last run")
    elif folder_filter:
        target = VAULT_DIR / folder_filter
        files = [f for f in all_files if f.is_relative_to(target)]
        print(f"Folder mode: {len(files)} files in {folder_filter!r} (merges into existing store)")
    elif not pdfs_only:
        files = all_files
        print(f"Full mode: embedding all {len(files)} files")
    else:
        files = all_files

    if test_limit > 0:
        files = files[:test_limit]
        print(f"Test mode: capped at {test_limit} files (merges into existing store)")

    checkpoint = None
    if mode == "incremental" and not pdfs_only and not test_limit:
        checkpoint = load_checkpoint()
        if checkpoint:
            already_done: set[str] = set(checkpoint["files_completed"])
            before = len(files)
            files = [f for f in files if str(f.relative_to(VAULT_DIR)) not in already_done]
            print(
                f"Resuming from checkpoint ({checkpoint['timestamp']}): "
                f"{checkpoint['chunks_embedded']} chunks previously done, "
                f"{len(already_done)} files skipped, {len(files)}/{before} remaining"
            )

    if not files:
        print("Nothing to embed.")
        return

    all_chunks: list[dict] = []
    pdf_found = 0
    pdf_extracted = 0
    for fp in files:
        try:
            is_pdf = fp.suffix.lower() == ".pdf"
            if is_pdf:
                pdf_found += 1
                text = extract_pdf_text(fp)
                if not text.strip():
                    print(f"  No text extracted from {fp.name} (scanned/empty?)", file=sys.stderr)
                    continue
                pdf_extracted += 1
            else:
                text = fp.read_text(encoding="utf-8", errors="replace")

            chunks = chunk_text(text, str(fp))
            mtime  = fp.stat().st_mtime
            rel    = str(fp.relative_to(VAULT_DIR))
            folder = get_folder(rel)
            tags   = [] if is_pdf else extract_frontmatter_tags(text)
            doc_type = "pdf" if is_pdf else get_doc_type(folder)
            for c in chunks:
                c["modified_time"] = mtime
                c["folder"]        = folder
                c["doc_type"]      = doc_type
                c["tags"]          = tags
            all_chunks.extend(chunks)
        except Exception as e:
            print(f"  Skipping {fp}: {e}", file=sys.stderr)

    if pdf_found > 0:
        print(f"PDFs: {pdf_extracted}/{pdf_found} had extractable text")

    total_chunks = len(all_chunks)
    print(f"Created {total_chunks} chunks from {len(files)} files")

    # Fail fast with a clear message if the embeddings server is down entirely,
    # rather than retrying every batch only to write an empty store.
    if total_chunks and not netio.is_reachable(EMBED_URL):
        raise netio.EndpointUnreachable(
            netio.unreachable_message(EMBED_URL, "Embeddings endpoint"), url=EMBED_URL
        )

    # Persist into the SQLite store. A partial embed (incremental/test/folder/
    # pdfs) deletes only the files it's about to re-embed and leaves the rest;
    # a full embed clears the store first. Either way, vectors are written per
    # batch, so the store is always a valid (if incomplete) index — no single
    # giant rewrite, and a crash mid-run keeps every batch already committed.
    store = open_store()
    touched_files = {str(f.relative_to(VAULT_DIR)) for f in files}
    is_partial = mode == "incremental" or test_limit > 0 or bool(folder_filter) or pdfs_only
    if is_partial:
        for touched in touched_files:
            store.delete_by_file(touched)
    else:
        store.clear()

    file_last_chunk_idx: dict[str, int] = {}
    for idx, c in enumerate(all_chunks):
        file_last_chunk_idx[c["file"]] = idx

    t0 = time.time()
    embedded = 0
    cache_hits = 0
    files_completed_this_run: set[str] = set()
    i = 0

    for batch_start in range(0, total_chunks, batch_size):
        batch = all_chunks[batch_start:batch_start + batch_size]
        batch_texts = [c["chunk_text"] for c in batch]
        batch_hashes = [rag.content_hash(t, EMBED_MODEL) for t in batch_texts]

        # Embedding cache: reuse vectors for chunks whose (model, text) we've
        # already embedded, and only call the endpoint for the misses.
        cached = store.cached_embeddings(batch_hashes)
        miss_idx = [j for j, h in enumerate(batch_hashes) if h not in cached]
        hits = len(batch) - len(miss_idx)

        print(
            f"Embedding {batch_start + 1}–{batch_start + len(batch)}/{total_chunks}: "
            f"{batch[0]['file']}" + (f" ({hits} cached)" if hits else "")
        )

        miss_vecs: list[list[float]] = []
        if miss_idx:
            try:
                miss_vecs = embed([batch_texts[j] for j in miss_idx])
            except Exception as e:
                print(f"  ERROR embedding batch {batch_start + 1}-{batch_start + len(batch)}: {e}",
                      file=sys.stderr)
                i += len(batch)
                continue
            store.cache_embeddings(
                (batch_hashes[j], vec) for j, vec in zip(miss_idx, miss_vecs)
            )

        # Reassemble vectors in batch order from cache hits + fresh misses.
        miss_iter = iter(miss_vecs)
        vecs = [
            cached[h] if h in cached else next(miss_iter)
            for h in batch_hashes
        ]
        cache_hits += hits

        batch_entries: list[dict] = []
        for chunk, vec in zip(batch, vecs):
            i += 1
            batch_entries.append({
                "id":            f"{chunk['file']}::{i}",
                "file":          chunk["file"],
                "chunk_text":    chunk["chunk_text"],
                "heading":       chunk["heading"],
                "embedding":     vec,
                "modified_time": chunk["modified_time"],
                "folder":        chunk["folder"],
                "doc_type":      chunk["doc_type"],
                "tags":          chunk["tags"],
            })
            if (i - 1) == file_last_chunk_idx[chunk["file"]]:
                files_completed_this_run.add(chunk["file"])

        store.add_vectors(batch_entries)
        embedded += len(batch_entries)

        if mode == "incremental" and i % checkpoint_interval == 0:
            save_checkpoint(files_completed_this_run, i, total_chunks, batch[-1]["file"])
            print(
                f"Checkpoint: {i}/{total_chunks} chunks embedded, "
                f"{len(files_completed_this_run)} files complete"
            )

        if INTER_CALL_DELAY:
            time.sleep(INTER_CALL_DELAY)

    elapsed = time.time() - t0
    total_vectors = store.count()
    store.close()
    print(f"Saved {embedded} new vectors to {VECTORS_DB}")

    if mode == "incremental":
        delete_checkpoint()

    if not test_limit:
        save_last_embed_time()

    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Files embedded : {len(files)}")
    print(f"  Chunks created : {total_chunks}")
    if cache_hits:
        print(f"  Cache hits     : {cache_hits} (skipped re-embedding)")
    print(f"  Total vectors  : {total_vectors}")

    if mode in ("full", "incremental") and not test_limit and not folder_filter and not pdfs_only:
        print("\nRebuilding knowledge graph…")
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "build_graph", Path(__file__).parent / "build_graph.py"
            )
            bg = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(bg)  # type: ignore[union-attr]
            graph, stats = bg.build_graph()
            bg.save_graph(graph)
            print(f"  Graph: {stats['total_nodes']} nodes, {stats['total_edges']} edges")
        except Exception as e:
            print(f"  Graph build failed: {e}", file=sys.stderr)


def main() -> None:
    args = sys.argv[1:]

    checkpoint_interval = 50
    if "--checkpoint-interval" in args:
        ci_idx = args.index("--checkpoint-interval")
        if ci_idx + 1 >= len(args):
            print("Usage: embed_vault.py --checkpoint-interval N")
            sys.exit(1)
        checkpoint_interval = int(args[ci_idx + 1])
        args = args[:ci_idx] + args[ci_idx + 2:]

    batch_size = 40
    if "--batch-size" in args:
        bs_idx = args.index("--batch-size")
        if bs_idx + 1 >= len(args):
            print("Usage: embed_vault.py --batch-size N")
            sys.exit(1)
        batch_size = int(args[bs_idx + 1])
        args = args[:bs_idx] + args[bs_idx + 2:]

    valid_flags = ("--full", "--incremental", "--test", "--folder", "--pdfs-only")
    if not args or args[0] not in valid_flags:
        print(
            "Usage: embed_vault.py "
            "[--full | --incremental | --test N | --folder NAME | --pdfs-only] "
            "[--checkpoint-interval N] [--batch-size N]"
        )
        sys.exit(1)

    mode          = args[0].lstrip("-")
    test_limit    = 0
    folder_filter = ""
    pdfs_only     = False

    if mode == "pdfs-only":
        pdfs_only = True
        mode = "full"
    elif mode == "test":
        if len(args) < 2:
            print("Usage: embed_vault.py --test N")
            sys.exit(1)
        test_limit = int(args[1])
        mode = "full"
    elif mode == "folder":
        if len(args) < 2:
            print("Usage: embed_vault.py --folder NAME")
            sys.exit(1)
        folder_filter = args[1]
        mode = "full"
    run_embed(mode, test_limit=test_limit, folder_filter=folder_filter,
              pdfs_only=pdfs_only, checkpoint_interval=checkpoint_interval,
              batch_size=batch_size)


if __name__ == "__main__":
    if not os.environ.get("VAULT_PATH"):
        scriptkit.fail(
            "VAULT_PATH environment variable is not set. See .env.example.",
            code=scriptkit.EXIT_CONFIG,
        )
    with scriptkit.error_boundary():
        main()
