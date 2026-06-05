# Architecture

Atlas OS is a thin, local-first layer that turns Claude Cowork into a personal
operating system over a markdown knowledge vault. It is deliberately
file-based: the "database" is a folder of `.md` files, the "API" is a set of
small Python scripts fronted by the unified **`atlas` CLI** (`atlas_os/`), and
the "scheduler" is a set of skill prompts run on a cron-like schedule. Both you
and the scheduled skills drive everything through the one `atlas` command.

```
                        ┌──────────────────────────────┐
                        │        Claude Cowork           │
                        │  (skills, scheduled tasks,     │
                        │   memory, MCP tools)           │
                        │  conversations + research ─────┼──┐
                        └───────────────┬────────────────┘  │ atlas session save
                                        │ invokes            │ (transcripts → notes)
            ┌───────────────────────────┼───────────────────┼───────────┐
            ▼                           ▼                     ▼           ▼
   ┌─────────────────┐       ┌────────────────────┐       ┌──────────────────┐
   │  scripts/ (py)  │       │  Markdown Vault     │       │  Local LLM        │
   │  embed, graph,  │◀─────▶│  notes / wiki /     │       │  (embeddings +    │
   │  commit, email, │  rw   │  memory / daily /   │       │  chat, OpenAI-    │
   │  health, trade, │       │  sessions           │       │  compatible)      │
   │  session        │       │  (git-tracked)      │       └─────────┬────────┘
   └────────┬────────┘       └────────────────────┘                 │
            │                                                        │
            ▼                                                        │
   ┌─────────────────┐                                              │
   │  .rag/          │   vectors.db + graph.json    ◀───────────────┘
   │  vector store   │   (SQLite, local only, git-ignored)
   └─────────────────┘
```

Session capture closes the loop: conversations and research done in Cowork are
written back into the vault (`sessions/`), where the RAG pipeline indexes them
alongside your notes — so the system's knowledge grows with every chat.

## Components

