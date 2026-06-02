# Script & CLI Reference

Complete reference for every executable in Atlas OS: what it does, how to call
it, every flag, the environment variables it reads, and what it writes. All
scripts read configuration from the environment — see
[`CONFIGURATION.md`](CONFIGURATION.md).

## Two ways to run

If you installed the package (`uv tool install` / `pipx` / `pip install -e .`),
the **`atlas` CLI** wraps every script and auto-loads your `.env` — no manual
`source` needed. Each subcommand forwards its flags straight through:

```bash
atlas embed --full --batch-size 16      # == python3 scripts/embed_vault.py --full --batch-size 16
atlas commit --dry-run
atlas schemas --folder projects
```

| CLI command | Wraps |
|---|---|
| `atlas embed` | `scripts/embed_vault.py` |
| `atlas graph` | `scripts/build_graph.py` |
| `atlas commit` | `scripts/vault_commit.py` |
| `atlas changelog` | `scripts/vault_changelog.py` |
| `atlas health` | `scripts/health_check.py` |
| `atlas email` | `scripts/send_email.py` |
| `atlas schemas` | `schemas/enforce_schemas.py` |

CLI-only commands (no script equivalent): `atlas init` and `atlas doctor` (see
[SETUP.md](SETUP.md)), and `atlas skills` — list the agent skills catalog, or
`atlas skills --sync` to (re)generate the `Skills Catalog.md` note in your vault
(see [SCHEDULED-TASKS.md](SCHEDULED-TASKS.md#the-skills-catalog-agent-discovery)).

To run the scripts **directly** instead, load your env first:

```bash
set -a; source .env; set +a
python3 scripts/<name>.py [flags]
```

The flags below are identical whether you call `atlas <cmd>` or the script.

| Script | One-liner |
|---|---|
| [`scripts/embed_vault.py`](#embed_vaultpy) | Chunk + embed the vault into a local RAG vector store |
| [`scripts/build_graph.py`](#build_graphpy) | Build the wikilink knowledge graph |
| [`scripts/vault_commit.py`](#vault_commitpy) | Auto-commit the vault with a categorised message |
| [`scripts/vault_changelog.py`](#vault_changelogpy) | Summarise what changed in the vault over a window |
| [`scripts/health_check.py`](#health_checkpy) | Probe every subsystem and report UP/DEGRADED/DOWN |
| [`scripts/send_email.py`](#send_emailpy) | Send an email (with attachments) via SMTP |
| [`scripts/trading_briefing.py`](#trading_briefingpy) | Generate a multi-agent trading research note |
| [`schemas/enforce_schemas.py`](#enforce_schemaspy) | Enforce per-folder frontmatter schemas |

---

## `embed_vault.py`

The RAG pipeline. Chunks markdown (~500 tokens, 50 overlap) and optionally PDFs,
embeds each chunk via your OpenAI-compatible endpoint, and stores vectors in
`$RAG_DIR/vectors.json`. After a **full** run it also rebuilds the knowledge
graph (it shells out to `build_graph.py`).

**Usage**

```bash
python3 scripts/embed_vault.py --full                       # re-embed everything
python3 scripts/embed_vault.py --incremental                # only files changed since last run
python3 scripts/embed_vault.py --test 5                     # smoke test on first 5 files
python3 scripts/embed_vault.py --folder research            # only one top-level folder
python3 scripts/embed_vault.py --pdfs-only                  # only PDF files
python3 scripts/embed_vault.py --full --checkpoint-interval 50 --batch-size 16
```

**Modes** (exactly one required):

| Flag | Effect |
|---|---|
| `--full` | Re-embed every file from scratch; rebuilds the graph afterwards |
| `--incremental` | Embed only files modified since the last run (per `last_embed.txt`) |
| `--test N` | Embed only the first `N` files — a fast connectivity/sanity check |
| `--folder NAME` | Embed only files under top-level folder `NAME` |
| `--pdfs-only` | Embed only PDF files (runs as a full pass over PDFs) |

**Modifier flags** (combine with a mode):

| Flag | Effect |
|---|---|
| `--checkpoint-interval N` | Persist progress every `N` files (resumable on interrupt) |
| `--batch-size N` | Embeddings request batch size |

**Reads:** `VAULT_PATH` (required), `RAG_DIR`, `EMBED_HOST`, `EMBED_PORT`,
`EMBED_URL`, `EMBED_MODEL`, `EMBED_API_KEY`.
**Writes:** `$RAG_DIR/vectors.json`, `$RAG_DIR/graph.json` (after `--full`),
`$RAG_DIR/last_embed.txt`.
**Needs:** a running embeddings endpoint.

---

## `build_graph.py`

Walks every `.md` file under `VAULT_PATH`, resolves `[[wikilinks]]` to files,
and writes a `graph.json` with nodes, edges, adjacency, and backlinks. Used by
the dashboard and to surface "related notes". Usually invoked automatically by
`embed_vault.py --full`; run it standalone to refresh just the graph.

**Usage**

```bash
python3 scripts/build_graph.py          # no flags
```

**Reads:** `VAULT_PATH` (required), `RAG_DIR`.
**Writes:** `$RAG_DIR/graph.json`.

---

## `vault_commit.py`

Stages everything in the vault git repo (respecting its `.gitignore`) and writes
a commit whose message summarises how many files were added/modified/deleted,
tagged by which top-level folders changed. Intended for the nightly task.

**Usage**

```bash
python3 scripts/vault_commit.py             # commit all changes
python3 scripts/vault_commit.py --dry-run   # report what would be committed; commit nothing
python3 scripts/vault_commit.py --json       # emit stats as JSON
```

| Flag | Effect |
|---|---|
| `--dry-run` | Show the staged changes and the message; do not commit |
| `--json` | Output the commit stats as JSON (for the dashboard / tasks) |

**Reads:** `VAULT_PATH` (required, must be a git repo).
**Writes:** a git commit in the vault repo (none with `--dry-run`).

---

## `vault_changelog.py`

Aggregates added/modified/deleted files across all vault commits in a time
window — the "what changed overnight" feed for a morning briefing, or a weekly
review.

**Usage**

```bash
python3 scripts/vault_changelog.py                       # last 24 hours
python3 scripts/vault_changelog.py --since "7 days ago"  # any git date expression
python3 scripts/vault_changelog.py --markdown            # markdown-formatted
python3 scripts/vault_changelog.py --json                # JSON output
```

| Flag | Effect |
|---|---|
| `--since EXPR` | Window start as a git date (`"24 hours ago"`, `"7 days ago"`, `2026-01-01`). Default: last 24h |
| `--markdown` | Render as markdown (for briefings / email) |
| `--json` | Render as JSON (for the dashboard) |

**Reads:** `VAULT_PATH` (required, must be a git repo).
**Writes:** nothing — read-only over git history.

---

## `health_check.py`

Endpoint-aware probe of every subsystem: vault present & indexed, RAG store
fresh, embeddings endpoint up, TTS, dashboard ports, git state, scheduled-tasks
directory, and SMTP readiness. Each HTTP probe has a known-good URL and an
accept range, so backends that 404 on `/` aren't falsely marked down.

**Usage**

```bash
python3 scripts/health_check.py            # human-readable report
python3 scripts/health_check.py --json     # machine-readable JSON (for the dashboard)
python3 scripts/health_check.py --quiet    # only print problems
```

| Flag | Effect |
|---|---|
| `--json` | Emit the full status object as JSON (powers `GET /api/health`) |
| `--quiet` | Suppress UP lines; show only DEGRADED / DOWN |

**Reads:** `VAULT_PATH`, `RAG_DIR`, `SCHEDULED_DIR`, `EMBED_HOST`, `EMBED_PORT`,
`TTS_HOST`, `TTS_PORT`, `DASHBOARD_FRONTEND_PORT`, `DASHBOARD_BACKEND_PORT`,
`SMTP_APP_PASSWORD`.
**Writes:** nothing.

> Subsystems that are intentionally not installed (e.g. TTS, dashboard) report
> **DEGRADED**, not a failure.

---

## `send_email.py`

Credential-free SMTP sender. Takes a single JSON argument describing the
message. The password comes from the environment — nothing is hardcoded.

**Usage**

```bash
python3 scripts/send_email.py '{
  "to": "someone@example.com",
  "subject": "Hello",
  "body_html": "<p>Hi</p>",
  "body_text": "Hi",
  "attachments": ["/path/to/file.pdf"]
}'
```

**JSON fields:** `to` (required), `subject`, `body_html`, `body_text`,
`attachments` (list of absolute paths). Provide at least one of `body_html` /
`body_text`.

**Reads:** `SMTP_APP_PASSWORD` (required), `SENDER_EMAIL` (required),
`SENDER_NAME`, `SMTP_SERVER`, `SMTP_PORT`.
**Writes:** sends an email. Exits non-zero on SMTP failure.

> Sending email is an outward-facing action. The scheduled tasks call this for
> you; when testing manually, send to yourself first.

---

## `trading_briefing.py`

**Optional.** Runs the multi-agent TradingAgents analysis for your tickers
against a local LLM and saves the result as a markdown note in the vault (so RAG
indexes it). Requires the third-party TradingAgents package and a running chat
endpoint.

> ⚠️ **Not financial advice.** Research/automation template only. See
> [`../trading/README.md`](../trading/README.md).

**Usage**

```bash
python3 scripts/trading_briefing.py                    # all TRADING_TICKERS
python3 scripts/trading_briefing.py --ticker BTC-USD   # a single symbol
python3 scripts/trading_briefing.py --date 2026-01-01  # as-of date
python3 scripts/trading_briefing.py --dry-run          # run analysis, don't write the note
```

| Flag | Effect |
|---|---|
| `--ticker SYM` | Analyse one symbol instead of the full list |
| `--date YYYY-MM-DD` | Run the analysis as of a specific date |
| `--dry-run` | Produce the briefing but don't write it into the vault |

**Reads:** `VAULT_PATH` (required), `LM_STUDIO_HOST`, `LM_STUDIO_PORT`,
`LM_STUDIO_URL`, `LM_STUDIO_MODEL`, `TRADING_AGENTS_PATH`, `TRADING_TICKERS`.
**Writes:** a markdown note under `VAULT_PATH` (none with `--dry-run`).

---

## `enforce_schemas.py`

Validates each note's YAML frontmatter against the schema for its top-level
folder and fills in missing required fields with sensible defaults (inferring
`date`/`title` from the filename where possible). **Non-destructive** — only
adds missing fields, never overwrites, writes atomically. Schema definitions and
the folder→schema table live in
[`../schemas/frontmatter-schemas.md`](../schemas/frontmatter-schemas.md).

**Usage**

```bash
python3 schemas/enforce_schemas.py --dry-run            # preview changes
python3 schemas/enforce_schemas.py                      # apply
python3 schemas/enforce_schemas.py --folder projects    # restrict to one folder
python3 schemas/enforce_schemas.py --verbose            # show every file examined
```

| Flag | Effect |
|---|---|
| `--dry-run` | Report what would change; write nothing |
| `--folder NAME` | Process only the given top-level folder |
| `--verbose` | List every file, not just changed ones |

**Reads:** `VAULT_PATH` (required).
**Writes:** frontmatter into existing notes in place (none with `--dry-run`).

---

## Typical sequences

**First-time index**

```bash
python3 schemas/enforce_schemas.py --dry-run     # sanity check
python3 schemas/enforce_schemas.py               # normalise frontmatter
python3 scripts/embed_vault.py --test 5          # confirm the endpoint works
python3 scripts/embed_vault.py --full            # full index + graph
python3 scripts/health_check.py                  # verify everything is UP
```

**Nightly (what the scheduled tasks automate)**

```bash
python3 scripts/embed_vault.py --incremental
python3 scripts/vault_commit.py
python3 scripts/vault_changelog.py --markdown
```

See [`SCHEDULED-TASKS.md`](SCHEDULED-TASKS.md) for the skill prompts that wrap
these on a schedule.
