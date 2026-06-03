# Setup

Step-by-step installation of Atlas OS from scratch.

## Core vs optional features

Atlas OS has a small **core** that works with nothing but Python, git, and a
markdown vault. Everything else is **optional** and degrades gracefully — an
unconfigured feature simply stays off; nothing else breaks.

### Core (always available)

| Feature | Command | Needs |
|---|---|---|
| Vault scaffolding & onboarding | `atlas init` | — |
| Setup validation | `atlas doctor` | — |
| Auto-commit the vault | `atlas commit` | git |
| Vault changelog | `atlas changelog` | git |
| Frontmatter schemas | `atlas schemas` | — |
| Health probe | `atlas health` | — |
| Skills catalog | `atlas skills` | — |
| Audit trail | `atlas audit` | — |

Core install: `pip install -e .` (or `uv tool install …`). No extra deps, no
network, no secrets.

### Optional (opt-in, each isolated)

| Feature | Command | Extra deps | Extra env vars |
|---|---|---|---|
| **Embeddings / RAG** | `atlas embed`, `atlas graph` | `pdfplumber` *(only for PDF notes — `pip install ".[pdf]"`)* | `EMBED_HOST`, `EMBED_PORT`, `EMBED_MODEL` (+ a running local LLM) |
| **Trading research** | `atlas trading` | `yfinance` + the third-party TradingAgents package — `pip install ".[trading]"` | `LM_STUDIO_HOST`, `LM_STUDIO_PORT`, `LM_STUDIO_MODEL`, `TRADING_AGENTS_PATH`, `TRADING_TICKERS` |
| **Email reports** | `atlas email` | — (stdlib `smtplib`) | `SENDER_EMAIL`, `SMTP_APP_PASSWORD`, `SMTP_SERVER`, `SMTP_PORT`, `USER_EMAIL` |
| **LLM backend** (LM Studio / Ollama / llama.cpp / OpenAI-compatible) | `atlas backends`, backs RAG + trading | — | auto-detected; `ATLAS_LLM_BACKEND`, `ATLAS_LLM_MODEL`, `*_URL`, `EMBED_*` / `LM_STUDIO_*` |
| **Dashboard** | static HTML | — (Node.js only if you build the full app) | `DASHBOARD_FRONTEND_PORT`, `DASHBOARD_BACKEND_PORT` |

Install all optional Python extras at once: `pip install -e ".[all]"`.

Every command validates its required env vars up front and exits with a clear
message if something is missing — run `atlas doctor` any time to see which
features are currently live. Full variable reference:
[`CONFIGURATION.md`](CONFIGURATION.md).

## Prerequisites