### 0. The `atlas` CLI (`atlas_os/`)
The single entry point. A [Typer](https://typer.tiangolo.com/) app that
auto-loads `.env`, validates each command's required env vars up front, and
wraps the pipeline scripts (`atlas embed`, `graph`, `commit`, `changelog`,
`health`, `email`, `trading`, `schemas`) plus CLI-only commands (`init`,
`doctor`, `skills`). Installed via `pip install -e .` (or `uv tool install` /
`pipx`); `pyproject.toml` declares the `atlas` entry point and the optional
dependency groups (`[pdf]`, `[trading]`, `[all]`). The same scripts remain
runnable directly, so the CLI is a convenience layer, not a hard dependency.

### 1. Knowledge vault
A plain folder of markdown notes (works great with Obsidian, but not required).
Top-level folders carry meaning (`research`, `projects`, `decisions`, `memory`,
`wiki`, `daily`, …) and drive the frontmatter schemas. Git-tracked for history.

### 2. Session capture (`scripts/save_sessions.py`)
Folds Cowork chat transcripts back into the vault as `sessions/session-log-*.md`
notes — a summary, the key actions, and the files touched, all extracted
**locally with no LLM call**. A watermark (`.atlas/last_session_save.txt`) makes
runs incremental, and the twice-daily capture skills keep it current. Because the
notes land in the vault as ordinary markdown, the RAG pipeline (below) indexes
them automatically — this is what makes every conversation, and the research the
deep-research skills write into the vault, permanently searchable.

### 3. RAG pipeline (`scripts/embed_vault.py`, `rag_search.py`, `build_graph.py`, `atlas_os/vectordb.py`, `atlas_os/rag.py`)
**Semantically chunks** notes (split on heading/paragraph boundaries, ~500
tokens) via `atlas_os.rag`, embeds them via a **local** OpenAI-compatible
endpoint, and stores vectors in a **SQLite** database (`.rag/vectors.db`) through
`atlas_os.vectordb.VectorStore`. One row per chunk holds the text, metadata, and
packed `float32` embedding together, so embeds are incremental (insert/delete by
file) rather than a full-file rewrite, and a crash mid-run leaves every committed
batch intact. An **embedding cache** (keyed by `(model, text)` hash, surviving a
full rebuild) skips re-embedding unchanged chunks. Vector search uses the
[`sqlite-vec`](https://github.com/asg017/sqlite-vec) extension's k-nearest-neighbour
index when it's installed, and transparently falls back to a NumPy (or pure-Python)
cosine scan otherwise — same API, same scores, no hard dependency. Query time
(`atlas search`) is **hybrid**: the vector and **BM25** rankings are fused by
**Reciprocal Rank Fusion**, **reranked** by TF-IDF, and pre-filtered by metadata
(folder, doc_type, tag, file type, date). A legacy `vectors.json` is
auto-migrated to `vectors.db` on first embed (or ahead of time via
`atlas migrate-vectors`). `build_graph.py` derives a wikilink knowledge graph.
Both run incrementally (nightly) and fully (weekly), indexing your notes, captured
sessions, and research findings into one searchable corpus.

### 4. Frontmatter schemas (`schemas/enforce_schemas.py`)
Non-destructive enforcement of per-folder YAML frontmatter so notes stay
consistent. See [`../schemas/frontmatter-schemas.md`](../schemas/frontmatter-schemas.md).

### 5. Scheduled tasks (`skills/*`)
Each is a `SKILL.md` prompt run on a schedule by Claude Cowork: nightly index +
RAG embed, twice-daily session capture, daily reports, weekly health check and
full re-embed, etc. They orchestrate the scripts above and your connected MCP
tools. See [`SCHEDULED-TASKS.md`](SCHEDULED-TASKS.md).

### 6. Git automation (`scripts/vault_commit.py`, `vault_changelog.py`)
Auto-commits the vault with categorised messages and produces changelogs for the
morning briefing.

### 7. Email (`scripts/send_email.py`)
A credential-free SMTP sender (password from env) used by the report tasks.

### 8. Trading briefings (extension, optional)
A multi-agent market-research framework that writes briefings into the vault.
Entirely optional and **not financial advice**. As of v3.0 this is an
**extension** (`atlas_os/extensions/trading/`), not core — see *Extension
architecture* below — so `atlas trading` is contributed by the bundled trading
extension rather than the core CLI.

### 9. Web dashboard (`atlas_os/dashboard/`)
A lightweight, local-first **Flask web UI** (`atlas dashboard`) over everything
you already run from the CLI — seven panels: system health, audit trail,
scheduled tasks, skills, the **knowledge graph viewer**, vector-store stats, and
RAG search. It is split into a pure, Flask-free data layer
(`atlas_os/dashboard/data.py`, unit-tested directly, never raising for the
"not set up yet" states) and a thin Flask routing layer
(`atlas_os/dashboard/app.py`) over Jinja2 templates. It is a *view* — every
number is read live from the same modules the CLI uses (`vectordb`, `audit`,
`_skills`, `packs`, `doctor`), never a second source of truth. The interactive
**D3 graph viewer** lives at `/graph` (`GET /api/graph` scans the vault live) and
is openable with `atlas graph --open`. Shipped as the optional `[dashboard]`
extra (Flask + Jinja2). The original static, single-file
[`dashboard/`](../dashboard/) overview (backed by your own local JSON endpoints)
still ships for embedding in your own page.

### 10. Skills marketplace (`atlas_os/marketplace.py`)
Turns skills from *files in the repo* into something **shareable across installs**.
A JSON **registry** (`skills/registry.json` ships built-in; add more with
`atlas skills registry add`) lists skills with discovery metadata; `atlas skills
search` queries every configured registry, `atlas skills publish` validates a
skill folder against the schema and packages it to a `<name>-<version>.tar.gz`
with a generated `manifest.json`, and `SkillRegistry.resolve_dependencies`
computes the install order (dependencies first), detecting missing deps and
cycles. All pure data + small I/O helpers, so it's tested with no network.

### 11. Audit trail (`atlas_os/audit.py`)
An append-only JSONL log of every autonomous action (what ran, how it was
triggered, the outcome, duration, and what changed), written under an OS-level
file lock and auto-rotating at 10 MB. Queryable and exportable via `atlas audit
show / tail / export`.

### 12. Extension architecture (`atlas_os/extensions/`)
The line between the **lean core** (vault parsing, git sync, RAG, CLI, dashboard,
audit trail) and **domain modules** (trading, voice/TTS, the job tracker). The
core never imports a domain module directly; instead it discovers and loads them
at startup through one small contract, so the core stays decoupled and a domain
module can be added, removed, or shipped by a third party without touching it.

- **The contract** — [`extensions/base.py`](../atlas_os/extensions/base.py)
  defines `AtlasExtension`, an `ABC` whose only required surface is `name` and
  `description`. Four optional hooks let an extension plug in: `register_commands`
  (add subcommands to the `atlas` Typer app), `register_skills`,
  `register_schedules`, and the `on_load` / `on_unload` lifecycle. Every hook but
  the two identity properties has a no-op default.
- **Discovery + loading** — [`extensions/__init__.py`](../atlas_os/extensions/__init__.py)
  merges two channels: Python **entry points** under the `atlas_os.extensions`
  group (how third-party and installed extensions are found, declared in
  `pyproject.toml`) and a **built-in** registry of the vendored modules (so a
  bare source checkout discovers them without entry-point metadata). An entry
  point overrides a built-in of the same name, so a user can shadow a bundled
  extension. Loading is **fault-tolerant**: an extension whose import fails (a
  missing optional dependency, a broken third-party package) is skipped and its
  error recorded, never crashing the core CLI. `atlas extensions list` shows what
  was discovered and what failed; `atlas extensions info <name>` shows one
  extension's metadata, skills, and schedules.
- **The bundled extensions** — `trading` (market-research briefings, needs the
  `[trading]` extra), `voice` (TTS, stub), and `jobs` (application tracker, stub).
  Each declares its dependencies as an opt-in extra
  (`pip install 'atlas-os[trading]'`), so the core install stays slim and you
  only pull in what you use.

The CLI wires this up at the end of [`cli.py`](../atlas_os/cli.py): after every
core command is defined, `load_all_extensions(app)` registers each extension's
commands onto the app, so extension subcommands are present whenever `atlas` runs.

See [`features/extensions.md`](features/extensions.md) for the full guide,
including how to write your own.

## Design principles

- **Local-first.** Notes and embeddings never leave the machine by default.
- **Config via environment.** No paths, hosts, emails, or secrets in code.
- **Files over databases.** Everything is inspectable, diffable, and portable.
- **Idempotent automations.** Re-running a task converges rather than duplicates.
- **Non-destructive.** Scripts add/append; the hot cache is append-only.
- **Lean core, optional extensions.** Domain modules plug into the core through a
  contract; the core never depends on them, and they pull their own deps in as
  opt-in extras.

## Deployment

Atlas OS runs three ways, all from the same source: a **source checkout**
(`pip install -e .`), an **installed tool** (`uv tool install` / `pipx`, which
bundles the scripts/schemas/templates into the wheel — see
[`atlas_os/_paths.py`](../atlas_os/_paths.py)), or a **container**. The root
[`Dockerfile`](../Dockerfile) (Python 3.11-slim + git) packages the CLI and
[`docker-compose.yml`](../docker-compose.yml) bind-mounts your vault and loads
`.env` at runtime — no secrets or vault data are baked into the image. There is
no long-running service: it's a CLI, so containers run one subcommand and exit.
