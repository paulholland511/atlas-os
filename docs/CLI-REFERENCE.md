# Atlas OS — CLI Reference & Stability Contract

**Applies to:** `atlas-os` **v0.3.0** · single binary entry point: `atlas`

This document is the authoritative reference for every `atlas` command, flag,
argument, and environment variable. It was generated from the live CLI
(`atlas <command> --help`) and the underlying scripts — it documents exactly
what exists, not what is planned.

It also serves as a **stability contract**. The commands, flags, exit codes, and
environment variables described here are the public interface of Atlas OS. See
[Stability promise](#stability-promise) at the end for what that guarantees.

- [Overview](#overview)
- [Global flags](#global-flags)
- [Commands at a glance](#commands-at-a-glance)
- [Command reference](#command-reference)
  - [`atlas init`](#atlas-init)
  - [`atlas doctor`](#atlas-doctor)
  - [`atlas health`](#atlas-health)
  - [`atlas embed`](#atlas-embed)
  - [`atlas search`](#atlas-search)
  - [`atlas migrate-vectors`](#atlas-migrate-vectors)
  - [`atlas commit`](#atlas-commit)
  - [`atlas changelog`](#atlas-changelog)
  - [`atlas graph`](#atlas-graph)
  - [`atlas email`](#atlas-email)
  - [`atlas trading`](#atlas-trading)
  - [`atlas skills`](#atlas-skills)
  - [`atlas backends`](#atlas-backends)
  - [`atlas audit`](#atlas-audit)
  - [`atlas schemas`](#atlas-schemas)
  - [`atlas session`](#atlas-session)
- [Environment variables reference](#environment-variables-reference)
- [Exit codes reference](#exit-codes-reference)
- [Stability promise](#stability-promise)

---

## Overview

`atlas` is the single command-line interface to Atlas OS. One command wraps the
whole system: onboarding, the RAG pipeline, the knowledge graph, git automation,
email reports, the trading briefing, the skills catalog, the LLM-backend probe,
and the audit trail.

```text
atlas [GLOBAL OPTIONS] COMMAND [ARGS]...
```

Two equivalent ways to invoke it:

```bash
atlas <command>            # installed console script (pip/uv install)
python -m atlas_os <command>   # module form (works from a source checkout)
```

**Configuration comes from the environment.** A `.env` in the current directory
or the repo root is **auto-loaded** on startup — no manual `source` needed. The
cwd `.env` wins over the repo-root one. Commands that need a specific variable
**validate it up front** and exit with a clear message (and a non-zero code) if
it is missing, so a half-configured feature fails fast rather than part-way
through.

Running `atlas` with no command prints help. Run `atlas --help` or
`atlas <command> --help` at any time for the same information shown here.

---

## Global flags

These apply to the top-level `atlas` command:

| Flag | Short | Description |
|---|---|---|
| `--version` | `-V` | Print `atlas-os <version>` and exit. |
| `--help` | | Show help and exit. Works on every command and subcommand. |
| `--install-completion` | | Install shell tab-completion for the current shell. |
| `--show-completion` | | Print the completion script (to copy or customize). |

```console
$ atlas --version
atlas-os 0.3.0
```

---

## Commands at a glance

| Command | What it does |
|---|---|
| [`atlas init`](#atlas-init) | Interactive onboarding — detect your LLM, write `.env`, scaffold the vault. |
| [`atlas doctor`](#atlas-doctor) | Diagnose the setup by category, offer fixes (`--fix`), emit JSON (`--json`). |
| [`atlas health`](#atlas-health) | Full subsystem health probe. |
| [`atlas embed`](#atlas-embed) | Build / refresh the RAG vector store. |
| [`atlas search`](#atlas-search) | Query the store: hybrid (BM25 + vector) search with reranking. |
| [`atlas migrate-vectors`](#atlas-migrate-vectors) | Migrate a legacy `vectors.json` into the SQLite store. |
| [`atlas commit`](#atlas-commit) | Auto-commit the vault with a categorised message. |
| [`atlas changelog`](#atlas-changelog) | Summarise vault changes over a time window. |
| [`atlas graph`](#atlas-graph) | Rebuild the wikilink knowledge graph. |
| [`atlas email`](#atlas-email) | Send an email via SMTP. |
| [`atlas trading`](#atlas-trading) | Generate a trading research briefing *(optional)*. |
| [`atlas skills`](#atlas-skills) | List, show, and install the agent skills, individually or as packs. |
| [`atlas backends`](#atlas-backends) | Show detected LLM backends; `test` runs an inference. |
| [`atlas audit`](#atlas-audit) | Inspect the append-only audit trail. |
| [`atlas schemas`](#atlas-schemas) | Enforce per-folder frontmatter schemas. |
| [`atlas session`](#atlas-session) | Save Cowork chat transcripts to the vault. |

**CLI-native vs. script-wrapping.** `init`, `doctor`, `skills`, `backends`, and
`audit` are implemented in the CLI itself. The rest forward their flags 1:1 to a
script under `scripts/` (or `schemas/`), so you can also run those directly,
e.g. `python3 scripts/embed_vault.py --full`. Every script-wrapping command
appends an entry to the [audit trail](#atlas-audit) recording what ran, how it
was triggered, the outcome, duration, and what changed.

---

## Command reference

### `atlas init`

Interactive onboarding: detect your LLM, write `.env`, scaffold the vault.

Walks a fresh machine from nothing to a working setup — finds your vault and
local LLM, generates a `.env`, builds the vault directory tree (`​.atlas/`,
`.rag/`, `wiki/`), generates the skills catalog, optionally initialises a git
repo in the vault, and finally runs the [`doctor`](#atlas-doctor) checks to
confirm it all works.

**Usage**

```text
atlas init [OPTIONS]
```

**Flags**

| Flag | Short | Type | Description |
|---|---|---|---|
| `--vault` | | PATH | Vault path (skips the interactive prompt). |
| `--yes` | `-y` | flag | Non-interactive: accept all defaults, no prompts. |
| `--force` | | flag | Overwrite an existing `.env`. |
| `--help` | | flag | Show help and exit. |

**Environment variables**

- Reads `VAULT_PATH` (if already set) as the default vault path; otherwise it
  guesses from `~/Documents/Obsidian`, `~/vault`, or the current directory.
- Probes for a local LLM and, on a match, writes `EMBED_HOST`, `EMBED_PORT`,
  `EMBED_MODEL`, `LM_STUDIO_HOST`, and `LM_STUDIO_PORT` into the generated
  `.env`.
- Interactive runs may also collect and write `SENDER_EMAIL`, `SMTP_SERVER`,
  `SMTP_PORT`, `SMTP_APP_PASSWORD`, and `USER_EMAIL`.

**Exit codes** — `0` on completion (even if the embedded doctor reports
warnings; a closing message flags any FAILs). `--yes` never prompts.

**Examples**

```bash
atlas init                       # full interactive wizard
atlas init --yes                 # accept every default, no prompts
atlas init --vault ~/notes --yes # point at a specific vault, non-interactive
atlas init --force               # regenerate .env over an existing one
```

---

### `atlas doctor`

Validate the Atlas OS setup, diagnose problems, and offer fixes.

Checks are **grouped by category** and colour-coded (green OK / yellow WARN /
red FAIL), and every non-OK row prints an actionable **next step**:

- **Config** — Python version (≥ 3.11) and `VAULT_PATH` (set + exists).
- **Git** — whether the vault is a git repo, plus detection of stale
  `index.lock` / `HEAD.lock` / ref locks left by an interrupted git process.
- **LLM** — probes the active (or `ATLAS_LLM_BACKEND`-forced) backend. If it's
  down, shows a clear diagnosis (*"LM Studio at host:port is not responding. Is
  it running?"*) and lists any reachable backends as alternatives. Also checks
  the embeddings endpoint that RAG depends on.
- **RAG** — whether a vector index exists, whether it's stale (last embed > 24h
  ago → suggests `atlas embed --incremental`), and whether the key files
  (`vectors.db`, `last_embed.txt`) have been offloaded to iCloud ("dataless").
- **SMTP** — whether email credentials are configured (links to the tutorial).

Several checks carry a **fix**. *Safe* fixes (clearing stale git locks) are
applied automatically by `--fix`; *unsafe* fixes (running the init wizard,
creating the vault's first git commit) always prompt for confirmation first,
even under `--fix`. Without `--fix`, every fix is offered interactively.

**Usage**

```text
atlas doctor [OPTIONS]
```

**Flags**

| Flag | Description |
|---|---|
| `--fix` | Apply safe fixes automatically; prompt for unsafe ones. |
| `--json` | Emit the health report as JSON (`{checks, summary}`) and exit. |
| `--help` | Show help and exit. |

**Environment variables** — reads `VAULT_PATH`, `RAG_DIR`, `EMBED_HOST`,
`EMBED_PORT`, `EMBED_URL`, `ATLAS_LLM_BACKEND` (+ the backend `*_URL` vars),
`SENDER_EMAIL`, `SMTP_APP_PASSWORD`.

**JSON shape** — `--json` prints `{"checks": [{category, name, status, detail,
next_step, fix?}], "summary": {ok, warn, fail}}`, where `fix` (present only on
fixable checks) is `{description, safe}`. This shape is part of the v1.0
stability contract.

**Exit codes** — `0` if no check is FAIL (warnings are tolerated); `1` if any
check reports FAIL.

**Examples**

```bash
atlas doctor              # diagnose and offer fixes interactively
atlas doctor --fix        # auto-apply safe fixes (e.g. clear stale git locks)
atlas doctor --json       # machine-readable health report
```

---

### `atlas health`

Full subsystem health probe. Wraps `scripts/health_check.py`.

**Usage**

```text
atlas health [OPTIONS]
```

**Flags**

| Flag | Description |
|---|---|
| `--json` | Emit the report as JSON instead of human-readable text. |
| `--quiet` | Suppress output; communicate via exit code only. |
| `--help` | Show help and exit. |

**Exit codes** — `0` healthy; `1` a runtime error during probing; `2` a
configuration error.

**Examples**

```bash
atlas health
atlas health --json
atlas health --quiet      # for cron / scripting: check $?
```

---

### `atlas embed`

Build / refresh the RAG vector store. Wraps `scripts/embed_vault.py`.

Reads your markdown vault, chunks and embeds it via an OpenAI-compatible
embeddings endpoint, and writes the vectors into a **SQLite store**
(`$RAG_DIR/vectors.db`, via [`atlas_os/vectordb.py`](../atlas_os/vectordb.py)).
Writes are **incremental** — only the touched files' chunks are replaced — and
each batch is committed as it lands, so an interrupted run resumes rather than
corrupting the index. A legacy `vectors.json` is auto-migrated on first run (see
[`atlas migrate-vectors`](#atlas-migrate-vectors)). Exactly one mode flag is
required.

**Usage**

```text
atlas embed (--full | --incremental | --test N | --folder NAME | --pdfs-only) \
            [--checkpoint-interval N] [--batch-size N]
```

**Flags**

| Flag | Argument | Description |
|---|---|---|
| `--full` | | Re-embed the entire vault from scratch. |
| `--incremental` | | Only embed files modified since the last run. |
| `--test` | `N` | Smoke test — embed only the first `N` files. |
| `--folder` | `NAME` | Embed only the given top-level folder. |
| `--pdfs-only` | | Embed only PDF attachments. |
| `--checkpoint-interval` | `N` | Persist progress every `N` files (default `50`). |
| `--batch-size` | `N` | Embeddings request batch size (default `40`). |
| `--help` | | Show help and exit. |

**Environment variables** — requires `VAULT_PATH`. Reads `RAG_DIR` (output
location, default `$VAULT_PATH/.rag`), `EMBED_URL` (or `EMBED_HOST` +
`EMBED_PORT`), `EMBED_MODEL`, and `EMBED_API_KEY` (optional bearer token).

**Exit codes** — `0` success; `1` runtime error (e.g. endpoint down); `2`
configuration error (`VAULT_PATH` unset or an invalid mode flag).

**Examples**

```bash
atlas embed --full                # re-embed everything
atlas embed --incremental         # only changed notes
atlas embed --test 5              # smoke-test the endpoint on 5 files
atlas embed --folder Research     # one folder only
atlas embed --full --batch-size 16
```

---

### `atlas search`

Query the RAG store from the command line. Wraps `scripts/rag_search.py`, which
runs the advanced retrieval pipeline in [`atlas_os/rag.py`](../atlas_os/rag.py):
semantic-chunked content, **BM25 + vector hybrid** fusion (Reciprocal Rank
Fusion), an optional **TF-IDF rerank**, and metadata pre-filtering.

**Usage**

```text
atlas search QUERY [--top-k N] [--mode hybrid|vector|keyword]
                   [--folder NAME ...] [--doc-type TYPE ...] [--tag TAG ...]
                   [--file-type EXT ...] [--since WHEN] [--until WHEN]
                   [--no-rerank] [--json]
```

**Flags**

| Flag | Argument | Description |
|---|---|---|
| `--top-k` / `-k` | `N` | Number of results to return (default `5`). |
| `--mode` | `MODE` | `hybrid` (default), `vector` (semantic only), or `keyword` (BM25 only — no endpoint needed). |
| `--folder` | `NAME` | Restrict to a top-level folder (repeatable). |
| `--doc-type` | `TYPE` | Restrict to a doc_type, e.g. `research` (repeatable). |
| `--tag` | `TAG` | Restrict to a frontmatter tag (repeatable). |
| `--file-type` | `EXT` | Restrict to a file extension, `md` or `pdf` (repeatable). |
| `--since` | `WHEN` | Only chunks modified since `24h` / `7d` / `2w` / `YYYY-MM-DD`. |
| `--until` | `WHEN` | Only chunks modified before the given window/date. |
| `--no-rerank` | | Skip the TF-IDF rerank pass (fusion order only). |
| `--json` | | Emit results as JSON instead of the human-readable list. |

**Environment variables** — requires `VAULT_PATH`. Reads `RAG_DIR` and, for the
query embedding, `EMBED_URL` (or `EMBED_HOST` + `EMBED_PORT`), `EMBED_MODEL`, and
`EMBED_API_KEY`. `--mode keyword` is purely lexical and needs no endpoint.

**Examples**

```bash
atlas search "kelly criterion sizing"                       # hybrid + rerank
atlas search "trading risk" --folder research --tag trading --top-k 10
atlas search "embeddings" --mode vector --file-type md --since 30d
atlas search "decision log" --mode keyword --json           # offline, scriptable
```

---

### `atlas migrate-vectors`

Migrate a legacy `vectors.json` index into the SQLite vector store
(`vectors.db`). Embeds auto-migrate on first run, so this is only needed to
convert an existing index **ahead of time**, or to re-import with `--force`.

Reads the old JSON store and writes every chunk into `vectors.db` (created
alongside it), reporting how many vectors were migrated and which search backend
is active (`sqlite-vec` if the `[vector]` extra is installed, otherwise the
brute-force cosine fallback). The legacy `vectors.json` is left in place so you
can verify search before deleting it.

**Usage**

```text
atlas migrate-vectors [--rag-dir PATH] [--force]
```

**Flags**

| Flag | Argument | Description |
|---|---|---|
| `--rag-dir` | `PATH` | RAG directory holding `vectors.json` (default `$RAG_DIR`, else `$VAULT_PATH/.rag`). |
| `--force` | | Re-import even if `vectors.db` already has vectors (clears it first). |
| `--help` | | Show help and exit. |

**Environment variables** — reads `RAG_DIR`, falling back to `$VAULT_PATH/.rag`.
No embeddings endpoint or `VAULT_PATH` is required (it only moves existing
vectors between files).

**Exit codes** — `0` success (including "already migrated" and "nothing to
migrate"); `1` no legacy `vectors.json` found; `2` no RAG directory resolved.

**Examples**

```bash
atlas migrate-vectors                       # convert $RAG_DIR/vectors.json → vectors.db
atlas migrate-vectors --rag-dir ~/vault/.rag
atlas migrate-vectors --force               # re-import, replacing the existing DB
```

---

### `atlas commit`

Auto-commit the vault with a categorised message. Wraps
`scripts/vault_commit.py`.

**Usage**

```text
atlas commit [--dry-run] [--json]
```

**Flags**

| Flag | Description |
|---|---|
| `--dry-run` | Report what would be committed without committing. |
| `--json` | Output the commit stats as JSON. |
| `--help` | Show help and exit. |

**Environment variables** — requires `VAULT_PATH`. The vault must be a git repo.

**Exit codes** — `0` success (including "nothing to commit"); `1` git/runtime
error; `2` `VAULT_PATH` unset.

**Examples**

```bash
atlas commit
atlas commit --dry-run
atlas commit --json
```

---

### `atlas changelog`

Summarise vault changes over a window. Wraps `scripts/vault_changelog.py`.

**Usage**

```text
atlas changelog [--since WINDOW] [--markdown] [--json]
```

**Flags**

| Flag | Argument | Description |
|---|---|---|
| `--since` | `WINDOW` | Time window in git date format (default `24 hours ago`). |
| `--markdown` | | Render the changelog as Markdown. |
| `--json` | | Emit the changelog as JSON. |
| `--help` | | Show help and exit. |

**Environment variables** — requires `VAULT_PATH`.

**Exit codes** — `0` success; `1` runtime error; `2` `VAULT_PATH` unset.

**Examples**

```bash
atlas changelog
atlas changelog --since "7 days ago" --markdown
atlas changelog --since 2026-06-01 --json
```

---

### `atlas graph`

Rebuild the wikilink knowledge graph. Wraps `scripts/build_graph.py`.

Walks every note's `[[wikilinks]]`, builds the node/edge graph, and writes it to
the RAG directory, printing node/edge counts and the most-connected notes.

**Usage**

```text
atlas graph [--json]
```

**Flags**

| Flag | Description |
|---|---|
| `--json` | Emit machine-readable JSON on error instead of a plain message. |
| `--help` | Show help and exit. |

**Environment variables** — requires `VAULT_PATH`. Reads `RAG_DIR` (output
location, default `$VAULT_PATH/.rag`).

**Exit codes** — `0` success; `1` runtime error; `2` `VAULT_PATH` unset.

**Example**

```bash
atlas graph
```

---

### `atlas email`

Send an email via SMTP, from `--subject`/`--body` flags or a raw `--json`
payload. Wraps `scripts/send_email.py`.

**Usage**

```text
atlas email [--to ADDR] (-s SUBJECT -b BODY | --json PAYLOAD) \
            [--text] [-a FILE]...
```

**Flags**

| Flag | Short | Argument | Description |
|---|---|---|---|
| `--to` | | TEXT | Recipient address (defaults to `USER_EMAIL`). |
| `--subject` | `-s` | TEXT | Email subject line. |
| `--body` | `-b` | TEXT | Email body (HTML by default). |
| `--text` | | flag | Send `--body` as plain text instead of HTML. |
| `--attach` | `-a` | TEXT | File to attach. Repeatable. |
| `--json` | | TEXT | Raw JSON payload — overrides all the flags above. |
| `--help` | | | Show help and exit. |

The `--json` payload accepts the keys `to`, `subject`, `body_html`, `body_text`,
and `attachments` (a list of file paths).

**Environment variables** — requires `SENDER_EMAIL` and `SMTP_APP_PASSWORD`.
Reads `USER_EMAIL` (default recipient), `SENDER_NAME`, `SMTP_SERVER` (default
`smtp.gmail.com`), `SMTP_PORT` (default `587`), and `SMTP_TIMEOUT` (default
`30` seconds).

**Exit codes** — `0` sent; `1` SMTP/runtime error; `2` configuration error
(missing credentials, no recipient, or missing subject/body without `--json`).

**Examples**

```bash
atlas email -s "Hi" -b "<p>Hello</p>" --to me@example.com
atlas email -s "Plain note" -b "Hello" --text --to me@example.com
atlas email -s "Report" -b "<p>Attached</p>" -a report.pdf -a data.csv
atlas email --json '{"to":"me@example.com","subject":"Hi","body_html":"<p>Hi</p>"}'
```

---

### `atlas trading`

Generate a trading research briefing. Wraps `scripts/trading_briefing.py`.

> **Optional component.** Needs the third-party `TradingAgents` package and a
> running local LLM endpoint. Reads `VAULT_PATH` and `LM_STUDIO_*` from the env.

**Usage**

```text
atlas trading [--ticker SYMBOL] [--date YYYY-MM-DD] [--dry-run] [--json]
```

**Flags**

| Flag | Argument | Description |
|---|---|---|
| `--ticker` | `SYMBOL` | Specific ticker, e.g. `BTC-USD`. |
| `--date` | `YYYY-MM-DD` | Analysis date (default: yesterday). |
| `--dry-run` | | Check configuration without running the analysis. |
| `--json` | | Emit machine-readable JSON instead of a human report. |
| `--help` | | Show help and exit. |

**Environment variables** — requires `VAULT_PATH`. Reads `LM_STUDIO_URL` /
`LM_STUDIO_ENDPOINT` (or `LM_STUDIO_HOST` + `LM_STUDIO_PORT`), `LM_STUDIO_MODEL`,
`TRADING_AGENTS_PATH`, `TRADING_TICKERS`, and optionally `ANTHROPIC_API_KEY` /
`ANTHROPIC_MODEL` for the opt-in cloud portfolio-manager step.

**Exit codes** — `0` success; `1` runtime error (endpoint or package missing);
`2` configuration error.

**Examples**

```bash
atlas trading --dry-run
atlas trading --ticker BTC-USD
atlas trading --date 2026-06-02 --json
```

---

### `atlas skills`

List, show, and install the agent skills shipped with Atlas OS. Run with no
subcommand to list the catalog.

**Usage**

```text
atlas skills [--sync] [--output PATH]
atlas skills list
atlas skills show NAME
atlas skills install NAME [--force]
atlas skills packs
atlas skills install-pack NAME [--force]
atlas skills search [QUERY]
atlas skills publish PATH [--output DIR]
atlas skills registry add URL
atlas skills registry list
```

**Top-level flags** (apply when run with no subcommand)

| Flag | Argument | Description |
|---|---|---|
| `--sync` | | Write / refresh the skills catalog note in the vault. |
| `--output` | PATH | Override the catalog note path (used with `--sync`). |
| `--help` | | Show help and exit. |

**Subcommands**

| Subcommand | Argument | Flags | Description |
|---|---|---|---|
| `list` | | | List every available skill (slug + cadence + description). |
| `show` | `NAME` | | Print a skill's `SKILL.md` to stdout. |
| `install` | `NAME` | `--force` | Install a skill into the scheduled-tasks dir, filling in `{{PLACEHOLDER}}` tokens from the environment. `--force` overwrites an existing install. |
| `packs` | | | List the pre-built skill packs (curated bundles for common workflows), with each pack's skill count and members. |
| `install-pack` | `NAME` | `--force` | Install every skill in a pack at once, each filled exactly as `install` would. Already-installed members are skipped unless `--force` is passed. |
| `search` | `[QUERY]` | | Search the configured registries (the **marketplace**) by keyword or tag — matches name, description, and tags. An empty query lists everything. |
| `publish` | `PATH` | `--output DIR` | Validate a skill folder against the schema and package it into a shareable `<name>-<version>.tar.gz` (with a generated `manifest.json`). Defaults to `dist/skills/`. |
| `registry add` | `URL` | | Add a custom registry (URL or local `registry.json` path) to search alongside the built-in one. |
| `registry list` | | | Show the configured registries and how many skills each lists. |

**The skills marketplace** — `search`, `publish`, and `registry` form a small
community marketplace. A *registry* is a JSON document (`registry.json`) listing
skills with metadata (name, version, description, author, tags, dependencies,
download URL). The built-in registry (`skills/registry.json`) ships with every
Atlas OS install and is always searched; add more with `registry add`. See
[`docs/features/skills-marketplace.md`](features/skills-marketplace.md) for the
schema and the publish/share workflow.

**Skill packs** — curated bundles that set up a complete workflow in one command:

| Pack | Skills | What it sets up |
|---|---|---|
| `knowledge` | 5 | Vault management — nightly commit & index, incremental + full RAG re-embedding, lint reports, weekly digest. |
| `communication` | 3 | Email & reporting — daily report email, inbox-triage digest, vault report docs. |
| `trading` | 2 | Trading intelligence — daily trading report, on-demand topic research briefs. |

**Environment variables** — `--sync` and the default install location need
`VAULT_PATH`. `install` / `install-pack` write to `$ATLAS_SKILLS_DIR` if set,
otherwise `$VAULT_PATH/.claude/skills/<name>/`; placeholder values are pulled
from the environment / `.env` (e.g. `SCHEDULED_DIR`, email vars). The registry
config file is resolved from `ATLAS_REGISTRIES_PATH` → `$VAULT_PATH/.atlas/registries.json`
→ `./.atlas/registries.json`.

**Exit codes** — `0` success; `1` install error, validation failure on
`publish`, registry error, or `VAULT_PATH` missing for `--sync`; `2` unknown
skill name, unknown pack name, or missing `SKILL.md`.

**Examples**

```bash
atlas skills                                  # list the catalog
atlas skills list
atlas skills show atlas-daily-report-email
atlas skills install atlas-daily-report-email # deploy one, filling placeholders
atlas skills install atlas-daily-report-email --force
atlas skills --sync                           # regenerate the catalog note
atlas skills packs                            # list the curated skill packs
atlas skills install-pack knowledge           # install a whole workflow at once
atlas skills install-pack trading --force     # reinstall, overwriting existing
atlas skills search trading                   # search the marketplace by keyword/tag
atlas skills publish ./my-skill               # validate + package a skill to share
atlas skills registry add https://example.com/registry.json
atlas skills registry list                    # show configured registries
```

---

### `atlas backends`

Show detected LLM backends; `atlas backends test` runs an inference.

Atlas OS talks to any OpenAI-compatible LLM server. With no argument it probes
every configured backend (LM Studio, Ollama, llama.cpp, a custom
OpenAI-compatible URL) and prints a reachability report, marking the active one.

**Usage**

```text
atlas backends [ACTION]
```

**Arguments**

| Argument | Description |
|---|---|
| `ACTION` | Omit (or pass `list`) to list backends; pass `test` to run a one-shot inference against the active backend. |

**Flags**

| Flag | Description |
|---|---|
| `--help` | Show help and exit. |

**Environment variables** — `ATLAS_LLM_BACKEND` forces a backend
(`lmstudio` / `ollama` / `llamacpp` / `openai-compatible`), skipping detection.
`ATLAS_LLM_MODEL` overrides the reported chat model. Per-backend base URLs:
`LM_STUDIO_URL` / `LM_STUDIO_ENDPOINT`, `OLLAMA_URL`, `LLAMACPP_URL`,
`OPENAI_COMPATIBLE_URL` / `OPENAI_BASE_URL`. API key (first set wins):
`ATLAS_LLM_API_KEY`, `EMBED_API_KEY`, `OPENAI_API_KEY`.

**Exit codes** — `0` success; `1` no backend reachable when running `test`; `2`
an invalid `ATLAS_LLM_BACKEND` value or unknown action.

**Examples**

```bash
atlas backends           # list detected backends, mark the active one
atlas backends test      # verify inference end-to-end
```

---

### `atlas audit`

Inspect the append-only audit trail of autonomous actions. Every
script-wrapping command appends an entry recording action, trigger, status,
duration, and what changed.

**Usage**

```text
atlas audit show [--limit N] [--action NAME] [--since WINDOW]
atlas audit tail
atlas audit export [--format csv|json] [--output FILE] [--action NAME] [--since WINDOW]
```

**Subcommands**

`audit show` — show recent entries (newest last), with optional filters:

| Flag | Short | Default | Description |
|---|---|---|---|
| `--limit` | `-n` | `20` | Max entries to show. |
| `--action` | | | Filter by action name (e.g. `commit`, `embed`). |
| `--since` | | | Only entries since e.g. `24h`, `7d`, or `2026-06-01`. |

`audit tail` — show the last 5 entries in a compact one-line format. No flags.

`audit export` — export the audit log for compliance reporting:

| Flag | Short | Default | Description |
|---|---|---|---|
| `--format` | `-f` | `csv` | Export format: `csv` or `json`. |
| `--output` | `-o` | | Write to a file instead of stdout. |
| `--action` | | | Filter by action name. |
| `--since` | | | Only entries since e.g. `30d`. |

**Environment variables** — the log lives at `$ATLAS_AUDIT_PATH` if set,
otherwise `$VAULT_PATH/.atlas/audit.jsonl`.

**Exit codes** — `0` success; `2` a bad `--since` value or an invalid
`--format`.

**Examples**

```bash
atlas audit show
atlas audit show --action commit --since 7d
atlas audit show -n 50
atlas audit tail
atlas audit export --format csv -o audit-report.csv
atlas audit export --format json --since 30d
```

---

### `atlas schemas`

Enforce per-folder frontmatter schemas on the markdown vault. Wraps
`schemas/enforce_schemas.py`.

**Usage**

```text
atlas schemas [--dry-run] [--folder NAME] [--verbose]
```

**Flags**

| Flag | Argument | Description |
|---|---|---|
| `--dry-run` | | Show the changes without writing them. |
| `--folder` | `NAME` | Only process this top-level folder. |
| `--verbose` | | Show each file as it is processed. |
| `--help` | | Show help and exit. |

**Environment variables** — requires `VAULT_PATH`.

**Exit codes** — `0` success; `1` runtime error; `2` `VAULT_PATH` unset.

**Examples**

```bash
atlas schemas --dry-run
atlas schemas --folder Research --verbose
atlas schemas
```

---

### `atlas session`

Save Claude Cowork chat transcripts to the vault as clean session-log notes.
Wraps `scripts/save_sessions.py`. Has two subcommands: `save` and `list`.

Each captured session becomes `$VAULT_PATH/sessions/session-log-YYYY-MM-DD-<title>.md`
with `[session-log, cowork]` frontmatter, a `session_id`, an extracted summary,
the key actions taken, and the files modified — all derived deterministically
from the local transcript (no LLM call, no network). Notes are keyed by session
id and overwritten in place, so re-running is idempotent.

**Usage**

```text
atlas session save [--since WINDOW | --all] [--sessions-dir PATH] [--json]
atlas session list [--limit N] [--sessions-dir PATH] [--json]
```

**`save` flags**

| Flag | Argument | Description |
|---|---|---|
| `--since` | `WINDOW` | Capture sessions active since e.g. `24h`, `7d`, `2026-06-01`. |
| `--all` | | Capture every session ever (ignores the watermark). |
| `--sessions-dir` | `PATH` | Override the Cowork session store location. |
| `--json` | | Emit a machine-readable summary. |
| `--help` | | Show help and exit. |

With no window flag, `save` captures everything new or changed since the last
run, tracked by a watermark in `$VAULT_PATH/.atlas/last_session_save.txt`.

**`list` flags**

| Flag | Argument | Description |
|---|---|---|
| `--limit` / `-n` | `N` | Max sessions to show (default `20`). |
| `--sessions-dir` | `PATH` | Override the Cowork session store location. |
| `--json` | | Emit the session list as JSON. |
| `--help` | | Show help and exit. |

**Environment variables** — `save` requires `VAULT_PATH`. Both subcommands read
`CLAUDE_SESSIONS_DIR` to locate the Cowork session store (defaults to the macOS
path `~/Library/Application Support/Claude/local-agent-mode-sessions`).

**Exit codes** — `0` success; `1` runtime error; `2` `VAULT_PATH` unset or bad
`--since` value. `list` never needs `VAULT_PATH`.

**Examples**

```bash
atlas session list
atlas session save                 # new/changed since last run
atlas session save --since 12h     # half-day window (twice-daily capture, the default)
atlas session save --since 24h     # the day's sessions (single nightly capture)
atlas session save --all --json
```

---

## Environment variables reference

Every variable Atlas OS reads. Set them in a `.env` (auto-loaded) or your shell.
Defaults shown are the built-in fallbacks; see [`.env.example`](../.env.example)
and [`docs/CONFIGURATION.md`](CONFIGURATION.md) for the annotated source.

### Core

| Variable | Default | Controls |
|---|---|---|
| `VAULT_PATH` | — (required by most commands) | Absolute path to your markdown vault. |
| `RAG_DIR` | `$VAULT_PATH/.rag` | Where the RAG vector store and graph are written. |
| `ATLAS_AUDIT_PATH` | `$VAULT_PATH/.atlas/audit.jsonl` | Location of the append-only audit log. |
| `ATLAS_TRIGGER` | `cli` | Tag recorded in the audit trail for how a command ran (a scheduler sets `scheduled`). |
| `SCHEDULED_DIR` | — | Where your Claude scheduled-task `SKILL.md` folders live. |
| `ATLAS_SKILLS_DIR` | `$VAULT_PATH/.claude/skills` | Where `atlas skills install` writes installed skills. |
| `CLAUDE_SESSIONS_DIR` | macOS Cowork session store | Where `atlas session` reads Cowork transcripts from. |
| `SESSION_CAPTURE_FREQUENCY` | `twice` | Intended cadence for the session-capture skills: `twice` (morning + afternoon, each `--since 12h`), `daily` (one nightly `--since 24h` run), `hourly` (every hour, heavy users), or `manual` (no schedule — run `atlas session save` yourself). A scheduling hint you wire your cron/skills to; documents intent rather than enforcing it. |

### Embeddings (RAG)

| Variable | Default | Controls |
|---|---|---|
| `EMBED_HOST` | `localhost` | Embeddings endpoint host. |
| `EMBED_PORT` | `5555` | Embeddings endpoint port. |
| `EMBED_URL` | — | Full embeddings URL; overrides host/port if set. |
| `EMBED_MODEL` | `text-embedding-nomic-embed-text-v1.5` | Embeddings model name. |
| `EMBED_API_KEY` | — | Bearer token, only if the endpoint requires one. |

### LLM backends

| Variable | Default | Controls |
|---|---|---|
| `ATLAS_LLM_BACKEND` | — (auto-detect) | Force a backend: `lmstudio` / `ollama` / `llamacpp` / `openai-compatible`. |
| `ATLAS_LLM_MODEL` | — | Override the chat model name reported to callers. |
| `ATLAS_LLM_API_KEY` | — | API key for the chat backend (falls back to `EMBED_API_KEY`, then `OPENAI_API_KEY`). |
| `LM_STUDIO_URL` | `http://$LM_STUDIO_HOST:$LM_STUDIO_PORT/v1` | LM Studio base URL (includes `/v1`; used by `trading_briefing.py`). |
| `LM_STUDIO_ENDPOINT` | `http://$LM_STUDIO_HOST:$LM_STUDIO_PORT` | LM Studio base URL (no `/v1`; used by `trading/`). |
| `LM_STUDIO_HOST` | `localhost` | LM Studio host (chat completions). |
| `LM_STUDIO_PORT` | `5555` | LM Studio port. |
| `LM_STUDIO_MODEL` | `local-model` | Chat model name. |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama base URL. |
| `LLAMACPP_URL` | `http://localhost:8080` | llama.cpp base URL. |
| `OPENAI_COMPATIBLE_URL` | — | Custom OpenAI-compatible base URL (also accepts `OPENAI_BASE_URL`). |
| `OPENAI_API_KEY` | — | API key for the custom OpenAI-compatible backend. |

### Email (SMTP)

| Variable | Default | Controls |
|---|---|---|
| `SENDER_EMAIL` | — (required to send) | The account that sends reports. |
| `SENDER_NAME` | `Atlas` | Display name on outgoing mail. |
| `SMTP_SERVER` | `smtp.gmail.com` | SMTP server hostname. |
| `SMTP_PORT` | `587` | SMTP server port. |
| `SMTP_APP_PASSWORD` | — (required to send) | SMTP app password — never commit it. |
| `SMTP_TIMEOUT` | `30` | SMTP connect/read timeout, seconds. |
| `USER_EMAIL` | — | Default recipient for reports / `atlas email`. |

### Trading (optional)

| Variable | Default | Controls |
|---|---|---|
| `TRADING_AGENTS_PATH` | — | Path to the third-party TradingAgents package. |
| `TRADING_TICKERS` | — | Comma-separated tickers, e.g. `BTC-USD,ETH-USD`. |
| `ANTHROPIC_API_KEY` | — | Opt-in cloud portfolio-manager step. |
| `ANTHROPIC_MODEL` | — | Model for the cloud portfolio-manager step. |

### Other (optional)

| Variable | Default | Controls |
|---|---|---|
| `TTS_HOST` | `localhost` | Text-to-speech host. |
| `TTS_PORT` | `8800` | Text-to-speech port. |
| `DASHBOARD_FRONTEND_PORT` | `3000` | Dashboard frontend port. |
| `DASHBOARD_BACKEND_PORT` | `5001` | Dashboard backend port. |
| `GITHUB_REPO` | — | Remote mirror for the vault, if you use one. |

---

## Exit codes reference

Atlas OS uses a small, stable set of exit codes across every command, so scripts
and schedulers can branch on `$?`:

| Code | Name | Meaning |
|---|---|---|
| `0` | Success | The command completed. (For `doctor`, warnings are tolerated; for `commit`, "nothing to commit" still exits `0`.) |
| `1` | Runtime error | Something failed while running: an endpoint was down, an SMTP send failed, a git operation failed, or `doctor` found a FAIL. No raw traceback is ever shown — just a one-line message. |
| `2` | Configuration error | The command was misconfigured before it could do real work: a required env var (e.g. `VAULT_PATH`) was unset, an argument was invalid, or a flag value was out of range. |

One additional code surfaces from interrupted script-wrapping commands:

| Code | Name | Meaning |
|---|---|---|
| `130` | Interrupted | The process was cancelled with `Ctrl-C` (`SIGINT` / `KeyboardInterrupt`). |

With `--json`, error output is structured as
`{"status": "error", "error": "<message>"}` on stderr instead of a plain line.

---

## Stability promise

**These interfaces are stable as of v1.0.** The following are the public,
supported contract of Atlas OS:

- **Command names** — every command and subcommand listed above.
- **Flags and arguments** — their names, short forms, accepted values, and
  defaults, as documented in each command's reference.
- **Environment variables** — their names, meanings, and default values, as
  listed in the [environment variables reference](#environment-variables-reference).
- **Exit codes** — the `0` / `1` / `2` (and `130`) meanings in the
  [exit codes reference](#exit-codes-reference).
- **JSON output shape** — the `{"status": "error", "error": ...}` error envelope
  and the documented `--json` payloads.

**Breaking changes to any of the above require a major version bump** (per
[Semantic Versioning](https://semver.org/)). A breaking change means: removing
or renaming a command, flag, argument, or environment variable; changing a
flag's default in a way that alters behaviour; repurposing an exit code; or
changing the shape of documented JSON output.

**What is *not* covered by this promise** (may change in a minor release):

- Exact human-readable output text, colours, spacing, and progress formatting.
- New commands, new flags, and new environment variables that are additive and
  backward-compatible.
- Internal script module layout under `scripts/` and `atlas_os/` (run commands
  through `atlas`, not by importing internals).
- The optional [`atlas trading`](#atlas-trading) component, which depends on a
  third-party package and is best-effort.

Deprecations will be announced in [`CHANGELOG.md`](../CHANGELOG.md) at least one
minor release before removal, with the replacement documented here.

---

*Generated from the live CLI for `atlas-os` v0.3.0. To regenerate after a CLI
change, run `atlas <command> --help` for each command and update this file. See
also [`docs/CONFIGURATION.md`](CONFIGURATION.md) for the annotated env-var source
and [`docs/SCRIPTS.md`](SCRIPTS.md) for the underlying scripts.*