- **Claude Cowork** subscription (for skills, scheduled tasks, memory)
- **Python 3.11+** (3.13 recommended)
- **Git**
- A **markdown vault** — a folder of `.md` notes (Obsidian optional but nice)
- *(Optional)* A **local LLM** exposing an OpenAI-compatible API for embeddings
  and chat — e.g. [LM Studio](https://lmstudio.ai/) or
  [Ollama](https://ollama.com/). Without it, RAG and trading features are off,
  but the vault, schemas, git, and reporting still work.
- *(Optional)* **Node.js** if you build the full dashboard.

## Option A — install the package (recommended)

The fastest path. Installs a global `atlas` command and walks you through setup.

```bash
uv tool install "git+https://github.com/paulholland511/atlas-os"
#   or:  pipx install "git+https://github.com/paulholland511/atlas-os"
#   trading/PDF extras:  uv tool install "atlas-os[trading,pdf] @ git+https://github.com/paulholland511/atlas-os"

atlas init        # detect your LLM, write .env, scaffold the vault, init git
atlas doctor      # verify
```

`atlas init` is interactive (auto-detects LM Studio / Ollama on the usual ports,
prompts for your vault path, and optionally configures email). Use `atlas init
--yes` for a non-interactive run with defaults, `--vault PATH` to set the vault
without prompting, and `--force` to overwrite an existing `.env`.

Then jump to [step 6](#6-build-the-rag-index-requires-a-local-llm) to build the
index. The CLI auto-loads `.env`, so you can skip the manual `source` steps
below.

## Option B — run from a source checkout

### 1. Clone

```bash
git clone https://github.com/paulholland511/atlas-os.git ~/code/atlas-os
cd ~/code/atlas-os
```

### 2. Python environment

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .                  # installs the `atlas` CLI + core deps
pip install -e ".[trading,pdf]"   # optional extras
```

> On Python 3.14 the editable `atlas` console script can be flaky; if so, use
> `python -m atlas_os <command>`, which always works from the checkout.

### 3. Configure

```bash
atlas init        # the easy way — writes .env for you
# — or by hand —
cp .env.example .env && $EDITOR .env
```

Set at minimum `VAULT_PATH`. If you have a local LLM, set `EMBED_HOST`/
`EMBED_PORT`/`EMBED_MODEL`. For email reports set `SENDER_EMAIL`,
`USER_EMAIL`, and `SMTP_APP_PASSWORD`. Full reference:
[`CONFIGURATION.md`](CONFIGURATION.md).

If you wrote `.env` by hand, load it into your shell (or use `direnv`):

```bash
set -a; source .env; set +a
```

## 4. Create the vault skeleton

If you're starting a fresh vault, copy the skeleton and drop the `.template`
suffixes:

```bash
mkdir -p "$VAULT_PATH/wiki"
cp templates/vault-skeleton/.claude-index.md.template   "$VAULT_PATH/.claude-index.md"
cp templates/vault-skeleton/wiki/index.md.template      "$VAULT_PATH/wiki/index.md"
cp templates/vault-skeleton/wiki/hot.md.template        "$VAULT_PATH/wiki/hot.md"
cp templates/vault-skeleton/wiki/log.md.template        "$VAULT_PATH/wiki/log.md"
cp "templates/vault-skeleton/Operations Dashboard.md"   "$VAULT_PATH/"
```

Initialise git in the vault so the commit/changelog tasks work:

```bash
cd "$VAULT_PATH" && git init && git add -A && git commit -m "Initialise vault"
cd -
```

> Add a `.gitignore` inside your vault for anything personal you don't want in
> its own history (the public Atlas OS `.gitignore` does not cover your private
> vault repo).

## 5. Frontmatter schemas (optional but recommended)

```bash
atlas schemas --dry-run     # preview   (or: python3 schemas/enforce_schemas.py --dry-run)
atlas schemas               # apply
```

## 6. Build the RAG index (requires a local LLM)

```bash
atlas embed --test 5        # smoke test on 5 files
atlas embed --full          # full index (also rebuilds the graph)
```

## 7. Install the CLAUDE.md and memory

```bash
cp templates/CLAUDE.md.template ~/CLAUDE.md        # then edit placeholders
# Memory lives wherever your Claude memory directory is:
cp templates/memory-structure/MEMORY.md.template <your-memory-dir>/MEMORY.md
```

## 8. Install the scheduled tasks

Copy each skill folder into your Claude scheduled-tasks directory and replace
the `{{PLACEHOLDER}}` tokens with your real values. See
[`SCHEDULED-TASKS.md`](SCHEDULED-TASKS.md) for suggested cadences and the full
placeholder list.

`atlas init` already wrote a **`Skills Catalog.md`** into your vault so agents can
discover what's available. Refresh it any time you add or change a skill:

```bash
atlas skills          # list the catalog
atlas skills --sync   # regenerate the catalog note in the vault
```

## 9. LLM backend configuration

Atlas OS speaks the OpenAI-compatible API, so it works with whatever local LLM
server you already run. It **auto-detects** a backend by probing these in order:

| Order | Backend | Default base URL | URL override env var |
|---|---|---|---|
| 1 | LM Studio | `http://localhost:5555` | `LM_STUDIO_URL` |
| 2 | Ollama | `http://localhost:11434` | `OLLAMA_URL` |
| 3 | llama.cpp | `http://localhost:8080` | `LLAMACPP_URL` |
| 4 | OpenAI-compatible | *(none — opt in)* | `OPENAI_COMPATIBLE_URL` |

Inspect and test what's detected:

```bash
atlas backends         # list every backend with reachable/unreachable + models
atlas backends test    # run a one-line inference against the active backend
```

**Forcing a backend.** To skip detection, set `ATLAS_LLM_BACKEND` to one of
`lmstudio`, `ollama`, `llamacpp`, or `openai-compatible`. Override the chat model
name with `ATLAS_LLM_MODEL`.

```bash
# Example: force Ollama and pick a specific model
export ATLAS_LLM_BACKEND=ollama
export ATLAS_LLM_MODEL=llama3.1
atlas backends test
```

**Backward compatibility.** Explicit `EMBED_*` and `LM_STUDIO_*` variables always
take precedence over auto-detection, so an existing LM Studio setup keeps working
unchanged. Auto-detection only kicks in when no endpoint is configured.

## 10. Verify

```bash
atlas doctor      # quick setup validation (OK / WARN / FAIL)
atlas health      # full subsystem probe   (or: python3 scripts/health_check.py)
```

You should see each subsystem report UP / DEGRADED / DOWN.

## 11. The audit trail

Every autonomous action Atlas runs — `embed`, `commit`, `graph`, `changelog`,
`health`, `trading`, `email` — appends one line to an **append-only** JSONL log.
This gives you a queryable record of what ran, how it was triggered, the
outcome, how long it took, what changed, and why. No setup is required; the log
is created on first write.

**Where it lives.** `$ATLAS_AUDIT_PATH` if you set it, otherwise
`$VAULT_PATH/.atlas/audit.jsonl`. The file auto-rotates at 10 MB
(`audit.jsonl.1`, `.2`, …), and appends are guarded by an OS-level file lock so
concurrent `atlas` runs never corrupt a line.

```bash
atlas audit show                       # recent entries (default last 20)
atlas audit show --action commit --since 7d
atlas audit tail                       # last 5, compact
atlas audit export --format csv -o audit-report.csv   # for compliance
```

**Trigger tagging for scheduled tasks.** Interactive runs are tagged
`trigger: cli`. So unattended runs are distinguishable, set
`ATLAS_TRIGGER=scheduled` in the environment of your scheduled tasks (or
`manual` for one-off scripted runs):

```bash
ATLAS_TRIGGER=scheduled atlas commit   # logged as a scheduled action
```

The audit trail supports ISO 27001 control A.12.4 (logging & monitoring) — see
[`../SECURITY.md`](../SECURITY.md).

## Run in Docker (optional)

If you'd rather not install Python tooling on the host, run the CLI in a
container. The image packages the `atlas` command and the pipeline scripts; your
vault is bind-mounted and secrets load from `.env`.

```bash
cp .env.example .env && $EDITOR .env     # set EMBED_HOST=host.docker.internal for a host LLM
docker build -t atlas-os .               # add --build-arg EXTRAS=".[all]" for trading/pdf

# one-shot commands (vault path comes from $VAULT_PATH or the compose default):
VAULT_PATH=~/Documents/Obsidian/MyVault docker compose run --rm atlas doctor
VAULT_PATH=~/Documents/Obsidian/MyVault docker compose run --rm atlas embed --full
```

The image is Python 3.11-slim + git only. See the root [`Dockerfile`](../Dockerfile)
and [`docker-compose.yml`](../docker-compose.yml).

## Troubleshooting

- **"VAULT_PATH environment variable is not set"** — you didn't export `.env`.
- **Embeddings unreachable** — confirm your local LLM is running and
  `EMBED_HOST:EMBED_PORT` is correct; `curl http://$EMBED_HOST:$EMBED_PORT/v1/models`.
- **Email fails** — for Gmail you need an app password (2FA required), set as
  `SMTP_APP_PASSWORD`. Regular account passwords won't work.
