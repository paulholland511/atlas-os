```
       _   _   _              ___  ____
      / \ | |_| | __ _ ___   / _ \/ ___|
     / _ \| __| |/ _` / __| | | | \___ \
    / ___ \ |_| | (_| \__ \ | |_| |___) |
   /_/   \_\__|_|\__,_|___/  \___/|____/

   Turn your Obsidian vault into a searchable AI knowledge base.
   Local LLMs · hybrid RAG search · web dashboard · 160+ skills.
   A personal AI operating system that remembers everything · works while you sleep.
```

# Atlas OS

> **Turn your Obsidian vault into a searchable AI knowledge base** — with local
> LLMs, hybrid RAG search, a web dashboard, and 160+ skills. Atlas OS is a
> personal AI operating system that remembers everything and works while you
> sleep.

[![CI](https://img.shields.io/github/actions/workflow/status/paulholland511/atlas-os/ci.yml?branch=main&label=CI)](https://github.com/paulholland511/atlas-os/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![GitHub stars](https://img.shields.io/github/stars/paulholland511/atlas-os?style=flat)](https://github.com/paulholland511/atlas-os/stargazers)
[![Last commit](https://img.shields.io/github/last-commit/paulholland511/atlas-os)](https://github.com/paulholland511/atlas-os/commits/main)
[![Local-first](https://img.shields.io/badge/privacy-local--first-success.svg)](docs/DATA-CLASSIFICATION.md)
[![No telemetry](https://img.shields.io/badge/telemetry-none-brightgreen.svg)](SECURITY.md)
[![Docs](https://img.shields.io/badge/docs-complete-informational.svg)](docs/README.md)

![Atlas OS demo](demo.gif)

### ✅ Already built and shipping

Everything below is **in the box today** — not roadmap, not "coming soon":

- 🔍 **Hybrid RAG search** — BM25 keyword + vector semantic search over your whole vault, fused into one ranked result set
- 📓 **Obsidian vault integration** — point Atlas at your markdown vault and it becomes a searchable, AI-aware second brain
- 💾 **Session capture** — every Cowork conversation saved to your vault twice daily
- 🔌 **Local LLM backends** — auto-detects Ollama, LM Studio, llama.cpp, or any OpenAI-compatible endpoint; nothing leaves your machine
- 📊 **Web dashboard** (`atlas dashboard`) — seven live panels: health, audit, tasks, skills, knowledge graph, vectors, RAG search
- 🕸️ **Visual knowledge graph** — interactive D3 view of how your notes connect (`atlas graph --open`)
- 🧙 **Interactive setup wizard** (`atlas init`) — zero to running in 5 minutes
- 📋 **Audit trail** — append-only JSONL logging every autonomous action (ISO 27001 aligned)
- 🐳 **Docker support** — `Dockerfile` + `docker-compose.yml` included
- 🩺 **Smart diagnostics** — `atlas doctor --fix` detects and repairs issues automatically
- ✅ **400+ automated tests** with CI/CD on every push
- 📚 **160+ skills catalogue** with one-command `atlas skills install-pack`
- 🛒 **Skills marketplace** — search, publish, and install community skills (`atlas skills search` / `publish` / `registry`)

---

**Atlas OS** turns [Claude Cowork](https://claude.ai/) into a personal,
local-first operating system over a markdown knowledge vault. It gives you a
searchable second brain, scheduled autonomous agents, automatic git history, and
a set of report/research workflows — all configured through environment
variables and runnable entirely on your own machine.

Crucially, **everything you discuss with Claude gets captured into your vault** —
conversations, research, code sessions, decisions. Nothing is lost between
sessions. Your vault becomes a complete, searchable record of your AI-assisted
work that gets smarter the more you use it.

It ships with **no personal data, no credentials, and no PII**. Everything is a
template you point at your own vault, your own local LLM, and your own email
account.

> **Privacy by default.** Your notes and embeddings never leave your machine
> unless *you* explicitly wire up an external endpoint. See
> [`SECURITY.md`](SECURITY.md) and
> [`docs/DATA-CLASSIFICATION.md`](docs/DATA-CLASSIFICATION.md).

---

## Table of contents

- [Quick start](#quick-start)
- [Tutorial](#tutorial)
- [Why Atlas OS](#why-atlas-os)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Dependencies](#dependencies)
- [First run (walkthrough)](#first-run-walkthrough)
- [The `atlas` CLI](#the-atlas-cli)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [The knowledge vault](#the-knowledge-vault)
- [Session capture & knowledge persistence](#session-capture--knowledge-persistence)
- [RAG search & knowledge graph](#rag-search--knowledge-graph)
- [Scheduled tasks & the skills catalog](#scheduled-tasks--the-skills-catalog)
- [Trading research SDK (optional)](#trading-research-sdk-optional)
- [Email reports](#email-reports)
- [Dashboard (optional)](#dashboard-optional)
- [Audit trail](#audit-trail)
- [Security & privacy](#security--privacy)
- [Repository layout](#repository-layout)
- [Documentation](#documentation)
- [Troubleshooting](#troubleshooting)
- [Frequently asked](#frequently-asked)
- [Roadmap](#roadmap)
- [Development & testing](#development--testing)
- [Contributing](#contributing)
- [License & disclaimer](#license--disclaimer)

---

## Quick start

New here? Get a working setup in **5 minutes** — clone, set three env vars,
scaffold a vault, and run your first task:

👉 **[docs/QUICKSTART.md](docs/QUICKSTART.md)**

**Install** — clone, create a venv, install the `atlas` CLI:

![Installing Atlas OS](install.gif)

```bash
git clone https://github.com/paulholland511/atlas-os.git && cd atlas-os
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
```

**Set up** — configure and scaffold your vault with the interactive wizard:

![Setting up Atlas OS](setup.gif)

```bash
cp .env.example .env          # set VAULT_PATH, USER_EMAIL, SMTP_APP_PASSWORD
atlas init --yes              # scaffold + git-init your vault
atlas doctor                  # verify
```

For step-by-step integration walkthroughs (Gmail SMTP, LM Studio, first
scheduled task, first RAG embed) see **[docs/EXAMPLES.md](docs/EXAMPLES.md)**.

---

## Tutorial

Want the full guided walkthrough instead of the 5-minute sprint? **[Your first 24
hours with Atlas OS](docs/TUTORIAL.md)** takes a brand-new user from
`pip install atlas-os` to an autonomous system — install & init, your first
vault and commit, building the RAG vector store and knowledge graph, scheduling
your first nightly task, wiring up email reports, and reading the audit trail the
next morning. No prior knowledge of Obsidian, RAG, or embeddings assumed.

👉 **[docs/TUTORIAL.md](docs/TUTORIAL.md)**

---

## Why Atlas OS

Out of the box, Claude is a brilliant but **stateless** assistant: it forgets
everything between sessions, can't act while you're away, and knows nothing about
the work you did last week. Atlas OS is the configuration layer that fixes that —
it turns Claude Cowork into a **persistent, autonomous, knowledge-aware operating
system** that runs on your own machine.

You don't get another chatbot. You get an assistant that *remembers, retrieves,
and acts on its own*.

### Stock Claude forgets. Atlas OS remembers everything.

The single biggest difference Atlas OS makes is **knowledge persistence**:

- **Stock Claude forgets everything between sessions.** Close the tab and the
  context is gone — last week's research, yesterday's planning discussion, the
  reasoning behind a decision.
- **Atlas OS captures every conversation automatically.** Twice a day (by
  default), every Cowork session is folded back into your vault as a searchable
  note — the summary, the key actions taken, and the files touched.
- **Your vault becomes a searchable, RAG-indexed knowledge base of everything
  you've ever discussed with Claude.** Research sessions, code reviews, planning
  discussions, debugging threads — all retrievable months later by meaning, not
  just keyword.
- **Research done via the deep-research skills gets embedded alongside your
  conversations.** `deep-research`, `autoresearch`, and `topic-research-brief`
  all write their findings into the vault, where the RAG pipeline indexes them
  into the same knowledge graph as your chats.
- **Over time, your vault gets smarter** because it holds the full context of
  your work. Every captured session and every embedded research brief sharpens
  what Claude can retrieve and reason over the next time you ask.

The result: nothing you do with Claude is ever lost. Your vault is the
institutional memory of your AI-assisted work.

### What Atlas OS actually sets up

A single `atlas init` wires Claude into a coherent system:

- **Automatic session capture** — every conversation you have in Cowork is
  saved back into your vault as a searchable note (twice daily by default), so
  research, code sessions, planning, and decisions are preserved permanently
  rather than lost when the tab closes.
- **Persistent memory across sessions** — a structured memory store and a
  git-tracked markdown vault, so Claude carries context forward instead of
  starting cold every time.
- **A knowledge base that grows smarter over time** — a local RAG pipeline
  (chunk → embed → hybrid vector+keyword search) plus a `[[wikilink]]` knowledge
  graph, so every note you add makes retrieval sharper.
- **Automated vault management** — frontmatter schemas kept consistent
  automatically and auto-commits with a categorised git history, so your second
  brain stays tidy without you curating it.
- **Scheduled tasks that run autonomously** — nightly indexing, morning
  briefings, daily reports, weekly health checks — Claude Cowork *skills* that
  fire on a cadence and do real work while you're away.
- **Multi-agent orchestration** — a self-updating skills catalog and a
  dependency-light multi-agent research framework, so agents can discover and
  invoke every automation you've configured. A
  [**catalogue of 160+ skills**](docs/SKILLS-CATALOGUE.md) (149 capability skills
  across 7 domains, plus the Atlas-native and scheduled automations) documents
  the full menu, and the [**skills framework**](docs/SKILLS-FRAMEWORK.md) shows
  how to author your own.
- **Local LLM integration** — embeddings and inference run against your own
  LM Studio / Ollama / llama.cpp endpoint by default; nothing leaves the box
  unless you wire it up yourself.
- **Voice, trading, and email automation** *(optional)* — TTS health hooks,
  a local-first market-research SDK that writes briefings into your vault, and a
  credential-free SMTP sender that emails you reports on schedule.
- **An append-only audit trail** — every autonomous action (embed, commit,
  email, trading, …) is logged to a tamper-evident JSONL trail recording what
  ran, how it was triggered, the outcome, duration, and what changed — queryable
  and exportable to CSV for compliance.

### What you get

- **A Claude that remembers everything** — past decisions, projects, and context
  are one search away, not lost to the last session boundary. Every conversation
  and research session is captured into the vault automatically and indexed for
  RAG search, so months later you can ask "what did we decide about X?" and get
  the real answer.
- **Daily operations that run themselves** — wake up to an indexed vault, a
  committed history, and a briefing in your inbox, all done overnight.
- **A professional-grade AI assistant that runs locally** — your notes,
  embeddings, and knowledge graph stay on your disk; the only external calls are
  ones you explicitly enable. No telemetry, ever.
- **Total transparency** — the "database" is a folder of markdown, the "API" is
  a set of small inspectable Python scripts, and history is plain git. Everything
  is diffable, portable, auditable, and yours.
- **A full audit trail of what Claude did** — every autonomous action appends to
  an append-only log (`atlas audit show`), so you can answer "what ran overnight,
  why, and what did it change?" and export the record for compliance.

The unit of work is a *skill* — a Claude Cowork prompt that runs on a schedule
and orchestrates the Python tooling below. That's the difference between *chatting
with your notes* and *running an operating system over them*.

---

## Features

Twelve composable systems, each usable on its own:

1. **Session capture** — every Cowork conversation is automatically saved back
   into your vault as a searchable session log (twice daily by default).
   Research, code reviews, planning, and decisions are preserved permanently and
   RAG-indexed alongside your notes — nothing discussed with Claude is ever lost.
   See [session capture](#session-capture--knowledge-persistence).
2. **Knowledge vault** — a folder of markdown notes (Obsidian-friendly) where
   top-level folders carry meaning and per-folder YAML frontmatter is kept
   consistent automatically. See [the vault](#the-knowledge-vault).
3. **Local RAG search** — semantic-chunk + embed your notes via a local LLM into
   a SQLite vector store (`.rag/vectors.db`, `sqlite-vec`-accelerated with a
   pure-Python fallback). **Hybrid** retrieval fuses BM25 + vector ranking and
   reranks the result; query it with `atlas search`. See
   [RAG search](#rag-search--knowledge-graph).
4. **Pluggable LLM backends** — bring whatever OpenAI-compatible server you run.
   Atlas OS auto-detects LM Studio, Ollama, llama.cpp, or any custom endpoint
   (probed in that order), with `ATLAS_LLM_BACKEND` to force one. Inspect with
   `atlas backends` / `atlas backends test`.
5. **Knowledge graph** — a wikilink (`[[note]]`) graph with nodes, edges,
   adjacency, and backlinks for "related notes", plus an interactive **D3
   force-directed viewer** (`atlas graph --open`, or the dashboard's `/graph`
   page) — zoom, pan, search, filter by note type, and click through links and
   backlinks.
6. **Git automation** — auto-commit the vault with messages categorised by which
   folders changed, and generate changelogs for a morning briefing.
7. **Scheduled tasks, skills catalog & marketplace** — nightly indexing, daily
   reports, weekly health checks and more, as Claude Cowork skills — plus a
   self-updating `Skills Catalog.md` in the vault so agents can discover every
   automation they can invoke, and a **skills marketplace** (`atlas skills
   search` / `publish` / `registry`) for sharing and installing community skills
   from JSON registries with dependency resolution.
8. **Email reports** — a credential-free SMTP sender for status reports and
   newsletters (password from the environment, never hardcoded).
9. **Trading research SDK** *(optional)* — a dependency-light multi-agent
   market-research framework that writes briefings into your vault.
   *Not financial advice.*
10. **Web dashboard** *(optional)* — a local-first Flask web UI (`atlas
   dashboard`) with seven live panels (system health, audit trail, scheduled
   tasks, skills, knowledge graph, vector-store stats, RAG search), reading from
   the same modules the CLI uses. Plus a static, single-file ops dashboard for
   embedding in your own page. See [the dashboard](#dashboard-optional).
11. **Voice / TTS hooks** *(optional)* — health-check probes for a local TTS
   service.
12. **Audit trail / logging** — append-only JSONL logging of every autonomous
   action (what ran, how it was triggered, the outcome, duration, and what
   changed), with `atlas audit show / tail / export` for inspection and CSV
   compliance reports. ISO 27001 aligned (A.12.4).

> **How does each one work?** Every feature has a deep-dive doc (internals, data
> formats, config) in [`docs/features/`](docs/features/README.md) — e.g.
> [how RAG works](docs/features/rag-search.md),
> [how trading works](docs/features/trading-sdk.md),
> [the knowledge graph](docs/features/knowledge-graph.md).

---

## Prerequisites

| Requirement | Needed for | Notes |
|---|---|---|
| **Python 3.11+** (3.13 recommended) | everything | the CLI and scripts |
| **Git** | vault history, changelog | your vault becomes its own git repo |
| A **markdown vault** | everything | any folder of `.md` files; Obsidian optional |
| **[uv](https://docs.astral.sh/uv/)** or **[pipx](https://pipx.pypa.io/)** | easy install | recommended way to install the `atlas` command |
| **Claude Cowork** subscription | skills, scheduled tasks, memory | the Python tooling runs standalone without it |
| A **local LLM** (OpenAI-compatible) | RAG search, trading module | [LM Studio](https://lmstudio.ai/), [Ollama](https://ollama.com/), llama.cpp, … |
| **Node.js** | the *full* dashboard only | the bundled static dashboard needs nothing |

> Without a local LLM, the vault, frontmatter schemas, git automation,
> changelog, email, and health check all still work — only RAG and trading need
> an embeddings/chat endpoint.

**Getting a local LLM (example, LM Studio):** install it, download an embeddings
model (e.g. `nomic-embed-text`) and a chat model, then start its local server
(default `http://localhost:1234`). `atlas init` auto-detects it. For Ollama:
`ollama serve` then `ollama pull nomic-embed-text`.

