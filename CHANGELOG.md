# Changelog

All notable changes to Eidetic OS are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Work toward **v4.0.0** — the rebrand-and-remember release. Tracked by the
**[v4.0.0 milestone](https://github.com/paulholland511/atlas-os/milestone/4)** and
issues [#22](https://github.com/paulholland511/atlas-os/issues/22)–[#27](https://github.com/paulholland511/atlas-os/issues/27).

### Added
- **Mem0-style fact-extraction engine** ([#22](https://github.com/paulholland511/atlas-os/issues/22)) —
  a new [`eidetic_os/facts.py`](eidetic_os/facts.py) module that distils discrete,
  atomic facts from conversations and **deduplicates them against existing
  memory**, replacing the append-whole-transcript approach that caused context
  bloat. Highlights:
  - `extract_facts(text, source)` extracts facts via the detected local LLM
    (LM Studio / Ollama / llama.cpp, through `eidetic_os.backends`) with a
    structured JSON prompt, and **falls back to a dependency-free heuristic
    extractor** — decision/preference/technical/project/person cues plus named
    entities — so extraction works fully offline.
  - `FactStore`, a SQLite-backed store (same approach as
    [`eidetic_os/vectordb.py`](eidetic_os/vectordb.py)) holding each fact with its
    source, timestamps, access count, confidence, category, embedding, and an
    `active` soft-delete flag.
  - **Deduplication** by cosine similarity (embeddings) or token overlap
    (offline): a near-identical fact **bumps** the existing one, a contradiction
    (opposite polarity) **supersedes** it (old soft-deleted, retained for
    history), and an overlapping fact is **merged** into the more informative
    statement.
  - `query_facts` / `get_facts_for_context` for semantic recall and context
    injection, and `decay_scores` applying half-life confidence decay since last
    access (the hook the sleeptime daemon, [#23](https://github.com/paulholland511/atlas-os/issues/23),
    and relevance scoring, [#27](https://github.com/paulholland511/atlas-os/issues/27), will drive).
  - New CLI command group: `eidetic facts extract <file>`, `eidetic facts list`,
    `eidetic facts search <query>`, and `eidetic facts stats`. The store lives at
    `$VAULT_PATH/.eidetic/facts.db` (override with `EIDETIC_FACTS_PATH`).
  - Full test coverage in [`tests/test_facts.py`](tests/test_facts.py) — CRUD,
    heuristic + LLM-parsing extraction, all four dedup paths, query/search,
    context selection, and decay.
- **Sleeptime memory consolidation daemon** ([#23](https://github.com/paulholland511/atlas-os/issues/23)) —
  a new [`eidetic_os/sleeptime.py`](eidetic_os/sleeptime.py) module that compresses
  recent session logs into a single synthesised note while you're offline,
  reducing the context bloat from dozens of near-duplicate session captures.
  Highlights:
  - `ConsolidationDaemon(vault_path, interval_hours=6)` with `run_once()` (a single
    scheduler-friendly pass) and `start()`/`stop()` for a lightweight interruptible
    background loop — no heavy frameworks, just a thread and an event.
  - Each pass scans `$VAULT_PATH/sessions/` for logs modified since the last run
    (watermark in `.eidetic/last_consolidation.txt`), distils each to its
    **decisions, actions, topics, files, and open questions**, merges them, and
    writes `$VAULT_PATH/wiki/consolidated/YYYY-MM-DD.md` with `type: consolidated`
    frontmatter that passes the automated-commit validation gate.
  - **Heuristic extraction by default** (regex for decision/action/file/heading/
    question cues) so consolidation runs fully offline; an LLM backend is used for
    a richer summary when reachable but is never required.
  - **Contradiction resolution** — when two sessions make conflicting choices for
    the same purpose, the most recent wins and the change is recorded in the note's
    *Contradictions Resolved* section.
  - **Optional fact integration** — when [`facts.py`](eidetic_os/facts.py) (#22) is
    present, each session's extracted facts are folded into a *Key Facts* section;
    the import degrades gracefully so the daemon works standalone.
  - Single-writer safety via the advisory `vault_lock` on `.eidetic/consolidation`;
    every pass is recorded in the audit trail.
  - New CLI command: `eidetic consolidate` (`--daemon`, `--status`, `--interval`,
    `--no-llm`, `--json`).
  - Full test coverage in [`tests/test_sleeptime.py`](tests/test_sleeptime.py) —
    noise stripping, all extractors, contradiction detection, watermark tracking,
    end-to-end passes, status, and the daemon lifecycle.
- **Native Obsidian plugin + API server** ([#24](https://github.com/paulholland511/atlas-os/issues/24)) —
  search memory, browse facts, and extract facts from a note **without leaving
  Obsidian**, backed by a small local REST server over the existing RAG/facts
  modules. Highlights:
  - New [`eidetic_os/plugin_server.py`](eidetic_os/plugin_server.py) — a minimal,
    CORS-enabled, **localhost-only** Flask app exposing `GET /api/health`,
    `GET /api/search` (hybrid/vector/keyword, reusing the dashboard's search
    layer), `GET /api/facts` and `GET /api/facts/search`, `GET /api/stats`
    (vault/vector/fact counts + last-embed time), and `POST /api/facts/extract`
    (preview or store, deduplicated). It is a *view* over the same modules the CLI
    and dashboard use — never a second source of truth.
  - New CLI command: `eidetic serve` (`--host`, `--port`, `--debug`) — starts the
    plugin API (default `http://localhost:8501`); needs the `dashboard` extra.
  - New [`obsidian-plugin/`](obsidian-plugin/) — a TypeScript Obsidian plugin
    (manifest, esbuild config, styles) adding four command-palette actions
    (**Search memory**, **Show facts**, **Extract facts from note**,
    **System stats**), a brain ribbon icon, a connection/fact-count status bar, and
    a settings tab for the server URL. Ships as source with a build config; not
    compiled in CI.
  - Full test coverage in [`tests/test_plugin_server.py`](tests/test_plugin_server.py) —
    every endpoint's JSON shape, offline keyword search, fact listing/filtering/
    search, extraction (preview + store), stats (with and without an index), and
    the CORS headers.

### Changed
- **Rebranded from Atlas OS to Eidetic OS.** The project's first three major
  versions shipped as *Atlas OS*; the name collided with [AtlasOS](https://atlasos.net/)
  (the Windows debloater, 20.8K+ stars) and Fluidstack's bare-metal "Atlas OS",
  and it didn't communicate the core value. *Eidetic* means **total, photographic
  recall** — the promise that your AI never forgets. This is a **breaking** change:
  - Python distribution renamed `atlas-os` → **`eidetic-os`** (`pip install eidetic-os`).
  - Import path renamed `atlas_os` → **`eidetic_os`** (and the bundled data dir
    `atlas_os_data` → `eidetic_os_data`).
  - CLI command renamed `atlas` → **`eidetic`** (e.g. `eidetic init`, `eidetic search`).
  - Environment variables renamed `ATLAS_*` → **`EIDETIC_*`** (`EIDETIC_LLM_BACKEND`,
    `EIDETIC_SKILLS_DIR`, `EIDETIC_AUDIT_PATH`, `EIDETIC_TRIGGER`, …).
  - Vault state directory renamed `.atlas/` → **`.eidetic/`** (audit log, session
    watermark).
  - Public extension base class renamed `AtlasExtension` → **`EideticExtension`**;
    entry-point group `atlas_os.extensions` → **`eidetic_os.extensions`**.
  - MCP skill server names renamed `atlas-skill[s]` → **`eidetic-skill[s]`**.
  - The GitHub repository URL stays `paulholland511/atlas-os` for now (the repo is
    renamed separately); all docs and metadata reference the new name. See
    [`docs/MIGRATION.md`](docs/MIGRATION.md) for the upgrade path.
- **Documentation overhaul** — competitive README rewrite (name rationale,
  feature highlights, architecture diagram, comparison table vs. Letta / Mem0 /
  Khoj / gAIOS) and a published **v4.0 roadmap**.

### Roadmap (v4.0.0)
- Mem0-style fact extraction with dedup against existing memory ([#22](https://github.com/paulholland511/atlas-os/issues/22)).
- Sleeptime memory-consolidation daemon ([#23](https://github.com/paulholland511/atlas-os/issues/23)).
- Interactive setup wizard 2.0 — model detection, endpoint mapping, style profiling ([#25](https://github.com/paulholland511/atlas-os/issues/25)).
- Channel adapters for Slack / Telegram ([#26](https://github.com/paulholland511/atlas-os/issues/26)).
- Memory decay & time-weighted relevance scoring ([#27](https://github.com/paulholland511/atlas-os/issues/27)).

## [3.0.0] — 2026-06-05

The **[v3.0.0 milestone](https://github.com/paulholland511/atlas-os/milestone/3)**
is an architecture-led release — Eidetic OS refactored from a monolithic toolkit
into a lean, extensible, MCP-native, hardened platform. Tracked by issues
[#15](https://github.com/paulholland511/atlas-os/issues/15)–[#19](https://github.com/paulholland511/atlas-os/issues/19).

### Added
- **Extension architecture** ([#15](https://github.com/paulholland511/atlas-os/issues/15)).
  The lean core (vault parsing, git sync, RAG indexer, CLI, dashboard, audit
  trail) is decoupled from the domain verticals. `trading/`, `voice_automation/`,
  and `job_search/` move into `extensions/` as opt-in extras
  (`pip install 'eidetic-os[trading]'`), discovered via setuptools entry points
  with a documented `register_commands()` / `register_skills()` /
  `register_schedules()` API. `pip install eidetic-os` installs core only.
- **MCP skills** ([#16](https://github.com/paulholland511/atlas-os/issues/16)).
  The skill framework speaks the **Model Context Protocol**: the `eidetic_os`
  runtime is an MCP client, each skill an MCP server with schema-validated tool
  definitions (stdio for local skills, SSE/HTTP for remote). Existing `SKILL.md`
  skills are auto-wrapped in an MCP shim, so skills are consumable from Claude
  Code, Cowork, and any third-party MCP host.
- **Security hardening** ([#17](https://github.com/paulholland511/atlas-os/issues/17)).
  Code validation and sandboxing for community skills: AST static analysis at
  `eidetic skills install` with BLOCK / WARN / INFO severities (BLOCK is not
  `--force`-overridable), a restricted runtime sandbox (timeout, memory limit,
  no network by default), and audit-trail logging of every install and run,
  surfaced via `eidetic security report`.
- **Git sync hardening** ([#18](https://github.com/paulholland511/atlas-os/issues/18)).
  Conflict resolution and data integrity so automated git never corrupts the
  vault: `git_sync.safe_sync` uses a favour-local merge that never overwrites a
  concurrent human edit and aborts true conflicts (tree untouched) rather than
  force-resolving; `frontmatter.validate_before_commit` gates commits on valid
  YAML and required keys; `filelock` adds advisory, stale-self-healing per-file
  locks; and crash-orphaned `.git/*.lock` files are cleared. Surfaced via
  `eidetic sync`, `eidetic validate`, and a Sync category in `eidetic doctor`.
- **Scalable vector storage — pluggable backends** ([#19](https://github.com/paulholland511/atlas-os/issues/19)).
  A small `VectorBackend` interface (`insert` / `search` / `delete_by_file` /
  `count` / `files` / `clear` / `export_chunks`) now sits in front of the RAG
  store (`eidetic_os/vector_backend.py`, `eidetic_os/vector_backends/`). **SQLite**
  stays the zero-config default; opt-in **LanceDB** (`eidetic-os[lancedb]` —
  columnar, on-disk, zero-copy scans) and **ChromaDB** (`eidetic-os[chroma]`)
  backends are selectable via `VECTOR_BACKEND`. `eidetic migrate-vectors --to
  <backend>` copies an existing store into another engine with progress and a
  verified count match; `eidetic doctor` reports the active backend. See
  [`docs/features/vector-backends.md`](docs/features/vector-backends.md).

### Fixed
- **Vector-index integrity on re-embed** (`eidetic_os/vectordb.py`). On an
  upsert that *updates* an existing chunk id, the `sqlite-vec` index was synced
  against a stale `lastrowid` (SQLite refreshes it only on INSERT, not the
  `ON CONFLICT DO UPDATE` path), which could overwrite an unrelated row's vector
  and surface the wrong chunk in KNN results. The rowid is now resolved by id.

## [2.0.0] — 2026-06-04

The **[v2.0.0 milestone](https://github.com/paulholland511/atlas-os/milestone/2)**
release — Eidetic OS goes from a CLI-and-scripts toolkit to a complete platform.
It completes every milestone issue ([#10](https://github.com/paulholland511/atlas-os/issues/10)–[#14](https://github.com/paulholland511/atlas-os/issues/14)):
the **SQLite vector store** ([#10](https://github.com/paulholland511/atlas-os/issues/10))
and the **advanced RAG pipeline** ([#11](https://github.com/paulholland511/atlas-os/issues/11))
graduated to shipped in [1.2.0](#120--2026-06-04); this release adds the
**open-source web dashboard** ([#12](https://github.com/paulholland511/atlas-os/issues/12)),
the **skills marketplace** ([#13](https://github.com/paulholland511/atlas-os/issues/13)),
and the **visual knowledge graph viewer** ([#14](https://github.com/paulholland511/atlas-os/issues/14)),
then polishes the dashboard UI and ships a set of terminal demo GIFs. No breaking
changes — the v1.0 stability contract (command names, flags, env vars, exit codes,
documented JSON shapes) is unchanged; the major bump marks the platform milestone.

### Added
- **Visual knowledge graph viewer** ([#14](https://github.com/paulholland511/atlas-os/issues/14)).
  A D3.js force-directed view of how vault notes connect via `[[wikilinks]]`,
  served by the dashboard and openable straight from the CLI:
  - **`/graph` page** — a new template,
    [`eidetic_os/dashboard/templates/graph.html`](eidetic_os/dashboard/templates/graph.html),
    a self-contained viewer (inline CSS/JS, D3 from a CDN). Nodes are **coloured
    by type** (session log, source, skill, research, wiki, memory, note), with
    zoom/pan, dragging, a name search, per-type filter chips, and a click-through
    panel showing each note's outbound links and backlinks. It degrades to a
    friendly empty state when there's nothing to graph, and self-heals its layout
    via a `ResizeObserver` so the force diagram stays centred.
  - **`GET /api/graph`** — a new `data.graph_data()` helper scans the vault live
    (mirroring `build_graph.py`) and returns nodes (with `type`, `degree`, in/out
    counts), `{source, target}` edges, a colour legend, and summary stats. It
    never raises for the "no vault / no notes" cases, and caps huge vaults to the
    most-connected nodes. Added to the dashboard's **Knowledge** nav group.
  - **`eidetic graph --open`** — (re)builds the graph and launches the dashboard at
    `/graph` in your browser. New flags `--host` / `--port` / `--no-build` /
    `--json`; the serving logic is shared with `eidetic dashboard` via a new
    `_serve_dashboard()` helper.
  - Tests: [`tests/test_graph.py`](tests/test_graph.py) covers node classification,
    wikilink resolution (aliases, headings, nested paths), edge dedup, orphans,
    the node cap, and both routes.
- **Skills marketplace / community registry** ([#13](https://github.com/paulholland511/atlas-os/issues/13)).
  A new module, [`eidetic_os/marketplace.py`](eidetic_os/marketplace.py), turns skills
  from files in this repo into something shareable across installs:
  - **Registries** — a JSON document (`registry.json`) listing skills with
    metadata (name, version, description, author, tags, dependencies, download
    URL). The built-in registry ([`skills/registry.json`](skills/registry.json))
    ships with every install and is always searched.
  - **`eidetic skills search [QUERY]`** — search every configured registry by
    keyword or tag (matches name, description, and tags), de-duplicated by name;
    an unreachable registry is reported and skipped, never aborting the search.
  - **`eidetic skills publish PATH`** — validate a skill folder against the schema
    (required fields, valid slug/semver, well-formed tags & dependencies) and
    package it into a `<name>-<version>.tar.gz` with a generated `manifest.json`.
  - **`eidetic skills registry add URL` / `list`** — register and list custom
    registries (a URL or a local path) alongside the built-in one; config lives
    in `$VAULT_PATH/.eidetic/registries.json` (override with `EIDETIC_REGISTRIES_PATH`).
  - **Dependency resolution** — a skill may declare `dependencies` on other
    skills; `SkillRegistry.resolve_dependencies` returns the install order
    (dependencies first) and detects missing dependencies and cycles.
  - As with packs, every built-in registry entry must resolve to a real skill
    under `skills/` — `marketplace.validate_builtin_registry()` enforces this and
    the test-suite asserts it. New tests in
    [`tests/test_marketplace.py`](tests/test_marketplace.py); docs in
    [`docs/features/skills-marketplace.md`](docs/features/skills-marketplace.md).
- **Open-source web dashboard** ([#12](https://github.com/paulholland511/atlas-os/issues/12)).
  A lightweight, local-first web UI over everything you already run from the
  command line, in a new package, [`eidetic_os/dashboard/`](eidetic_os/dashboard/):
  - **`eidetic dashboard`** — serves the app at `http://127.0.0.1:8501`
    (`--host` / `--port` / `--open`/`--no-open` / `--debug`) and opens a browser.
    It's an **optional extra** (`pip install 'eidetic-os[dashboard]'`, Flask + Jinja2
    only) — if the extra isn't installed the command prints a one-line install hint
    instead of a traceback.
  - **Seven panels**, each read live from the same modules the CLI uses (never a
    second source of truth): **system health** (the `eidetic doctor` report with
    green/amber/red indicators), a paginated **audit trail** browser, **scheduled
    tasks** with last-run status, a **skills** manager with one-click pack installs,
    the interactive **knowledge graph** (above), **vector-store stats** (chunks,
    files, cache, DB size, backend, last embed), and **RAG search** (the same
    engine as `eidetic search`).
  - **Two layers, deliberately separated:**
    [`eidetic_os/dashboard/data.py`](eidetic_os/dashboard/data.py) is pure, Flask-free
    data-shaping that never raises for the "not set up yet" states (rendered as
    amber panels), and [`eidetic_os/dashboard/app.py`](eidetic_os/dashboard/app.py) is
    a thin Flask routing layer over Jinja2 templates and one hand-written
    stylesheet. RAG search shells out to `scripts/rag_search.py --json`, so a
    missing endpoint can never take the page down. New `flask` extra in
    [`pyproject.toml`](pyproject.toml); docs in
    [`docs/features/dashboard.md`](docs/features/dashboard.md).
- **Polished dashboard UI — the *UI UX Pro Max* design system.** The dashboard was
  redesigned into a cohesive, detail-dense interface: a refined dark theme, a
  consistent icon set ([`templates/_icons.html`](eidetic_os/dashboard/templates/_icons.html)),
  a **Knowledge** navigation group, and layouts tuned for scanning at a glance —
  applied across every panel without adding a build step or a client-side
  framework.
- **New terminal demo GIFs.** A set of recorded walkthroughs surfaced in the
  README — [`install.gif`](install.gif) and [`setup.gif`](setup.gif) (Quick start),
  [`dashboard.gif`](dashboard.gif) / [`dashboard-screenshot.png`](dashboard-screenshot.png)
  (the web dashboard), and [`search.gif`](search.gif) (RAG search) — generated by a
  new helper, [`scripts/make_doc_gifs.py`](scripts/make_doc_gifs.py).

## [1.2.0] — 2026-06-04

This release graduates two **[v2.0.0 milestone](https://github.com/paulholland511/atlas-os/milestone/2)**
features to shipped — the SQLite vector store ([#10](https://github.com/paulholland511/atlas-os/issues/10))
and the advanced RAG pipeline ([#11](https://github.com/paulholland511/atlas-os/issues/11)) — and
moves session capture to a twice-daily default.

### Changed
- **Session capture is now twice-daily by default (morning + afternoon).** Two
  new scheduled skills, **`morning-session-capture`** (~09:00) and
  **`afternoon-session-capture`** (~17:00–18:00), each run
  `EIDETIC_TRIGGER=scheduled eidetic session save --since 12h`. They cover a 12-hour
  window apiece so work lands in the vault closer to when it happened, and the
  shared watermark in `.eidetic/last_session_save.txt` means the overlapping
  windows never double-write a session. The **`knowledge`** pack now installs
  both in place of the single daily skill.
- The original **`daily-session-capture`** skill is retained for users who prefer
  a single nightly `--since 24h` run; its SKILL.md now points to the twice-daily
  pair as the recommended default.

### Added
- **Advanced RAG pipeline — semantic chunking, hybrid search, reranking,
  embedding cache.** A new module, [`eidetic_os/rag.py`](eidetic_os/rag.py), upgrades
  every stage of retrieval, and the `eidetic search` command exposes it:
  - **Semantic chunking** splits on heading and paragraph boundaries and packs
    whole paragraphs up to a token budget (oversized paragraphs are windowed),
    instead of cutting at a fixed character offset mid-sentence.
  - **Hybrid search** fuses a vector ranking and an **Okapi BM25** lexical
    ranking with **Reciprocal Rank Fusion** — no score-scale reconciliation
    needed — replacing the old weighted term-frequency blend.
  - **Reranking** re-scores the fused candidates by **TF-IDF cosine** to the
    query (a local, model-free cross-encoder substitute); never worsens fusion's
    order when it finds no lexical signal.
  - **Embedding cache** keyed by a `(model, text)` content hash means unchanged
    chunks are never re-embedded — even across a full rebuild (the cache survives
    `clear()`). Re-embedding an unchanged vault makes zero embedding calls.
  - **Metadata filtering** narrows candidates by folder, doc_type, tag, file
    extension, or a modified-time window *before* the vector search.
  - **`eidetic search`** (wraps [`scripts/rag_search.py`](scripts/rag_search.py)):
    `eidetic search "query" --mode hybrid|vector|keyword --folder … --tag …
    --file-type md --since 30d --top-k N [--no-rerank] [--json]`. See
    [`docs/CLI-REFERENCE.md`](docs/CLI-REFERENCE.md#eidetic-search).
- **SQLite vector store — production-scale RAG (replaces `vectors.json`).** The
  RAG index now lives in a single SQLite database (`$RAG_DIR/vectors.db`) via the
  new [`eidetic_os/vectordb.py`](eidetic_os/vectordb.py) `VectorStore`, instead of one
  monolithic `vectors.json` rewritten in full on every embed. Vector search runs
  through the [`sqlite-vec`](https://github.com/asg017/sqlite-vec) KNN index (with
  a NumPy-accelerated brute-force cosine fallback when the extension isn't
  installed), embeds are **incremental** (insert/delete by file, no whole-store
  rewrite), a crash mid-run leaves every committed batch intact, and metadata
  filtering (folder / doc_type / tags) is a first-class query option.
  - **Transparent migration.** An existing `vectors.json` is imported
    automatically the first time the store is opened, so upgrading is a no-op.
  - **`eidetic migrate-vectors`** converts an existing `vectors.json` → `vectors.db`
    ahead of time (or re-imports with `--force`). See
    [`docs/CLI-REFERENCE.md`](docs/CLI-REFERENCE.md#eidetic-migrate-vectors).
  - **`[vector]` optional dependency** (`pip install -e ".[vector]"`) pulls in
    `sqlite-vec` + `numpy`; both are optional — the store falls back gracefully.
  - **`EIDETIC_VECTORDB_NO_VEC=1`** forces the brute-force backend (for testing, or
    opting out of the native extension).
- **`SESSION_CAPTURE_FREQUENCY` configuration.** A scheduling hint documenting
  your intended session-capture cadence — `twice` (default), `daily`, `hourly`,
  or `manual`. Documented in [`.env.example`](.env.example),
  [`docs/CLI-REFERENCE.md`](docs/CLI-REFERENCE.md), and
  [`docs/SCHEDULED-TASKS.md`](docs/SCHEDULED-TASKS.md).

## [1.1.0] — 2026-06-03

### Added
- **Daily session capture — save your Cowork chats to the vault.** A new
  command, **`eidetic session`**, folds Claude Cowork chat transcripts back into
  your knowledge base as searchable markdown. It reads Cowork's local session
  store (metadata + the standard Claude Code JSONL transcripts) and, for every
  session in the requested window, writes
  `$VAULT_PATH/sessions/session-log-YYYY-MM-DD-<title>.md` with
  `[session-log, cowork]` frontmatter, a `session_id`, an extracted summary, the
  key actions taken, and the files modified — all derived **deterministically**
  from the local transcript (no LLM call, no network).
  - **`eidetic session save`** captures everything new or changed since the last
    run (tracked by a watermark in `.eidetic/last_session_save.txt`, so re-running
    is idempotent and notes are overwritten in place). `--since 24h` / `--since
    7d` / `--since 2026-06-01` scope a window; `--all` captures every session.
  - **`eidetic session list`** shows recent sessions with their dates and titles
    (read-only, no `VAULT_PATH` required).
  - Backed by a new standalone script,
    [`scripts/save_sessions.py`](scripts/save_sessions.py), wired through the
    audit trail like every other action. The session store location is
    configurable via `CLAUDE_SESSIONS_DIR` (defaults to the macOS Cowork path),
    so it runs on any platform and is fully testable; missing/empty stores and
    malformed transcript lines are handled gracefully.
- **New scheduled skill — `daily-session-capture`.** Runs nightly via
  `EIDETIC_TRIGGER=scheduled eidetic session save --since 24h` so the day's Cowork
  work lands in the vault as part of the unattended audit trail. Added to the
  **`knowledge`** pack alongside the nightly index and RAG embed, and documented
  in [`docs/CLI-REFERENCE.md`](docs/CLI-REFERENCE.md) and
  [`docs/TUTORIAL.md`](docs/TUTORIAL.md) (Hour 3 — "Going Autonomous").

## [1.0.0] — 2026-06-03

### Added
- **Migration guide — v0.3.0 → v1.0.** A new
  [`docs/MIGRATION.md`](docs/MIGRATION.md) walks existing installs through the
  upgrade. The headline: **v1.0 is fully backward compatible** — no breaking
  changes, no env-var renames, no config edits. The recommended upgrade is
  `pip install --upgrade eidetic-os && eidetic doctor --fix && eidetic embed
  --incremental`. The guide also catalogues everything additive in v1.0 (the
  interactive `eidetic init` wizard, the diagnosing/fixing `eidetic doctor`, skill
  packs, pluggable LLM backends, the audit trail, hardened scripts), the new
  CLI flags (`doctor --fix`/`--json`, `skills packs`/`install-pack`), the new
  internal modules, the new optional environment variables, and how to roll
  back. Linked from [`README.md`](README.md) and [`docs/README.md`](docs/README.md).
- **Pre-built skill packs — install a whole workflow in one command.** A new
  registry, [`eidetic_os/packs.py`](eidetic_os/packs.py), bundles related skills into
  curated **packs** so you can stand up a complete workflow at once instead of
  installing skills one by one. Three packs ship:
  - **`knowledge`** (5 skills) — vault management: nightly commit & index,
    incremental + full RAG re-embedding, lint reports, and the weekly digest.
  - **`communication`** (3 skills) — email & reporting: the daily report email,
    inbox-triage digest, and vault report docs.
  - **`trading`** (2 skills) — trading intelligence: the daily trading report and
    on-demand topic research briefs.

  Two new subcommands back this: **`eidetic skills packs`** lists the packs with
  their members and counts, and **`eidetic skills install-pack <name>`** installs
  every skill in a pack (same `{{PLACEHOLDER}}` substitution as `install`),
  skipping already-installed members unless `--force` is passed. Every slug a
  pack names is validated against `skills/` (`packs.validate_packs()`, asserted
  in the test-suite) so a typo fails CI, not at install time. Documented in
  [`docs/CLI-REFERENCE.md`](docs/CLI-REFERENCE.md) and
  [`docs/SKILLS-FRAMEWORK.md`](docs/SKILLS-FRAMEWORK.md).
- **`eidetic doctor` — from reporting to diagnosing and fixing.** The doctor no
  longer just lists OK / WARN / FAIL; it now groups checks by category
  (**Config / Git / LLM / RAG / SMTP**), colour-codes each row, and prints an
  actionable **next step** for everything that isn't OK. New checks:
  - **Git state** — detects stale `index.lock` / `HEAD.lock` / ref locks left by
    an interrupted git process (new `gitutil.find_stale_locks`), and flags a
    vault that isn't a git repo.
  - **LLM backends** — probes the active (or `EIDETIC_LLM_BACKEND`-forced) backend
    and, when it's down, shows a clear diagnosis (*"LM Studio at host:port is not
    responding. Is it running?"*) plus any reachable backends as alternatives.
  - **RAG freshness** — warns when the index is older than 24h (or never built)
    and suggests `eidetic embed --incremental`.
  - **iCloud offload** — detects the recurring dataless / cloud-offloaded file
    problem on `vectors.json` and `last_embed.txt`.
  - **Config & SMTP** — offers to run `eidetic init` for a missing `VAULT_PATH`,
    and explains how to configure email (linking the tutorial) when SMTP is unset.

  Two new flags back this up: **`--fix`** auto-applies *safe* remediations
  (clearing stale git locks) while still prompting for *unsafe* ones (running the
  init wizard, creating the vault's first commit), and **`--json`** emits the
  whole report as `{checks, summary}` for programmatic use (part of the v1.0
  stability contract). Documented in
  [`docs/CLI-REFERENCE.md`](docs/CLI-REFERENCE.md).
- **CLI reference & v1.0 stability contract.** A new
  [`docs/CLI-REFERENCE.md`](docs/CLI-REFERENCE.md) documents the complete `eidetic`
  CLI — generated from the live `--help` output and the underlying scripts, so it
  reflects exactly what exists. It covers global flags, a commands table, a
  detailed per-command reference (description, usage, flags, env vars read, exit
  codes, examples), a full environment-variable table (purpose + default), and
  the `0` / `1` / `2` / `130` exit-code meanings. It doubles as a **stability
  contract**: command names, flags, env vars, exit codes, and documented JSON
  output shapes are stable as of v1.0, and a breaking change to any of them
  requires a major version bump. Linked from the root [`README.md`](README.md)
  and the docs [index](docs/README.md).
- **Tutorial: *Your first 24 hours with Eidetic OS*.** A new end-to-end guide,
  [`docs/TUTORIAL.md`](docs/TUTORIAL.md), walks a brand-new user from
  `pip install eidetic-os` to a fully autonomous system — structured as a timeline
  (Hour 0 install & init → Hour 1 first vault & commit → Hour 2 RAG vectors &
  knowledge graph → Hour 3 skills & scheduled tasks → Hour 4 email reports →
  Hours 5–24 going autonomous). Every command is copy-pasteable with a "what you
  should see" check, and it assumes no prior knowledge of Obsidian, RAG, or
  embeddings. Linked from the root [`README.md`](README.md) and the docs
  [index](docs/README.md).
- **Production hardening for the pipeline scripts.** Every script under
  [`scripts/`](scripts) now degrades gracefully instead of dumping a traceback,
  backed by five new reusable modules:
  - [`eidetic_os/retry.py`](eidetic_os/retry.py) — a `RetryPolicy` plus a `retry`
    decorator and `retry_call` helper for exponential-backoff retries with an
    injectable `sleep` (so tests stay instant);
  - [`eidetic_os/netio.py`](eidetic_os/netio.py) — HTTP with explicit `(10s, 30s)`
    connect/read timeouts, retries on transient failures and `429/5xx`, and clear
    *"X at host:port is not responding"* errors (`EndpointUnreachable` /
    `HTTPStatusError`) rather than raw `requests` tracebacks;
  - [`eidetic_os/fileio.py`](eidetic_os/fileio.py) — atomic writes
    (write-temp → `fsync` → `os.replace`) for critical files like `vectors.json`
    and `graph.json`, plus reads that turn missing / permission-denied /
    iCloud-offloaded (`EDEADLK`, dataless stub) / corrupt-JSON cases into typed
    errors or a caller-supplied default;
  - [`eidetic_os/gitutil.py`](eidetic_os/gitutil.py) — stale lock cleanup
    (`index.lock`, `HEAD.lock`, ref locks) and `worktree prune` before writes,
    repo detection, and timeout-guarded command running (`GitError`);
  - [`eidetic_os/scriptkit.py`](eidetic_os/scriptkit.py) — consistent exit codes
    (`0` success, `1` error, `2` config), `--json` structured error output, and
    an `error_boundary` context manager that converts any exception into a
    one-line message — no script ever shows a user a Python traceback.

  Wired through: `embed_vault` (retrying timeout-bounded embeddings + atomic
  vector store + fail-fast on a down endpoint), `trading_briefing` (clear
  endpoint errors, `--json`, atomic briefing write), `send_email` (SMTP timeout
  and backoff retries on transient failures), `vault_commit` /
  `vault_changelog` (lock cleanup, not-a-repo detection, clean git errors),
  `build_graph` (atomic graph write), and `health_check` (HEAD/ref lock
  detection, traceback-free). New unit suites cover every module
  ([`test_retry`](tests/test_retry.py), [`test_netio`](tests/test_netio.py),
  [`test_fileio`](tests/test_fileio.py), [`test_gitutil`](tests/test_gitutil.py),
  [`test_scriptkit`](tests/test_scriptkit.py)).
- **End-to-end integration test suite.** A new
  [`tests/test_integration.py`](tests/test_integration.py) drives the real
  `eidetic` CLI through Typer's `CliRunner` and exercises the pipelines as a user
  would — no mocked internals. Commands that wrap a script genuinely shell out to
  a subprocess; only the truly external dependencies (the LLM endpoint and SMTP)
  are stubbed, and those with **real local sockets** (a background
  OpenAI-compatible HTTP server, a refused SMTP port) so the child processes see
  them. The ten scenarios cover the full surface: `init → doctor`, the embed
  pipeline writing `vectors.json`, the git `commit` cycle, `changelog`
  generation, `skills list → install` with placeholder substitution, the audit
  trail round-trip, `health --json` structure, multi-backend detection, email
  graceful-failure paths, and a `init → embed → commit → changelog → audit` full
  lifecycle. New shared fixtures in [`tests/conftest.py`](tests/conftest.py)
  (`sample_vault`, `git_vault`, `llm_server`) build throwaway vaults and mock
  endpoints. Tests are marked `@pytest.mark.integration` so they can be run or
  skipped on their own (`pytest -m integration` / `pytest -m "not integration"`).
- **Interactive `eidetic init` wizard.** First-run onboarding is now a guided,
  colourful wizard rather than hand-editing `.env`. It opens with a short
  explanation of what Eidetic OS is, then: (1) suggests a **smart vault default**
  — an existing `~/Documents/Obsidian/*` folder, `~/vault`, or the current
  directory if it looks like a vault; (2) **auto-detects a local LLM** by probing
  LM Studio (`:5555`), Ollama (`:11434`), and llama.cpp (`:8080`), wiring the
  first match's host/port and embedding model into the config; (3) optionally
  collects **SMTP** settings for email reports; (4) **generates `.env`** from the
  answers; (5) **scaffolds the vault tree** (`.eidetic/`, `.rag/`, `wiki/`) plus
  the index files and skills catalog, and git-inits the vault; (6) runs
  **`eidetic doctor`** automatically and prints a "you're ready" summary with next
  steps. `--yes` accepts every default for a fully non-interactive run (fresh
  machines, scripts, containers), `--vault PATH` sets the vault explicitly, and
  `--force` overwrites an existing `.env`. The `doctor` checks were extracted
  into a reusable `_doctor_results()` so the wizard and the standalone command
  share one source of truth. Endpoint probing
  ([`eidetic_os/_probe.py`](eidetic_os/_probe.py)) was realigned to the documented
  default ports and now de-duplicates a server that answers on more than one API
  path. Covered by new tests in
  [`tests/test_cli.py`](tests/test_cli.py); the
  [Quick Start](docs/QUICKSTART.md) leads with the wizard.
- **Automated PyPI publishing via GitHub Actions + Trusted Publishing.** Pushing
  a `v*` tag (e.g. `v0.4.0`) now builds, tests, and publishes the release to
  PyPI with no stored token — authentication is
  [OIDC Trusted Publishing](https://docs.pypi.org/trusted-publishers/).
  [`.github/workflows/publish.yml`](.github/workflows/publish.yml) runs
  `test → build → publish`: lint + `pytest`, then `python -m build` +
  `twine check`, then `pypa/gh-action-pypi-publish` against the `pypi`
  environment with `id-token: write`. A companion
  [`.github/workflows/test-publish.yml`](.github/workflows/test-publish.yml)
  routes pre-release tags (`v*rc*`, `v*dev*`) to TestPyPI for dress rehearsals.
  [`docs/PUBLISHING.md`](docs/PUBLISHING.md) documents the flow and the one-time
  PyPI trusted-publisher setup (pending-publisher or manual-first-upload).
- **`eidetic skills install <name>`** — one-command skill deployment. Copies a
  skill's `SKILL.md` into your scheduled-tasks directory (`$EIDETIC_SKILLS_DIR`,
  default `$VAULT_PATH/.claude/skills/<name>/`) and substitutes its
  `{{PLACEHOLDER}}` tokens from the environment / `.env`. Most tokens map to the
  env var of the same name (`{{VAULT_PATH}}` ← `VAULT_PATH`); `{{EIDETIC_OS}}`
  resolves to the repo path and `{{LLM_PORT}}` reads `LM_STUDIO_PORT`. Tokens
  with no value are left in place and reported so you can fill them by hand;
  `--force` overwrites an existing install. Two companion subcommands:
  `eidetic skills list` (every available skill) and `eidetic skills show <name>`
  (print a skill's `SKILL.md`). The placeholder logic and install live in
  [`eidetic_os/_skills.py`](eidetic_os/_skills.py), covered by
  [`tests/test_skills.py`](tests/test_skills.py).
- **PyPI release preparation.** The package is now publish-ready: the version is
  single-sourced from `__version__` in
  [`eidetic_os/__init__.py`](eidetic_os/__init__.py) via `[tool.hatch.version]`
  (bump it in one place), the sdist explicitly bundles `scripts/`, `schemas/`,
  `templates/`, `skills/`, and `docs/` (`[tool.hatch.build.targets.sdist]`), and
  the metadata gained AI/indexing topic classifiers. A new
  [`docs/PUBLISHING.md`](docs/PUBLISHING.md) is the maintainer runbook (bump →
  `python -m build` → `twine check` → TestPyPI → `twine upload` → tag). No
  release is published yet — everything is staged so `pipx install eidetic-os`
  works the moment it is.
- **Pluggable LLM backends** ([`eidetic_os/backends.py`](eidetic_os/backends.py)).
  Eidetic OS now auto-detects any OpenAI-compatible LLM server, probing **LM Studio
  (`:5555`) → Ollama (`:11434`) → llama.cpp (`:8080`) → a custom
  `OPENAI_COMPATIBLE_URL`** in that order and using the first that responds. The
  module exposes `detect_backend()`, `get_client()`, `list_models()`, and a
  one-shot `run_inference()` test. Two env vars override the defaults:
  `EIDETIC_LLM_BACKEND` forces a backend (`lmstudio`/`ollama`/`llamacpp`/
  `openai-compatible`, skipping detection) and `EIDETIC_LLM_MODEL` overrides the
  chat model name. New CLI: `eidetic backends` lists every backend with
  reachability + models, and `eidetic backends test` runs an end-to-end inference.
  The RAG (`embed_vault.py`), trading (`trading_briefing.py`), and health
  (`health_check.py`) scripts now resolve their endpoint through this module.
  **Fully backward compatible:** explicit `EMBED_*` / `LM_STUDIO_*` settings still
  win, so existing setups are unchanged. Covered by
  [`tests/test_backends.py`](tests/test_backends.py).
- **Skills catalogue & framework docs.** A
  [`docs/SKILLS-CATALOGUE.md`](docs/SKILLS-CATALOGUE.md) documenting the full menu
  of **160+ skills** — 149 capability skills across seven domains (Security,
  DevOps, Frontend, Backend, Quality, Data & AI, Business), each with a one-line
  summary, what it does, and when to use it, plus the four Eidetic-native skills
  (`autoresearch`, `save-to-vault`, `wiki-search`, `send-email`) and the nine
  scheduled automations. A companion
  [`docs/SKILLS-FRAMEWORK.md`](docs/SKILLS-FRAMEWORK.md) explains what a skill is,
  the anatomy of a `SKILL.md`, the placeholder-token system, the lifecycle
  (creation → installation → scheduling → execution → audit logging), how the
  RAG-indexed catalog reaches sub-agents, the `skill-creator` meta-skill, and a
  copy-paste `SKILL.md` template. Everything is generic and `{{PLACEHOLDER}}`-
  tokenised — no personal data.
- **Six example skills** ([`skills/`](skills)) demonstrating the framework across
  document creation (`generate-vault-report-doc`), email automation
  (`inbox-triage-digest`), data analysis (`spreadsheet-analysis`), web research
  (`topic-research-brief`), vault management (`vault-lint-report`), and report
  generation (`weekly-digest-report`) — bringing the shipped skill count to 15.
- **Audit trail** ([`eidetic_os/audit.py`](eidetic_os/audit.py)). An append-only
  JSONL log of every autonomous action, written to `$EIDETIC_AUDIT_PATH` (default
  `$VAULT_PATH/.eidetic/audit.jsonl`). Each entry records the timestamp, action,
  trigger (`scheduled`/`manual`/`cli`), status, duration, what changed, why it
  ran, and any error. Appends are serialised with an in-process lock plus an
  OS-level advisory file lock (safe across concurrent `eidetic` processes) and the
  file auto-rotates at 10 MB to `audit.jsonl.1`, `.2`, …. Every script-wrapping
  command (`embed`, `commit`, `graph`, `changelog`, `health`, `trading`,
  `email`) now logs its outcome automatically; scheduled tasks tag their runs by
  setting `EIDETIC_TRIGGER=scheduled`. New `eidetic audit` subcommands: `show`
  (`--limit`/`--action`/`--since`), `tail` (last 5, compact), and `export`
  (`--format csv|json`, `--output`) for compliance reporting. Strengthens ISO
  27001 control A.12.4 (logging & monitoring). Covered by
  [`tests/test_audit.py`](tests/test_audit.py).
- **GitHub issue & PR templates**
  ([`.github/ISSUE_TEMPLATE/`](.github/ISSUE_TEMPLATE/),
  [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md)) — a
  structured bug report (with an environment block: OS, Python, Eidetic OS
  version, install method), a feature request (use case / proposed solution /
  alternatives), and a PR checklist (tests, docs, the PII scan). An
  `ISSUE_TEMPLATE/config.yml` disables blank issues and routes security reports
  to `SECURITY.md` and questions to the FAQ.
- **README status badges** — GitHub Actions CI status, GitHub stars, and
  last-commit, alongside the existing license / Python / privacy / docs badges.
- **`eidetic trading`** — wraps `scripts/trading_briefing.py` (`--ticker`,
  `--date`, `--dry-run`); the last optional pipeline script to gain a first-class
  subcommand, so the whole system is now reachable through one `eidetic` command.
- **Up-front env validation.** Every vault/optional command checks its required
  environment variables before shelling out and exits with a clear message and a
  non-zero code if any are missing — a half-configured feature fails fast instead
  of part-way through.
- **`eidetic email` flags.** Send mail with `--to` / `--subject` / `--body`
  (`--text` for plain text, repeatable `--attach`), or the original raw payload
  via `--json`.
- **Docker support.** A minimal [`Dockerfile`](Dockerfile) (Python 3.11-slim +
  git) that packages the `eidetic` CLI, a [`docker-compose.yml`](docker-compose.yml)
  that bind-mounts your vault and loads `.env`, and a `.dockerignore`. Run any
  subcommand in a container without installing Python tooling on the host.
  Build-tested end-to-end (`eidetic --version` / `doctor` / `commit` against a
  bind-mounted vault), with three fixes from that pass: copy the
  `scripts/schemas/templates/skills` dirs *before* `pip install` (the wheel
  force-includes them, so the build failed without them); `git config --global
  --add safe.directory` so git operations work on a vault owned by a non-root
  host user (avoids "dubious ownership"); and an optional `env_file` so compose
  runs before a `.env` exists.
- **CLI tests** ([`tests/test_cli.py`](tests/test_cli.py)) covering `--version`,
  every registered subcommand, and the env-validation guards.
- **Core vs optional** section in [`docs/SETUP.md`](docs/SETUP.md) separating the
  always-available core (vault, commit, changelog, schemas, health) from opt-in
  features (RAG/embeddings, trading, email, LM Studio, dashboard) with each one's
  extra deps and env vars, plus a Docker quick-start.
- **Automated test suite** in [`tests/`](tests/) — 74 hermetic `pytest` tests
  covering the core scripts (`embed_vault`, `build_graph`, `health_check`,
  `send_email`, `vault_commit`, `vault_changelog`, `trading_briefing`). They stub
  every external dependency (network, SMTP, git, and the optional
  `tradingagents` package) and point `VAULT_PATH`/`RAG_DIR` at a temp directory,
  so they need no env vars, no network, and never touch a real vault.
- **GitHub Actions CI** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml))
  — runs ruff, pytest, and pip-audit on every push and pull request to `main`.
- **Development & testing** section in the README and dev/CI tooling (`pytest`,
  `ruff`, `pip-audit`) added to `requirements.txt`.
- **Feature deep-dive docs** in [`docs/features/`](docs/features/README.md) — one
  per feature, explaining how it actually works (internals, data formats,
  configuration, edge cases), grounded in the source: knowledge vault & schemas,
  local RAG search, knowledge graph, git automation, scheduled tasks & skills
  catalog, email reports, trading SDK, and health check & dashboard. Linked from
  the README and the docs index.

### Changed
- **`CONTRIBUTING.md` expanded** into a full contributor guide — dev-environment
  setup, running the test/lint/audit suite, code style, the PR workflow, and a
  project-structure overview — on top of the existing "golden rule" (never
  commit personal data) and PII scan.
- **README**: documented `eidetic trading`, the new `eidetic email` flags,
  env-validation behaviour, a Docker section (+ a Docker pointer under
  Installation), the Docker files in the repo-layout diagram, and updated the
  `.github/` layout line to note the issue/PR templates.
- **Docs sync across the set** to match the streamlined CLI:
  - `docs/ARCHITECTURE.md` — added the `eidetic` CLI as component 0 (the unified
    entry point) and a Deployment section covering checkout / installed tool /
    Docker.
  - `docs/EXAMPLES.md`, `docs/features/email-reports.md` — updated every
    `eidetic email` example to the new flags (with `--json` for raw payloads),
    fixing samples that the flag change would otherwise have broken.
  - `docs/QUICKSTART.md` — corrected the minimum Python to 3.11+ and linked the
    Docker quick-start.
  - `docs/README.md` (docs index) — linked the SETUP core-vs-optional matrix and
    the Docker files.
  - `SECURITY.md` — added a "Running in containers (Docker)" section (no secrets
    or vault data in the image; runtime-only `--env-file`; bind-mounted vault).
- **`pyproject.toml`** continues to declare the `eidetic` entry point and the
  optional dependency groups (`[pdf]`, `[trading]`, `[all]`); these are now the
  documented install path (`pip install -e ".[all]"`) for the optional features.

## [0.3.0] — 2026-06-02

### Added
- **Agent skills catalog.** A self-updating `Skills Catalog.md` note generated
  into the vault, listing every skill (name, description, suggested cadence)
  read from each `skills/*/SKILL.md` frontmatter — so agents reading or
  searching the vault can discover what automations they can invoke. Carries
  `type: reference` frontmatter so the RAG indexer picks it up.
- **`eidetic skills`** — list the catalog in the terminal; `eidetic skills --sync`
  (re)generates the note in the vault (`--output` to override the path).
  `eidetic init` now generates it automatically on setup.
- The `skills/` directory is bundled into the wheel so the catalog works in an
  installed `eidetic` without the source checkout.

## [0.2.0] — 2026-06-02

### Added
- **Installable package** with a unified **`eidetic` CLI** (`pyproject.toml`,
  `eidetic_os/`). Install via `uv tool install` / `pipx` / `pip install -e .`.
  Subcommands `embed`, `graph`, `commit`, `changelog`, `health`, `email`, and
  `schemas` wrap the existing scripts and forward their flags; configuration
  (`.env`) is auto-loaded.
- **`eidetic init`** — guided onboarding: auto-detects a local LLM (LM Studio /
  Ollama / any OpenAI-compatible endpoint), writes `.env`, scaffolds the vault
  skeleton, initialises the vault git repo, and optionally installs the
  `CLAUDE.md` template. Supports `--vault`, `--yes`, `--force`.
- **`eidetic doctor`** — validates the whole setup (Python, vault, git, RAG
  index, embeddings endpoint, SMTP) and reports OK / WARN / FAIL with a
  non-zero exit on failures.
- Optional dependency extras: `eidetic-os[trading]` (yfinance),
  `eidetic-os[pdf]` (pdfplumber), `eidetic-os[all]`.
- `docs/CONFIGURATION.md` — authoritative reference for every environment
  variable (purpose, default, required/optional, consuming scripts).
- `docs/SCRIPTS.md` — complete CLI reference for all scripts and their flags,
  including the previously-undocumented `embed_vault.py` flags
  (`--incremental`, `--folder`, `--pdfs-only`, `--checkpoint-interval`,
  `--batch-size`).
- `docs/FAQ.md` — frequently asked questions and troubleshooting.
- `docs/README.md` — documentation index and recommended reading order.
- `CHANGELOG.md` — this file.

### Changed
- The scripts/schemas/templates are now bundled into the wheel (under
  `eidetic_os_data/`) so an installed `eidetic` works without the source checkout;
  in a source checkout the CLI uses the live files.
- `.env.example` now documents `LM_STUDIO_URL` (used by
  `scripts/trading_briefing.py`, expects a `/v1` suffix) alongside
  `LM_STUDIO_ENDPOINT` (used by `trading/config.py`/`core.py`, no suffix),
  clarifying which script reads which.
- Root `README.md` expanded with the install/CLI quick start, a CLI command
  table, badges, a documentation map, and a configuration pointer.
- `docs/SETUP.md` restructured into "install the package" (recommended) vs
  "run from a source checkout".

## [0.1.0] — 2026-06-02

### Added
- Initial public release of Eidetic OS — a local-first personal AI operating
  system built on Claude Cowork.
- Knowledge vault conventions with per-folder frontmatter schema enforcement
  (`schemas/`).
- Local RAG pipeline (`scripts/embed_vault.py`) and wikilink knowledge graph
  (`scripts/build_graph.py`).
- Git automation: auto-commit (`scripts/vault_commit.py`) and changelog
  (`scripts/vault_changelog.py`).
- Credential-free SMTP email sender (`scripts/send_email.py`).
- System health check across all subsystems (`scripts/health_check.py`).
- Optional multi-agent trading research SDK (`trading/`) and briefing generator
  (`scripts/trading_briefing.py`).
- Nine Claude Cowork scheduled-task skills (`skills/`).
- Templates for `CLAUDE.md`, memory structure, vault skeleton, and a static ops
  dashboard (`templates/`, `dashboard/`).
- Documentation: setup, architecture, rebuild runbook, scheduled tasks, data
  classification; `SECURITY.md`, `CONTRIBUTING.md`, MIT `LICENSE`.

[Unreleased]: https://github.com/paulholland511/atlas-os/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/paulholland511/atlas-os/compare/v1.2.0...v2.0.0
[1.2.0]: https://github.com/paulholland511/atlas-os/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/paulholland511/atlas-os/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/paulholland511/atlas-os/compare/v0.3.0...v1.0.0
[0.3.0]: https://github.com/paulholland511/atlas-os/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/paulholland511/atlas-os/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/paulholland511/atlas-os/releases/tag/v0.1.0
