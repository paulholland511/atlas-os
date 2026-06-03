# Configuration Reference

Every Atlas OS component is configured **entirely through environment
variables** — there are no hardcoded paths, hosts, emails, or secrets anywhere
in the codebase. This page is the authoritative reference for all of them: what
each variable does, its default, whether it's required, and exactly which
scripts read it.

The canonical place to set these is a local `.env` file (copied from
[`../.env.example`](../.env.example)) that you load into your shell:

```bash
cp .env.example .env       # then edit
set -a; source .env; set +a
```

`.env` is git-ignored. **Never commit real secrets.**

---

## At a glance

| Variable | Required? | Default | Used by |
|---|---|---|---|
| `VAULT_PATH` | **Yes** (almost everything) | `.` (cwd) | all scripts |
| `RAG_DIR` | No | `$VAULT_PATH/.rag` | embed, graph, health |
| `SCHEDULED_DIR` | No | `~/Documents/Claude/Scheduled` | health |
| `ATLAS_SKILLS_DIR` | No | `$VAULT_PATH/.claude/skills` | `atlas skills install` |
| `EMBED_HOST` | No | `localhost` | embed, health |
| `EMBED_PORT` | No | `5555` | embed, health |
| `EMBED_MODEL` | No | `text-embedding-nomic-embed-text-v1.5` | embed |
| `EMBED_URL` | No | `http://$EMBED_HOST:$EMBED_PORT/v1/embeddings` | embed |
| `EMBED_API_KEY` | No | `""` (none) | embed |
| `LM_STUDIO_HOST` | No | `localhost` | trading |
| `LM_STUDIO_PORT` | No | `5555` | trading |
| `LM_STUDIO_MODEL` | No | `local-model` | trading |
| `LM_STUDIO_URL` | No | `http://$LM_STUDIO_HOST:$LM_STUDIO_PORT/v1` | `scripts/trading_briefing.py` |
| `LM_STUDIO_ENDPOINT` | No | `http://$LM_STUDIO_HOST:$LM_STUDIO_PORT` | `trading/config.py`, `trading/core.py` |
| `TTS_HOST` | No | `localhost` | health |
| `TTS_PORT` | No | `8800` | health |
| `SENDER_EMAIL` | **Yes** (to send email) | `""` | send_email |
| `SENDER_NAME` | No | `Atlas` | send_email |
| `SMTP_SERVER` | No | `smtp.gmail.com` | send_email |
| `SMTP_PORT` | No | `587` | send_email |
| `SMTP_APP_PASSWORD` | **Yes** (to send email) | `""` | send_email, health |
| `USER_EMAIL` | No (used by tasks) | — | scheduled tasks |
| `DASHBOARD_FRONTEND_PORT` | No | `3000` | health |
| `DASHBOARD_BACKEND_PORT` | No | `5001` | health |
| `TRADING_AGENTS_PATH` | No | `~/Documents/TradingAgents` | trading |
| `TRADING_TICKERS` | No | `BTC-USD,ETH-USD` | trading |
| `ANTHROPIC_API_KEY` | No (opt-in) | — | trading PM (cloud) |
| `ANTHROPIC_MODEL` | No | `claude-opus-4-6` | trading PM (cloud) |
| `GITHUB_REPO` | No | — | informational |

> "Required?" means the listed feature won't work without it. The vault,
> schemas, git, and reporting scripts only need `VAULT_PATH`. RAG needs the
> embeddings vars + a running LLM. Email needs the SMTP vars. Trading needs the
> LM Studio vars + a running LLM.

---

## Vault

### `VAULT_PATH` — **required by almost everything**
Absolute path to your markdown vault. Read by every script. If unset it
defaults to the current directory (`.`), which is almost never what you want —
scripts that strictly require it (`embed_vault`, `build_graph`, `vault_commit`,
`vault_changelog`, `trading_briefing`, `enforce_schemas`) exit with an error
when it isn't set.

```bash
VAULT_PATH=~/Documents/Obsidian/MyVault
```

### `RAG_DIR`
Where the RAG vector store (`vectors.json`), knowledge graph (`graph.json`),
and run markers (`last_embed.txt`, `index.lock`) are written.
Default: `$VAULT_PATH/.rag`. Read by `embed_vault.py`, `build_graph.py`, and
`health_check.py`. Always keep this **git-ignored** — it's derived data.

### `SCHEDULED_DIR`
Directory holding your installed Claude scheduled-task `SKILL.md` folders.
Default: `~/Documents/Claude/Scheduled`. Only `health_check.py` reads it (to
confirm tasks are installed).

### `ATLAS_SKILLS_DIR`
Where `atlas skills install <name>` writes a skill's `SKILL.md` (under a
`<name>/` subfolder). Default: `$VAULT_PATH/.claude/skills`. Set this to point
installs at your real Claude scheduled-tasks directory instead.

---

## Local LLM — embeddings (RAG)