Atlas OS works with **any** OpenAI-compatible server. It auto-detects LM Studio,
Ollama, llama.cpp, or a custom endpoint (probed in that order) — run
`atlas backends` to see what's reachable and `atlas backends test` to confirm
inference. Force a specific one with `ATLAS_LLM_BACKEND=ollama`.

---

## Installation

### Recommended — install the `atlas` command

[Atlas OS is on PyPI](https://pypi.org/project/atlas-os/) — install it directly:

```bash
# uv (fast, isolated):
uv tool install atlas-os

# …or pipx:
pipx install atlas-os

# …or pip:
pip install atlas-os
```

> **Automated releases.** Each `v*` tag builds, tests, and publishes to PyPI via
> GitHub Actions + [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
> (OIDC, no stored token). To track `main` ahead of a release, install from git:
> `uv tool install "git+https://github.com/paulholland511/atlas-os"`. See
> [`docs/PUBLISHING.md`](docs/PUBLISHING.md) for the release runbook.

**With optional extras** (trading needs `yfinance`, PDF embedding needs
`pdfplumber`, the web dashboard needs `flask`):

```bash
uv tool install "atlas-os[dashboard,trading,pdf]"
# extras: [dashboard]  [trading]  [pdf]  [vector]  [all]
```

### From a source checkout (for development)

```bash
git clone https://github.com/paulholland511/atlas-os.git ~/code/atlas-os
cd ~/code/atlas-os
python3 -m venv .venv && source .venv/bin/activate
pip install -e .                 # installs the `atlas` CLI + core deps
pip install -e ".[trading,pdf]"  # optional extras
```

> On Python 3.14 the editable console script can be flaky; if `atlas` doesn't
> resolve, use `python -m atlas_os <command>`, which always works from a
> checkout. (On macOS this happens when the checkout lives in an iCloud-synced
> folder: iCloud sets the `hidden` flag on the editable `.pth`, and Python 3.13+
> skips hidden `.pth` files. Fix it with
> `chflags nohidden .venv/lib/python*/site-packages/*.pth`, or keep the venv
> outside iCloud.)

### No install at all (run the scripts directly)

```bash
git clone https://github.com/paulholland511/atlas-os.git ~/code/atlas-os
cd ~/code/atlas-os
python3 -m venv .venv && source .venv/bin/activate
pip install requests pyyaml pdfplumber
cp .env.example .env && $EDITOR .env     # at minimum set VAULT_PATH
set -a; source .env; set +a
python3 scripts/health_check.py
```

### Or run in Docker (no host Python)

```bash
docker build -t atlas-os .      # add --build-arg EXTRAS=".[all]" for trading/pdf
VAULT_PATH=~/Documents/Obsidian/MyVault docker compose run --rm atlas doctor
```

Full details in the [Docker section](#docker-optional) below.

### Updating / uninstalling

```bash
uv tool upgrade atlas-os        # or: pipx upgrade atlas-os
uv tool uninstall atlas-os      # or: pipx uninstall atlas-os
```

---

## Dependencies

Atlas OS is deliberately dependency-light. The full, pinned list lives in
[`requirements.txt`](requirements.txt):

```bash
pip install -r requirements.txt      # core, pinned to tested versions
# or, via the packaged extras:
pip install ".[trading,pdf]"
```

| Package | Pin | Needed for |
|---|---|---|
| `requests` | `2.34.2` | HTTP — embeddings, chat, SMTP probes, trading APIs (**core**) |
| `pyyaml` | `6.0.3` | frontmatter parsing / schema enforcement (**core**) |
| `typer` | `0.26.6` | the `atlas` CLI (**core**) |
| `python-dotenv` | `1.2.2` | auto-loading `.env` (**core**) |
| `yfinance` | `1.4.1` | market data — trading SDK *(optional `[trading]`)* |
| `pdfplumber` | `0.11.9` | PDF text extraction for RAG *(optional `[pdf]`)* |
| `anthropic` | `0.105.2` | the opt-in cloud trading step only *(optional)* |

Everything else (numpy, pandas, certifi, …) is a transitive dependency resolved
automatically — Atlas OS imports none of it directly.

---

## First run (walkthrough)

```bash
atlas init       # guided onboarding (interactive)
atlas doctor     # validate the setup
atlas embed --full   # build the RAG index (needs a local LLM)
atlas health     # full subsystem report
```

**`atlas init`** will:

1. ask for your **vault path** (default `~/Documents/Obsidian/MyVault`);
2. **probe for a local LLM** on the common ports (LM Studio `1234`, generic
   `5555`, Ollama `11434`) and wire up the embeddings/chat host, port, and an
   embeddings model if one is detected;
3. optionally **configure email** (sender, SMTP server/port, app password,
   recipient);
4. write a commented **`.env`**;
5. **scaffold the vault skeleton** (`.claude-index.md`, `wiki/index.md`,
   `wiki/hot.md`, `wiki/log.md`, `Operations Dashboard.md`);
6. **generate `Skills Catalog.md`** so agents can discover your skills;
7. **`git init`** the vault and make the first commit;
8. optionally install the `CLAUDE.md` template to your home directory.

Flags: `--vault PATH` (skip the prompt), `--yes` (non-interactive, accept
defaults), `--force` (overwrite an existing `.env`).

**`atlas doctor`** reports OK / WARN / FAIL for Python, the vault (exists + git),
the RAG index, the embeddings endpoint, and SMTP — and exits non-zero if
anything is FAIL. Run **`atlas doctor --fix`** and it repairs what it safely can
(clearing stale locks, initialising the vault's git repo, re-running the setup
wizard for missing config) instead of just reporting. Example:

```
Atlas OS — doctor

  ✓ Python         3.13 (need ≥ 3.11)
  ✓ Vault path     /Users/you/Documents/Obsidian/MyVault
  ✓ Vault git      tracked
  ! RAG index      no vectors yet — run `atlas embed --full`
  ! Embeddings     unreachable at http://localhost:5555/v1/models (RAG disabled until it's up)
  ! Email (SMTP)   not configured (reports won't send)

3 OK · 3 WARN · 0 FAIL
```

Full walkthrough: [`docs/SETUP.md`](docs/SETUP.md).

---

## The `atlas` CLI

One command wraps the whole system. Configuration is read from the environment;
a `.env` in the current directory or repo root is **auto-loaded** — no manual
`source` needed. Every pipeline command forwards its flags straight to the
underlying script.

| Command | What it does | Key flags |
|---|---|---|
| `atlas init` | Interactive setup wizard — detect LLM, write `.env`, scaffold vault, generate the skills catalog | `--vault`, `--yes`, `--force` |
| `atlas doctor` | Smart diagnostics — validate the setup (OK / WARN / FAIL per subsystem) and optionally repair issues | `--fix` |
| `atlas skills` | List the agent skills catalog | `--sync`, `--output` |
| `atlas skills list` | List every available skill (slug + cadence) | — |
| `atlas skills show` | Print a skill's `SKILL.md` | — |
| `atlas skills install` | Install a skill into the scheduled-tasks dir, filling placeholders | `--force` |
| `atlas embed` | Build/refresh the RAG index | `--full`, `--incremental`, `--test N`, `--folder NAME`, `--pdfs-only`, `--checkpoint-interval N`, `--batch-size N` |
| `atlas graph` | Rebuild the wikilink knowledge graph, or `--open` the interactive D3 viewer | `--open`, `--host`, `--port`, `--no-build`, `--json` |
| `atlas commit` | Auto-commit the vault with a categorised message | `--dry-run`, `--json` |
| `atlas changelog` | Summarise vault changes over a window | `--since`, `--markdown`, `--json` |
| `atlas health` | Full subsystem health probe | `--json`, `--quiet` |
| `atlas trading` | Generate a trading research briefing *(optional)* | `--ticker`, `--date`, `--dry-run` |
| `atlas email` | Send an email via SMTP | `--to`, `--subject`, `--body`, `--text`, `--attach`, `--json` |
| `atlas schemas` | Enforce per-folder frontmatter schemas | `--dry-run`, `--folder`, `--verbose` |
| `atlas session save` | Save Cowork chat transcripts to the vault as session logs | `--since`, `--all`, `--sessions-dir`, `--json` |
| `atlas session list` | List recent Cowork sessions with dates and titles | `--limit`, `--sessions-dir`, `--json` |
| `atlas audit show` | Show recent audit-trail entries | `--limit`, `--action`, `--since` |
| `atlas audit tail` | Last 5 audit entries, compact | — |
| `atlas audit export` | Export the audit log for compliance | `--format csv\|json`, `--output`, `--action`, `--since` |

```bash
# examples
atlas embed --incremental                 # embed only changed notes
atlas embed --test 5                       # smoke-test the endpoint on 5 files
atlas changelog --since "7 days ago" --markdown
atlas commit --dry-run
atlas skills list                          # every installable skill
atlas skills install atlas-daily-report-email   # deploy one, filling placeholders
atlas skills --sync                        # regenerate Skills Catalog.md
atlas email -s "Hi" -b "<p>Hello</p>" --to me@example.com
atlas email --json '{"to":"me@example.com","subject":"Hi","body_html":"<p>Hi</p>"}'
atlas audit show --action commit --since 7d
atlas audit export --format csv -o audit-report.csv
```

Every command auto-loads `.env` and **validates its required env vars up front**,
exiting with a clear message (and a non-zero code) if something is missing — so a
half-configured optional feature fails fast instead of part-way through.

Run `atlas --help` or `atlas <command> --help` for details. Complete per-command
reference — flags, env vars consumed, exit codes, and the v1.0 stability
contract: [`docs/CLI-REFERENCE.md`](docs/CLI-REFERENCE.md). The underlying scripts
are documented in [`docs/SCRIPTS.md`](docs/SCRIPTS.md).

> `atlas init`, `atlas doctor`, `atlas skills`, and `atlas audit` are CLI-only.
> The rest map 1:1 to scripts in `scripts/` (and `schemas/`), so you can also run
> them directly, e.g. `python3 scripts/embed_vault.py --full`. Every script
> command also appends an entry to the [audit trail](#audit-trail).

---

## Configuration

All configuration is via **environment variables** — there are no hardcoded
paths, hosts, emails, or secrets anywhere in the repo. Copy
[`.env.example`](.env.example) to `.env` (or let `atlas init` write it). The CLI
auto-loads `.env`; if you run scripts directly, `set -a; source .env; set +a`.

| Variable | Required? | Default | Used by |
|---|---|---|---|
| `VAULT_PATH` | **Yes** | `.` | all scripts |
| `RAG_DIR` | No | `$VAULT_PATH/.rag` | embed, graph, health |
| `SCHEDULED_DIR` | No | `~/Documents/Claude/Scheduled` | health |
| `ATLAS_SKILLS_DIR` | No | `$VAULT_PATH/.claude/skills` | `atlas skills install` |
| `EMBED_HOST` / `EMBED_PORT` | No | `localhost` / `5555` | embed, health |
| `EMBED_MODEL` | No | `text-embedding-nomic-embed-text-v1.5` | embed |
| `EMBED_URL` | No | `http://$EMBED_HOST:$EMBED_PORT/v1/embeddings` | embed |
| `EMBED_API_KEY` | No | `""` | embed |
| `LM_STUDIO_HOST` / `LM_STUDIO_PORT` | No | `localhost` / `5555` | trading |
| `LM_STUDIO_MODEL` | No | `local-model` | trading |
| `LM_STUDIO_URL` | No | `…:$PORT/v1` | `trading_briefing.py` (needs `/v1`) |
| `LM_STUDIO_ENDPOINT` | No | `…:$PORT` | `trading/config.py` (no `/v1`) |
| `TTS_HOST` / `TTS_PORT` | No | `localhost` / `8800` | health |
| `SENDER_EMAIL` | **Yes** (email) | `""` | email |
| `SENDER_NAME` | No | `Atlas` | email |
| `SMTP_SERVER` / `SMTP_PORT` | No | `smtp.gmail.com` / `587` | email |
| `SMTP_APP_PASSWORD` | **Yes** (email) | `""` | email, health |
| `USER_EMAIL` | No | — | scheduled tasks |
| `DASHBOARD_FRONTEND_PORT` / `DASHBOARD_BACKEND_PORT` | No | `3000` / `5001` | health |
| `TRADING_AGENTS_PATH` | No | `~/Documents/TradingAgents` | trading |
| `TRADING_TICKERS` | No | `BTC-USD,ETH-USD` | trading |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | No (opt-in) | — / `claude-opus-4-6` | trading cloud PM |
| `GITHUB_REPO` | No | — | informational |

Full reference (per-variable detail, secret handling, the `LM_STUDIO_URL` vs
`LM_STUDIO_ENDPOINT` gotcha): [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

---

## Architecture

```
                        ┌──────────────────────────────┐
                        │        Claude Cowork           │
                        │  skills · scheduled tasks ·    │
                        │  memory · MCP tools            │
                        └───────────────┬────────────────┘
                                        │ invokes
        ┌───────────────────────────────┼───────────────────────────────┐
        ▼                               ▼                               ▼
 ┌──────────────┐            ┌────────────────────┐           ┌──────────────────┐
 │  atlas CLI / │            │   Markdown vault    │           │   Local LLM       │
 │  scripts/    │◀── rw ────▶│  notes · wiki ·     │           │  embeddings +     │
 │  (Python)    │            │  memory · daily     │           │  chat (OpenAI-    │
 └──────┬───────┘            │  (git-tracked)      │           │  compatible)      │
        │                    └────────────────────┘           └─────────┬────────┘
        ▼                                                                │
 ┌──────────────┐                                                       │
 │  .rag/       │   vectors.db + graph.json  ◀──────────────────────────┘
 │  (local,     │   (SQLite store, regenerated, git-ignored)
 │  git-ignored)│
 └──────────────┘
```

- **The vault is the source of truth.** Everything in `.rag/` is derived and
  reproducible — back up the vault and your secrets; rebuild the rest.
- **Config via environment.** No paths, hosts, emails, or secrets in code.
- **Idempotent automations.** Re-running a task converges rather than
  duplicating; the hot cache is append-only.
- **Local-first.** External calls (SMTP, opt-in cloud model) are explicit.

Deep dive: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Disaster-recovery /
clean-install runbook: [`docs/REBUILD.md`](docs/REBUILD.md).

---

## The knowledge vault

A plain folder of markdown notes. Top-level folders carry meaning and drive the
frontmatter schemas. The `atlas init` skeleton gives you:

```
your-vault/
├── .claude-index.md        # master index agents read first
├── Operations Dashboard.md # at-a-glance status note
├── Skills Catalog.md        # auto-generated menu of agent skills
└── wiki/
    ├── index.md            # wiki home / coverage index
    ├── hot.md              # append-only "recently changed" cache
    └── log.md              # running activity log
```

**Frontmatter schemas.** `atlas schemas` validates each note's YAML frontmatter
against a per-folder schema and fills in missing required fields
(non-destructively — it only *adds*, inferring `date`/`title` from the
filename). Schemas ship for `research`, `projects`, `decisions`, `guides`,
`wiki`, `daily`, `memory`, `learning`, `code-solutions`, and more. Customise the
`SCHEMAS` dict to match your own layout. Full table:
[`schemas/frontmatter-schemas.md`](schemas/frontmatter-schemas.md).

---

## Session capture & knowledge persistence

This is what turns Atlas OS from "Claude with a notes folder" into a system with
a memory. **Every conversation you have in Cowork is folded back into your vault
as a searchable note** — so the record of *what was done and why* lives in your
knowledge base, not in chat transcripts that vanish when you close the tab.

```bash
atlas session list          # see your recent Cowork sessions
atlas session save --all    # write a session-log note for every session
atlas session save --since 12h   # only what's new in the last 12 hours
```

For each session, `atlas session save` writes
`$VAULT_PATH/sessions/session-log-YYYY-MM-DD-<title>.md` — frontmatter tagged
`[session-log, cowork]`, a summary, the key actions taken, and the files
modified. Everything is extracted **locally — no LLM call, nothing leaves your
machine**. A watermark in `.atlas/last_session_save.txt` means a plain
`atlas session save` only picks up what's new, so it's safe to run repeatedly.

**Captured automatically, twice a day.** The recommended default is a morning and
an afternoon capture, each covering a 12-hour window, so your work lands in the
vault close to when it happened:

```bash
atlas skills install morning-session-capture     # ~09:00, --since 12h
atlas skills install afternoon-session-capture   # ~17:00, --since 12h
```

Prefer a single nightly run? Install `daily-session-capture` (`--since 24h`)
instead. Record your choice in `.env` with `SESSION_CAPTURE_FREQUENCY`
(`twice` | `daily` | `hourly` | `manual`).

**Everything gets indexed.** Because session logs land in the vault as ordinary
markdown, the nightly RAG embed picks them up automatically — your conversations
become searchable by meaning alongside your notes. And it's not just chats:
research produced by the deep-research skills is captured the same way.
`deep-research`, `autoresearch`, and `topic-research-brief` all write their
findings into the vault, where they're embedded into the **same knowledge graph**
as your conversations. Over time the vault accumulates the full context of your
AI-assisted work, and every captured session makes the next retrieval sharper.

The twice-daily pair is part of the [`knowledge` pack](docs/SCHEDULED-TASKS.md),
so `atlas skills install-pack knowledge` sets both up alongside the nightly index
and RAG embed. Full walkthrough:
[`docs/TUTORIAL.md`](docs/TUTORIAL.md#step-35--capture-your-cowork-sessions-to-the-vault).

---

## RAG search & knowledge graph

**RAG (`atlas embed`).** Notes (and optionally PDFs) are chunked (~500 tokens,
50 overlap), embedded via your local OpenAI-compatible endpoint, and stored in a
**SQLite vector store** at `$RAG_DIR/vectors.db` (see
[`atlas_os/vectordb.py`](atlas_os/vectordb.py)). Query time uses **hybrid**
retrieval (vector + keyword).

- `atlas embed --full` — re-embed everything (also rebuilds the graph).
- `atlas embed --incremental` — only files changed since the last run.
- `atlas embed --test N` — embed the first N files (connectivity check).
- `--folder NAME`, `--pdfs-only`, `--checkpoint-interval N`, `--batch-size N`.
- `atlas migrate-vectors` — convert an existing `vectors.json` → `vectors.db`
  (auto-runs on first embed, so this is only for migrating ahead of time).

The store scales past the old single-file `vectors.json`: vector search uses the
[`sqlite-vec`](https://github.com/asg017/sqlite-vec) KNN index when the
`[vector]` extra is installed (`pip install -e ".[vector]"`), and falls back to a
NumPy-accelerated cosine scan otherwise. Embeds write **incrementally** (per
file, per batch), so a full run **checkpoints** and an interrupted embed resumes
rather than starting over — and never corrupts the index with a half-written
rewrite.

**Advanced retrieval ([`atlas_os/rag.py`](atlas_os/rag.py)).** The pipeline uses
production-grade IR at every stage:

- **Semantic chunking** splits on heading/paragraph boundaries (whole paragraphs
  up to a token budget) instead of fixed character windows.
- **Hybrid search** fuses the vector ranking with an **Okapi BM25** lexical
  ranking via **Reciprocal Rank Fusion**, then **reranks** by TF-IDF cosine to
  the query.
- **Embedding cache** (keyed by `(model, text)` hash) skips re-embedding
  unchanged chunks — even across a full rebuild.
- **Metadata filtering** by folder, doc_type, tag, file type, or date window
  *before* the vector search.

**Search (`atlas search`).** Query the store from the CLI:

![RAG search from the CLI](search.gif)

```bash
atlas search "kelly criterion sizing"                 # hybrid + rerank, top 5
atlas search "trading risk" --folder research --tag trading --top-k 10
atlas search "embeddings" --mode vector --file-type md --since 30d
atlas search "kelly" --mode keyword                   # BM25 only (no endpoint)
```

**Knowledge graph (`atlas graph`).** Walks every note, resolves `[[wikilinks]]`,
and writes `$RAG_DIR/graph.json` with nodes, edges, adjacency, and backlinks —
the basis for "related notes" and the dashboard's graph view. It's rebuilt
automatically after `atlas embed --full`. Run `atlas graph --open` to launch the
interactive **D3 graph viewer** in your browser (the dashboard's `/graph` page) —
a force-directed map of your vault you can zoom, pan, search, filter by note
type, and click through note-by-note.

Both `.rag/` artifacts are **git-ignored** and never leave your machine.

---

## Scheduled tasks & the skills catalog

Automations are **Claude Cowork skills** — a `SKILL.md` prompt per task in
`skills/<name>/`. Install one with `atlas skills install <name>` — it copies the
`SKILL.md` into your scheduled-tasks directory (`$ATLAS_SKILLS_DIR`, default
`$VAULT_PATH/.claude/skills/`) and substitutes the `{{PLACEHOLDER}}` tokens from
your `.env`. Then register it on the cadence below.

| Skill | Suggested cadence | What it does |
|---|---|---|
| `nightly-obsidian-index` | Nightly (~02:00) | Index changed notes, sync the wiki, append the hot cache, commit the vault, write a morning briefing |
| `nightly-rag-incremental` | Nightly (after the index) | Embed only notes changed since the last run |
| `morning-session-capture` | Morning (~09:00) | Capture overnight/early-morning Cowork transcripts to the vault (`--since 12h`) |
| `afternoon-session-capture` | Late afternoon (~17:00–18:00) | Capture the day's Cowork transcripts to the vault (`--since 12h`) |
| `daily-session-capture` | Nightly (~23:30) | Single once-a-day alternative — save the day's Cowork transcripts (`--since 24h`) |
| `daily-job-tracker-update` | Weekday mornings | Scan email for application updates; update the tracker |
| `afternoon-job-tracker-update` | Weekday ~14:00 | Catch afternoon emails; update the tracker |
| `atlas-daily-report-email` | Daily (~09:30) | Email a status report (job search, health, action items) |
| `daily-trading-report` | Daily (~13:00) | Run analyst agents on a watchlist; email a research report |
| `friday-it-newsletter` | Fridays AM | Compile and email a weekly IT-news digest; save to the vault |
| `weekly-system-health-check` | Weekly | Probe every subsystem; email a health report |
| `weekly-rag-full-reembed` | Weekly (Sun early AM) | Re-embed the entire vault from scratch |

**The skills catalog.** Atlas OS keeps a self-updating **`Skills Catalog.md`** in
your vault — an always-current index of every skill (name, description, suggested
cadence), built from each `SKILL.md`'s frontmatter so it never drifts. Because
it carries `type: reference` frontmatter, the RAG indexer picks it up, and any
agent that reads or searches your vault can discover the full menu of automations
it can invoke.

```bash
atlas skills              # list the catalog in the terminal
atlas skills show <name>  # print a skill's SKILL.md
atlas skills install <name>   # deploy it, filling placeholders from .env
atlas skills --sync       # (re)generate Skills Catalog.md in the vault
```

`atlas init` generates it on first setup. Add your own skill by dropping a
`skills/<slug>/SKILL.md` with `name` + `description` frontmatter, then
`atlas skills --sync`. Cadences, placeholder tokens, and safety notes:
[`docs/SCHEDULED-TASKS.md`](docs/SCHEDULED-TASKS.md).

**The full skills menu.** Beyond the scheduled tasks above, Atlas OS documents a
[**catalogue of 160+ skills**](docs/SKILLS-CATALOGUE.md) — 149 capability skills
across Security, DevOps, Frontend, Backend, Quality, Data & AI, and Business, plus
the four Atlas-native skills (`autoresearch`, `save-to-vault`, `wiki-search`,
`send-email`) and the nine scheduled automations. The
[**skills framework**](docs/SKILLS-FRAMEWORK.md) explains what a skill is, the
lifecycle (creation → installation → scheduling → execution → audit logging), and
how to author your own — with a copy-paste `SKILL.md` template.

---

## Trading research SDK (optional)

> ⚠️ **Not financial advice.** A research/automation template only. It does not
> place trades, and nothing it outputs is a recommendation. You are solely
> responsible for any use. Markets are risky; you can lose money.

A small, dependency-light multi-agent framework in [`trading/`](trading/README.md).
Four analyst agents — **technical, fundamentals, sentiment, news** — produce
per-asset signals from a **local** LLM, and an optional **Portfolio Manager**
step synthesises them into a final recommendation.

```
 [Local LLM] technical + fundamentals + sentiment + news → briefing.md
                                                               │
                                                               ▼
 [Portfolio Manager] debate → final signal + confidence  → signals.json
   (local by default; Anthropic cloud opt-in)                 │
                                                               ▼
                                                  Freqtrade strategy (optional)
```

`atlas`/`scripts/trading_briefing.py` runs the analysis for your `TRADING_TICKERS`
and writes a markdown briefing into the vault (so RAG indexes it). The cloud
Portfolio Manager is **off by default** and, when enabled, sends only anonymous
analyst votes — never your notes or positions. Install extras with
`atlas-os[trading]`.

---

## Email reports

`atlas email` / `scripts/send_email.py` is a credential-free SMTP sender: the
app password comes from `SMTP_APP_PASSWORD`, the sender from `SENDER_EMAIL`,
nothing hardcoded. Use the simple flags for a quick message, or `--json` for a
full payload (`to`, `subject`, `body_html`, `body_text`, `attachments`).

```bash
atlas email -s "Report" -b "<p>…</p>" --to me@example.com
atlas email --json '{"to":"me@example.com","subject":"Report","body_html":"<p>…</p>","attachments":["/path/report.pdf"]}'
```

For Gmail, generate an [app password](https://myaccount.google.com/apppasswords)
(requires 2FA) — your normal account password won't work. The report skills call
this for you.

---

## Dashboard (optional)

A lightweight, local-first **web dashboard** ships in the box. Install the extra
and launch it:

![Atlas OS web dashboard](dashboard.gif)

```bash
pip install 'atlas-os[dashboard]'
atlas dashboard                 # serves http://127.0.0.1:8501
```

Seven panels, read live from the same modules the CLI uses (no second source of
truth): **system health** (`atlas doctor` with green/amber/red indicators), a
paginated **audit trail** browser, **scheduled tasks** with last-run status, a
**skills** manager with one-click pack installs, an interactive **knowledge
graph** (a D3 force-directed view at `/graph`, also reachable via `atlas graph
--open`), **vector-store stats** (chunks, files, DB size, last embed), and **RAG
search**. Flask + Jinja2 only — the one client-side dependency is D3, loaded by
the graph page from a CDN. Details:
[`docs/features/dashboard.md`](docs/features/dashboard.md).

Prefer to embed the data in your own page? A self-contained, single-file HTML
dashboard also ships at
[`templates/ops-dashboard.html`](templates/ops-dashboard.html); it expects two
optional local JSON endpoints you can back with a ~30-line shim:

| Endpoint | Produced by |
|---|---|
| `GET /api/health` | `atlas health --json` |
| `GET /api/changelog` | `atlas changelog --json` |

For a richer multi-panel app, build it as a **separate repo** pointed at the same
local endpoints — keep its dependencies and any cached data out of this public
repo. Details: [`dashboard/README.md`](dashboard/README.md).

---

## Docker (optional)

Prefer not to install Python tooling on the host? Run the `atlas` CLI in a
container. The image (Python 3.11-slim + git) packages the command and the
pipeline scripts; your vault is bind-mounted and secrets load from `.env`.

```bash
cp .env.example .env && $EDITOR .env      # for a host LLM: EMBED_HOST=host.docker.internal
docker build -t atlas-os .                # add --build-arg EXTRAS=".[all]" for trading/pdf

# run any subcommand against your mounted vault:
VAULT_PATH=~/Documents/Obsidian/MyVault docker compose run --rm atlas doctor
VAULT_PATH=~/Documents/Obsidian/MyVault docker compose run --rm atlas embed --full
VAULT_PATH=~/Documents/Obsidian/MyVault docker compose run --rm atlas commit --dry-run
```

A local LLM (LM Studio / Ollama) on the host is reachable from inside the
container at `host.docker.internal`. There is no long-running service to expose —
this is a CLI, so use `docker compose run` per command. See the root
[`Dockerfile`](Dockerfile) and [`docker-compose.yml`](docker-compose.yml).

> The public repo ships only the static, single-file ops dashboard
> (`templates/ops-dashboard.html`), so there's no web app to containerise — the
> image is for the CLI tooling. Keep any full dashboard in its own repo (above).

---

## Audit trail

Atlas runs work on your behalf — overnight indexing, auto-commits, scheduled
briefings, emails. The audit trail gives you a single, queryable record of every
one of those actions, so "what did Claude do last night, and why?" has a precise
answer.

Every script-wrapping command (`embed`, `commit`, `graph`, `changelog`, `session`,
`health`, `trading`, `email`) appends one JSON line to an **append-only** log
when it finishes:

```jsonl
{"timestamp":"2026-06-03T02:00:11.482+00:00","action":"commit","trigger":"scheduled","status":"success","duration_seconds":1.84,"changes":["3 new","1 modified","commit a1b9f2c"],"context":"atlas commit --json","error":null}
```

Each entry records **what** ran (`action`), **how** it was triggered (`trigger`
— `scheduled` / `manual` / `cli`), the **outcome** (`status`), how long it took,
**what changed**, **why** it ran (`context`), and any **error**. The log is
appended under an OS-level file lock (safe across concurrent `atlas` processes)
and auto-rotates at 10 MB to `audit.jsonl.1`, `.2`, ….

```bash
atlas audit show                       # recent entries (default last 20)
atlas audit show --action commit --since 7d
atlas audit tail                       # last 5, compact
atlas audit export --format csv -o audit-report.csv   # for compliance
```

- **Location:** `$ATLAS_AUDIT_PATH` if set, otherwise `$VAULT_PATH/.atlas/audit.jsonl`.
- **Trigger tagging:** scheduled tasks set `ATLAS_TRIGGER=scheduled`; interactive
  runs default to `cli`.

This logging directly supports ISO 27001 control **A.12.4 (Logging &
monitoring)** — see [SECURITY.md](SECURITY.md).

---

## Security & privacy

Atlas OS distinguishes four data classes and keeps each in its place:

| Class | Examples | Storage | Leaves device? |
|---|---|---|---|
| **Public** | this repo's code/docs/templates | the git repo | Yes — by design, no personal data |
| **Internal** | your notes, RAG vectors, graph | local disk (`VAULT_PATH`, `.rag/`) | **No** |
| **Confidential** | trackers, positions, email content | local disk, outside the repo | **No** (git-ignored) |
| **Secret** | SMTP app password, API keys | environment variables only | **No** |

- **No telemetry, no analytics, no phone-home.**
- Secrets live only in env vars; `.env` is git-ignored (only `.env.example` is
  committed). The `.gitignore` blocks PII-bearing artefacts (`*.xlsx`,
  `*.db`, `graph.json`, `*.key`, `credentials*`, …).
- The design is built to support an **ISO/IEC 27001-aligned** posture (data
  classification, secrets handling, recoverability, auditability) — an alignment
  statement, not a certification.

Policy, credential management, and responsible disclosure:
[`SECURITY.md`](SECURITY.md). Data-flow map:
[`docs/DATA-CLASSIFICATION.md`](docs/DATA-CLASSIFICATION.md).

---

## Repository layout

```
atlas-os/
├── atlas_os/        the `atlas` CLI package (init, doctor, skills, wrappers)
├── pyproject.toml   packaging — `uv tool install` / `pipx` / `pip install -e .`
├── scripts/         embed · graph · commit · changelog · email · health · trade
├── tests/           pytest suite (scripts + CLI; hermetic, no network)
├── .github/         CI workflow (ruff · pytest · pip-audit) + issue/PR templates
├── skills/          15 SKILL.md prompts (9 scheduled tasks + 6 example skills, templated)
├── schemas/         frontmatter schema enforcement + docs
├── templates/       CLAUDE.md, memory structure, vault skeleton, ops dashboard
├── trading/         optional multi-agent research SDK
├── dashboard/       static ops dashboard + setup notes
├── docs/            setup, configuration, scripts, architecture, rebuild, FAQ, …
├── Dockerfile       run the CLI in a container (Python 3.11-slim + git)
├── docker-compose.yml   bind-mount your vault, load .env, run any subcommand
├── .env.example     every configurable variable, documented
├── CHANGELOG.md     release history (Keep a Changelog)
├── SECURITY.md · CONTRIBUTING.md · LICENSE
```

---

## Documentation

Full docs live in [`docs/`](docs/README.md):

- [**Tutorial — your first 24 hours**](docs/TUTORIAL.md) — the full end-to-end
  walkthrough, from `pip install` to an autonomous system.
- [**Feature deep-dives**](docs/features/README.md) — how each feature works
  internally (RAG, graph, git automation, trading, skills, email, health).
- [Setup](docs/SETUP.md) — install from scratch (package or source).
- [**Configuration reference**](docs/CONFIGURATION.md) — every env var: default,
  required/optional, consuming script.
- [**CLI reference & stability contract**](docs/CLI-REFERENCE.md) — every command,
  flag, env var, and exit code; the v1.0 stability promise.
- [**Script & CLI reference**](docs/SCRIPTS.md) — every command and flag.
- [Scheduled tasks](docs/SCHEDULED-TASKS.md) — the skills, cadences, placeholders,
  and the skills catalog.
- [**Skills catalogue**](docs/SKILLS-CATALOGUE.md) — the full 160+ skill menu by
  domain · [**Skills framework**](docs/SKILLS-FRAMEWORK.md) — anatomy, lifecycle,
  and authoring your own.
- [**Migration guide — v0.3.0 → v1.0**](docs/MIGRATION.md) — upgrading an existing
  install (backward compatible; what's new and how to adopt it).
- [Architecture](docs/ARCHITECTURE.md) · [Rebuild runbook](docs/REBUILD.md) ·
  [Data classification](docs/DATA-CLASSIFICATION.md) · [FAQ](docs/FAQ.md)
- [Frontmatter schemas](schemas/frontmatter-schemas.md) ·
  [Trading SDK](trading/README.md) · [Dashboard](dashboard/README.md)
- [Security policy](SECURITY.md) · [Contributing](CONTRIBUTING.md) ·
  [Changelog](CHANGELOG.md)

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `VAULT_PATH … not set` | Run `atlas init`, or `set -a; source .env; set +a` before running scripts. |
| Embeddings unreachable | Confirm your LLM is running: `curl http://$EMBED_HOST:$EMBED_PORT/v1/models`. Set `EMBED_URL` for non-standard paths. |
| `atlas` command not found (editable install, Py 3.14) | Use `python -m atlas_os <command>`. |
| Gmail rejects the password | Use an app password (2FA required), not your account password. |
| `vault_commit` errors about git | Your vault must be its own git repo: `cd "$VAULT_PATH" && git init`. |
| A subsystem shows DEGRADED | Expected for components you haven't installed (TTS, dashboard). |

More: [`docs/FAQ.md`](docs/FAQ.md). For a clean rebuild:
[`docs/REBUILD.md`](docs/REBUILD.md).

---

## Frequently asked

- **Does it support Ollama?** Yes. The [pluggable LLM backends](#features)
  auto-detect Ollama (alongside LM Studio, llama.cpp, and any OpenAI-compatible
  endpoint). Run `atlas backends` to see what's reachable, or force it with
  `ATLAS_LLM_BACKEND=ollama`.
- **Is there a setup wizard?** Yes — `atlas init` is an interactive wizard that
  detects your LLM, writes `.env`, scaffolds the vault, and makes the first
  commit. Zero to running in about 5 minutes. See
  [First run](#first-run-walkthrough).
- **Does it have logging?** Yes — an append-only JSONL [audit trail](#audit-trail)
  records every autonomous action (what ran, how, the outcome, duration, and what
  changed). Inspect it with `atlas audit show` / `tail` / `export` (CSV for
  compliance).
- **Can I run it in Docker?** Yes — a `Dockerfile` and `docker-compose.yml` ship
  in the repo root. Bind-mount your vault and run any subcommand in a container.
  See [Docker](#docker-optional).
- **Is there a config file?** Yes — everything is configured through a `.env`
  file (no hardcoded paths, hosts, emails, or secrets). `atlas init` generates a
  commented one for you; [`.env.example`](.env.example) documents every variable.
  See [Configuration](#configuration).
- **Is there a dashboard?** Yes — a self-contained, single-file ops
  [dashboard](#dashboard-optional) (`templates/ops-dashboard.html`) backed by
  `atlas health --json` and `atlas changelog --json`.
- **How do I fix a broken setup?** Run `atlas doctor --fix` — it diagnoses each
  subsystem and repairs what it safely can.

---

## Roadmap

The **[v2.0.0 milestone](https://github.com/paulholland511/atlas-os/milestone/2)**
is **complete** — every item below shipped in v2.0.0 (contributions still welcome
for what's next):

- ✅ **SQLite vector store** ([#10](https://github.com/paulholland511/atlas-os/issues/10)) —
  production-scale RAG: `vectors.db` with `sqlite-vec` KNN, incremental
  insert/delete, and a graceful brute-force fallback. *Shipped.*
- ✅ **Advanced RAG pipeline** ([#11](https://github.com/paulholland511/atlas-os/issues/11)) —
  semantic chunking, hybrid BM25 + vector search, TF-IDF reranking, embedding
  cache, metadata filtering, and the `atlas search` command. *Shipped.*
- ✅ **Open-source lightweight dashboard** ([#12](https://github.com/paulholland511/atlas-os/issues/12)) —
  a local-first Flask web UI: system health, audit trail, scheduled-task status,
  skill management, vector-store stats, and RAG search. Launch with
  `atlas dashboard` (`pip install 'atlas-os[dashboard]'`). *Shipped.*
- ✅ **Skills marketplace / registry** ([#13](https://github.com/paulholland511/atlas-os/issues/13)) —
  share, discover, and install community skills: a JSON registry, `atlas skills
  search`, schema-validated `atlas skills publish` packaging, custom registries,
  and manifest dependency resolution. *Shipped.*
- ✅ **Visual knowledge graph viewer** ([#14](https://github.com/paulholland511/atlas-os/issues/14)) —
  a D3.js force-directed view of how your notes connect, in the dashboard at
  `/graph` (or `atlas graph --open`): nodes coloured by type, zoom/pan, search,
  per-type filters, and a click-through panel of each note's links and backlinks.
  *Shipped.*

### ✅ v3.0.0 — the architecture refactor (shipped)

The **[v3.0.0 milestone](https://github.com/paulholland511/atlas-os/milestone/3)**
is **complete** — a lean core, MCP-native skills, a security gate for community
code, bullet-proof git sync, and a scalable, pluggable vector store all shipped:

- ✅ **Extension architecture** ([#15](https://github.com/paulholland511/atlas-os/issues/15)) —
  decoupled the lean core (vault, git sync, RAG, CLI, dashboard, audit trail)
  from the domain verticals. Trading/voice/jobs move to `extensions/`, installed
  via extras (`pip install 'atlas-os[trading]'`) and discovered through
  setuptools entry points with a clean `register_commands()` /
  `register_skills()` / `register_schedules()` API. *Shipped.*
- ✅ **MCP skills** ([#16](https://github.com/paulholland511/atlas-os/issues/16)) —
  the skill framework speaks the **Model Context Protocol**: the runtime is an
  MCP client, each skill an MCP server (stdio for local, SSE/HTTP for remote),
  existing `SKILL.md` skills auto-wrapped in a shim, and skills usable from
  Claude Code, Cowork, and any MCP host. *Shipped.*
- ✅ **Security hardening** ([#17](https://github.com/paulholland511/atlas-os/issues/17)) —
  AST static analysis at `atlas skills install` (BLOCK / WARN / INFO), a
  restricted runtime sandbox (timeout, memory limit, no network by default),
  and full audit-trail logging for community skills via `atlas security report`.
  *Shipped.*
- ✅ **Git sync hardening** ([#18](https://github.com/paulholland511/atlas-os/issues/18)) —
  favour-local merges that abort true conflicts untouched, frontmatter
  validation before every automated commit, advisory file locking, and stale
  `.git/*.lock` cleanup, so automated git never corrupts your vault. Surfaced via
  `atlas sync`, `atlas validate`, and `atlas doctor`. *Shipped.*
- ✅ **Scalable vector storage** ([#19](https://github.com/paulholland511/atlas-os/issues/19)) —
  a pluggable `VectorBackend` interface with `sqlite-vec` as the zero-config
  default plus **LanceDB** (zero-copy disk queries, metadata filtering) and
  ChromaDB options, selectable via `VECTOR_BACKEND`, with an
  `atlas migrate-vectors` tool. *Shipped.*

Further out:

- ✅ **PyPI release** — [Atlas OS is on PyPI](https://pypi.org/project/atlas-os/):
  `pipx install atlas-os` (or `uv tool install atlas-os` / `pip install atlas-os`),
  published automatically on every `v*` tag via Trusted Publishing
  ([`docs/PUBLISHING.md`](docs/PUBLISHING.md)). *Shipped.*
- **Nix flake** — `nix run github:paulholland511/atlas-os` for a hermetic install.

Recently shipped: the SQLite vector store and the advanced RAG pipeline (above),
the `atlas dashboard` web UI, the skills marketplace (`atlas skills search` /
`publish` / `registry`), an append-only audit trail, and `atlas skills install`
for one-command skill deployment with placeholder substitution.

---

## Development & testing

Atlas OS ships with a `pytest` suite covering the core scripts (text helpers,
graph building, git-status parsing, scoring, SMTP flow, and the trading
briefing) — all hermetic: no network, no env vars, no real vault required.

```bash
# From a source checkout, install the dev tooling (test runner, linter, auditor):
pip install -r requirements.txt        # or: pip install pytest ruff pip-audit

# Run the full suite:
pytest                                 # config lives in pyproject.toml

# Lint and audit exactly as CI does:
ruff check scripts tests
pip-audit -r requirements.txt
```

Tests live in [`tests/`](tests/) and stub every external dependency
(`requests`, `smtplib`, `git`, and the optional `tradingagents` package) so they
run in well under a second. `tests/conftest.py` points `VAULT_PATH`/`RAG_DIR` at
a throwaway temp directory before any script is imported, so running the suite
never touches your real vault.

Every push and pull request to `main` runs the same three checks on GitHub
Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)): **ruff →
pytest → pip-audit** on Python 3.12. Please run them locally before opening a PR.

---

## Contributing

Contributions welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md). The golden
rule: **never commit personal data, credentials, or PII.** Keep `SKILL.md` files
generic (`{{PLACEHOLDER}}` tokens), note any new env vars in `.env.example`, and
run the PII scan in `CONTRIBUTING.md` before every commit. Python style: 3.11+,
type hints, env-var config, `ruff`, minimal dependencies.

---

## License & disclaimer

[MIT](LICENSE).

Atlas OS is a template project released as-is. The trading module is **not
financial advice**. You operate your own controls, secrets, and data — review
each automation before enabling it.
