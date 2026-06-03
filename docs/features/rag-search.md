# Feature: Local RAG Search

**Source:** [`scripts/embed_vault.py`](../../scripts/embed_vault.py),
[`atlas_os/rag.py`](../../atlas_os/rag.py),
[`scripts/rag_search.py`](../../scripts/rag_search.py) ·
**CLI:** `atlas embed`, `atlas search` ·
**Store:** `$RAG_DIR/vectors.db` (SQLite, via `atlas_os/vectordb.py`)

Atlas OS turns your markdown vault into a searchable knowledge base by
**semantically chunking** each note, embedding the chunks with a **local**
OpenAI-compatible model, and storing them in a **SQLite** vector store. Search is
**hybrid** — it fuses vector similarity with BM25 lexical scoring and reranks the
result. Nothing leaves your machine.

---

## How it works

### 1. File discovery

`os.walk` over `VAULT_PATH`, pruning `SKIP_DIRS = {.obsidian, .git, .rag,
.claude}`. It collects every `.md` file, and — if [`pdfplumber`](https://github.com/jsvine/pdfplumber)
is installed — every `.pdf` too. PDF text is extracted page-by-page; scanned or
empty PDFs (no extractable text) are skipped with a warning.

### 2. Semantic chunking

Documents are split by `atlas_os.rag.semantic_chunk()` on **structure**, not a
fixed character window:

- Split first on **markdown heading boundaries** (`#`–`######`), then on
  **paragraph breaks** within each section.
- Whole paragraphs are **packed** into chunks up to a **500-token** budget
  (`CHUNK_TOKENS`), with **50-token overlap** (`OVERLAP_TOKENS`) carried across
  the boundary; tokens are approximated as `len(text) // 4` characters. A
  paragraph larger than the hard cap is windowed as a fallback.
- Every chunk records its **nearest heading**, so results show which section
  they came from, and no chunk is ever cut mid-sentence.

### 3. Metadata

For each chunk, the pipeline attaches:

| Field | Source |
|---|---|
| `file` | path relative to the vault |
| `heading` | nearest preceding heading |
| `folder` | first-level folder (`""` for vault-root files) |
| `doc_type` | mapped from the folder via `DOC_TYPE_MAP` (e.g. `research`→`research`, `daily`→`daily`, PDFs→`pdf`, unknown→`misc`) |
| `tags` | parsed from the note's YAML frontmatter (`tags: [a, b]` **or** block list form) |
| `modified_time` | file mtime |

### 4. Embedding

`embed()` POSTs batches of chunk texts to `EMBED_URL`
(default `http://$EMBED_HOST:$EMBED_PORT/v1/embeddings`) with
`{"model": EMBED_MODEL, "input": [...]}`. Behaviour:

- **Batched** — `--batch-size` chunks per request (default **40**).
- **Resilient** — up to 5 attempts with exponential backoff; honours HTTP 429
  rate-limit responses; a 0.05s delay between calls.
- **Auth optional** — sends `Authorization: Bearer $EMBED_API_KEY` only if the
  key is set (local servers usually need none).
- **Cached** — every embedding is cached in `vectors.db` keyed by a
  `(model, text)` hash, so unchanged chunks are **never re-embedded** — even on a
  full rebuild (the cache survives `clear()`). Re-embedding an unchanged vault
  makes zero embedding calls.

Each embedded chunk becomes a row in the SQLite store, carrying the same fields:

```json
{
  "id": "research/note.md::12",
  "file": "research/note.md",
  "chunk_text": "…",
  "heading": "Background",
  "embedding": [0.0123, -0.045, …],
  "modified_time": 1717372800.0,
  "folder": "research",
  "doc_type": "research",
  "tags": ["ml", "rag"]
}
```

Rows are written **incrementally** into `vectors.db` (a `chunks` table holding the
text, metadata, and packed `float32` embedding) via `atlas_os.vectordb.VectorStore`.
Only the touched files' chunks are replaced, and each batch is committed as it
lands — so an interrupted embed resumes rather than leaving a half-written index.
Similarity search uses the `sqlite-vec` KNN index when the `[vector]` extra is
installed, falling back to a NumPy/pure-Python cosine scan otherwise.

### 5. Graph rebuild

After a `--full` or `--incremental` run (not `--test`/`--folder`/`--pdfs-only`),
the pipeline dynamically imports [`build_graph.py`](../../scripts/build_graph.py)
and rebuilds `graph.json`. See [knowledge-graph.md](knowledge-graph.md).

---

## Run modes

| Command | Behaviour |
|---|---|
| `atlas embed --full` | Re-embed **everything** from scratch, then rebuild the graph. |
| `atlas embed --incremental` | Embed only files with `mtime` newer than the last run (`last_embed.txt`); resumable via checkpoints. |
| `atlas embed --test N` | Embed the first `N` files only — a fast endpoint/connectivity check. Merges into the existing store. |
| `atlas embed --folder NAME` | Embed only files under top-level folder `NAME`. Merges into the existing store. |
| `atlas embed --pdfs-only` | Embed only PDF files (full pass over PDFs). |

Modifiers: `--checkpoint-interval N` (default 50), `--batch-size N` (default 40).

**Incremental merge semantics.** For incremental / test / folder / pdfs-only
runs, the pipeline loads the existing store, drops the vectors of files it's
about to re-embed (so they don't duplicate), embeds the touched files, and
writes the union. `--full` starts from an empty store.

### Checkpointing & resume

During an incremental run the pipeline writes `embed_checkpoint.json` every
`--checkpoint-interval` chunks (and saves the partial vector store). If the run
is interrupted, the next `--incremental` run reads the checkpoint, skips files
already completed, and resumes — so a large embed never has to start over. The
checkpoint is deleted on clean completion. `last_embed.txt` (with a
`last_embed_fallback.txt` backup) records the run timestamp that drives
incremental selection.

---

## Search (`atlas search`)

Query the store from the CLI via [`scripts/rag_search.py`](../../scripts/rag_search.py),
which runs the advanced pipeline in [`atlas_os/rag.py`](../../atlas_os/rag.py).
Three modes:

- **`vector`** — embed the query, rank by **cosine similarity** (the `sqlite-vec`
  KNN index, or a brute-force scan when unfiltered).
- **`keyword`** — **Okapi BM25** lexical scoring (term saturation + length
  normalisation). Needs no embeddings endpoint.
- **`hybrid`** (default) — fuse the vector and BM25 rankings with **Reciprocal
  Rank Fusion** (merge by *rank*, so the two score scales never need
  reconciling), then **rerank** the fused candidates by **TF-IDF cosine** to the
  query (a local, model-free cross-encoder substitute). `--no-rerank` returns the
  fusion order directly.

**Metadata filtering** (applied *before* ranking): `--folder`, `--doc-type`,
`--tag`, `--file-type` (all repeatable, "any of" within a criterion, AND across
criteria), plus a `--since` / `--until` modified-time window (`24h`/`7d`/`2w`/
`YYYY-MM-DD`).

```bash
atlas search "kelly criterion sizing"                       # hybrid + rerank
atlas search "trading risk" --folder research --tag trading --top-k 10
atlas search "embeddings" --mode vector --file-type md --since 30d
atlas search "decision log" --mode keyword --json           # offline, scriptable
```

Programmatically, `embed_vault.search(query, top_k, mode, filters, rerank)` is the
simple entry point and `embed_vault.advanced_search(...)` adds the rich date /
file-type filtering. The building blocks (`semantic_chunk`, `BM25`,
`reciprocal_rank_fusion`, `tfidf_rerank`, `filter_chunks`) live in
[`atlas_os/rag.py`](../../atlas_os/rag.py).

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `VAULT_PATH` | — (**required**) | vault to embed |
| `RAG_DIR` | `$VAULT_PATH/.rag` | where `vectors.db` etc. live |
| `EMBED_HOST` / `EMBED_PORT` | `localhost` / `5555` | embeddings endpoint |
| `EMBED_URL` | `…/v1/embeddings` | full override for non-standard paths |
| `EMBED_MODEL` | `text-embedding-nomic-embed-text-v1.5` | model name |
| `EMBED_API_KEY` | `""` | bearer token, if required |

Files written under `RAG_DIR`: `vectors.db`, `last_embed.txt`,
`last_embed_fallback.txt`, `embed_checkpoint.json`, and (via the graph step)
`graph.json`. **All are git-ignored** — derived data, reproducible from the
vault.

---

## Tuning & extending

- **Chunk size / overlap** — edit `CHUNK_TOKENS` / `OVERLAP_TOKENS` (passed to
  `semantic_chunk`).
- **Folder → doc_type** — edit `DOC_TYPE_MAP` to match your vault's folders.
- **Throughput** — raise `--batch-size` if your endpoint handles it; lower
  `INTER_CALL_DELAY` for local servers.
- **BM25 parameters** — tune `k1` / `b` in `atlas_os.rag.BM25`; adjust the RRF
  `k` or swap the reranker in `atlas_os.rag`.

## Troubleshooting

- *Embeddings unreachable* — `curl http://$EMBED_HOST:$EMBED_PORT/v1/models`;
  set `EMBED_URL` if the path differs.
- *PDFs skipped* — install `pdfplumber` (`atlas-os[pdf]`); scanned PDFs need OCR
  first.
- *Stale results* — run `atlas embed --incremental` (nightly task automates it).

See also: [knowledge-graph.md](knowledge-graph.md) ·
[knowledge-vault.md](knowledge-vault.md) ·
[`docs/SCRIPTS.md`](../SCRIPTS.md#embed_vaultpy)