An OpenAI-compatible embeddings endpoint, e.g. [LM Studio](https://lmstudio.ai/)
or [Ollama](https://ollama.com/). Used by `embed_vault.py`; the host/port are
also probed by `health_check.py`.

- **`EMBED_HOST`** — host (default `localhost`).
- **`EMBED_PORT`** — port (default `5555`).
- **`EMBED_MODEL`** — embeddings model name (default
  `text-embedding-nomic-embed-text-v1.5`).
- **`EMBED_URL`** — full URL, overrides host/port. Default
  `http://$EMBED_HOST:$EMBED_PORT/v1/embeddings`. Set this if your endpoint
  uses a non-standard path.
- **`EMBED_API_KEY`** — bearer token, only if your endpoint requires one
  (default empty — local servers usually don't).

Verify reachability: `curl http://$EMBED_HOST:$EMBED_PORT/v1/models`.

---

## Local LLM — chat completions (trading)

> ⚠️ **Two variables, two shapes.** The trading code grew two entry points that
> read the chat endpoint differently. Set whichever matches the path you run, or
> set both. Leaving them unset falls back to host/port, which is fine for a
> standard LM Studio / Ollama setup.

- **`LM_STUDIO_HOST`** — host (default `localhost`).
- **`LM_STUDIO_PORT`** — port (default `5555`).
- **`LM_STUDIO_MODEL`** — chat model name (default `local-model`).
- **`LM_STUDIO_URL`** — used by **`scripts/trading_briefing.py`**. **Include the
  `/v1` suffix.** Default `http://$LM_STUDIO_HOST:$LM_STUDIO_PORT/v1`.
- **`LM_STUDIO_ENDPOINT`** — used by **`trading/config.py`** and
  **`trading/core.py`**. **No `/v1` suffix** (the client appends paths itself).
  Default `http://$LM_STUDIO_HOST:$LM_STUDIO_PORT`.

---

## Text-to-speech (optional)

A local TTS service. Only `health_check.py` probes it — Atlas OS ships no TTS
server itself.

- **`TTS_HOST`** — default `localhost`.
- **`TTS_PORT`** — default `8800`.

---

## Email (SMTP)

Read by `send_email.py`; `SMTP_APP_PASSWORD` is also checked by
`health_check.py` to report email readiness.

- **`SENDER_EMAIL`** — the "from" address. **Required to send.**
- **`SENDER_NAME`** — display name (default `Atlas`).
- **`SMTP_SERVER`** — SMTP host (default `smtp.gmail.com`).
- **`SMTP_PORT`** — SMTP port (default `587`, STARTTLS).
- **`SMTP_APP_PASSWORD`** — the app password / SMTP password. **Required to
  send.** For Gmail, generate an [app password](https://myaccount.google.com/apppasswords)
  (requires 2FA) — a normal account password will not work. **Secret — never
  commit.**
- **`USER_EMAIL`** — where reports are sent (usually yourself). Consumed by the
  scheduled-task prompts rather than `send_email.py` directly.

---

## Dashboard (optional)

Only `health_check.py` reads these, to probe a local dashboard if you run one.

- **`DASHBOARD_FRONTEND_PORT`** — default `3000`.
- **`DASHBOARD_BACKEND_PORT`** — default `5001`.

---

## Trading module (optional)

Read by `scripts/trading_briefing.py` and the `trading/` package. See also
[`../trading/README.md`](../trading/README.md).

- **`TRADING_AGENTS_PATH`** — path to the third-party TradingAgents package
  (default `~/Documents/TradingAgents`).
- **`TRADING_TICKERS`** — comma-separated symbols (default `BTC-USD,ETH-USD`).
- **`ANTHROPIC_API_KEY`** — **only** if you opt into the cloud Portfolio
  Manager step (off by default). When set with `provider: claude`, it sends
  *anonymous analyst votes only* — never your notes or positions. **Secret.**
- **`ANTHROPIC_MODEL`** — model for the cloud PM step (default
  `claude-opus-4-6`).

---

## Git (optional / informational)

- **`GITHUB_REPO`** — if you mirror your *private* vault to a remote, record it
  here (`your-username/your-vault`). Informational; the commit/changelog scripts
  operate on the local `VAULT_PATH` git repo regardless.

---

## How the scripts resolve config

- Variables are read with `os.environ.get(NAME, DEFAULT)` at import time.
- Paths are expanded (`~` → home) and resolved to absolute.
- A `URL`/`ENDPOINT` override, when set, takes precedence over the
  corresponding host/port pair.
- Nothing is read from a file automatically — you must `source` your `.env`
  (or otherwise export the vars) into the environment each shell session. Tools
  like [`direnv`](https://direnv.net/) automate this per-directory.

See [`SCRIPTS.md`](SCRIPTS.md) for the per-script CLI reference and
[`DATA-CLASSIFICATION.md`](DATA-CLASSIFICATION.md) for which of these values are
secret and how data flows.
