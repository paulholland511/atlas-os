```
       _   _   _              ___  ____
      / \ | |_| | __ _ ___   / _ \/ ___|
     / _ \| __| |/ _` / __| | | | \___ \
    / ___ \ |_| | (_| \__ \ | |_| |___) |
   /_/   \_\__|_|\__,_|___/  \___/|____/

   A personal AI operating system, built on Claude Cowork.
```

# Atlas OS

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Local-first](https://img.shields.io/badge/privacy-local--first-success.svg)](docs/DATA-CLASSIFICATION.md)
[![No telemetry](https://img.shields.io/badge/telemetry-none-brightgreen.svg)](SECURITY.md)
[![Docs](https://img.shields.io/badge/docs-complete-informational.svg)](docs/README.md)

**Atlas OS** turns [Claude Cowork](https://claude.ai/) into a personal,
local-first operating system over a markdown knowledge vault. It gives you a
searchable second brain, scheduled automations, automatic git history, and a
set of report/agent workflows — all configured through environment variables and
runnable entirely on your own machine.

It ships with **no personal data, no credentials, and no PII**. Everything is a
template you point at your own vault, your own local LLM, and your own email
account.

> **Privacy by default.** Your notes and embeddings never leave your machine
> unless *you* explicitly wire up an external endpoint. See
> [`SECURITY.md`](SECURITY.md) and [`docs/DATA-CLASSIFICATION.md`](docs/DATA-CLASSIFICATION.md).

## Features

Eight composable systems:

1. **Knowledge vault** — a folder of markdown notes (Obsidian-friendly), with
   per-folder frontmatter schemas kept consistent automatically.
2. **Local RAG search** — chunk + embed your notes via a local LLM into a
   hybrid (vector + keyword) search index.
3. **Knowledge graph** — a wikilink graph derived from your notes for
   backlinks and "related notes".
4. **Git automation** — auto-commit the vault with categorised messages and
   generate changelogs for a morning briefing.
5. **Scheduled tasks & skills catalog** — nightly indexing, daily reports,
   weekly health checks and more, as Claude Cowork skills, plus a
   self-updating `Skills Catalog.md` in the vault so agents can discover every
   automation they can invoke.
6. **Email reports** — credential-free SMTP sender for status reports and
   newsletters.
7. **Trading research SDK** *(optional)* — a multi-agent market-research
   framework that writes briefings into your vault. *Not financial advice.*
8. **Voice / TTS hooks & dashboard** *(optional)* — health-check probes for a
   local TTS service, plus a static operations dashboard.

## Quick start

Install the `atlas` command, then let it set everything up:

```bash
uv tool install "git+https://github.com/paulholland511/atlas-os"   # or: pipx install …

atlas init       # detects your local LLM, writes .env, scaffolds the vault
atlas doctor     # verify the setup (OK / WARN / FAIL per subsystem)
atlas embed --full   # build the RAG index (needs a local LLM)
```

That's it. `atlas init` is interactive (auto-detects LM Studio / Ollama, prompts
for your vault path and email); add `--yes` for a non-interactive run with
defaults. Extras: `atlas-os[trading]` (yfinance), `atlas-os[pdf]` (pdfplumber).

<details>
<summary>Prefer to run the scripts directly (no install)?</summary>

```bash
git clone https://github.com/paulholland511/atlas-os.git ~/code/atlas-os
cd ~/code/atlas-os
python3 -m venv .venv && source .venv/bin/activate
pip install requests pyyaml pdfplumber

cp .env.example .env          # then edit — at minimum set VAULT_PATH
set -a; source .env; set +a

python3 scripts/health_check.py        # see what's up
python3 scripts/embed_vault.py --full  # build the RAG index (needs a local LLM)
```
</details>

Full walkthrough: [`docs/SETUP.md`](docs/SETUP.md).

## The `atlas` CLI

One command wraps the whole system. Configuration is read from the environment;
a `.env` in the current directory or repo root is auto-loaded — no manual
`source` needed.

| Command | What it does |
|---|---|
| `atlas init` | Guided onboarding — detect LLM, write `.env`, scaffold vault, generate the skills catalog |
| `atlas doctor` | Validate the setup; report OK / WARN / FAIL per subsystem |
| `atlas skills` | List the agent skills catalog; `--sync` writes it into the vault |
| `atlas embed` | Build/refresh the RAG index (`--full`, `--incremental`, `--test N`, …) |
| `atlas graph` | Rebuild the wikilink knowledge graph |
| `atlas commit` | Auto-commit the vault with a categorised message |
| `atlas changelog` | Summarise what changed over a window |
| `atlas health` | Full subsystem health probe (`--json`, `--quiet`) |
| `atlas email` | Send an email via SMTP (JSON payload) |
| `atlas schemas` | Enforce per-folder frontmatter schemas |

Run `atlas --help` or `atlas <command> --help` for details, or see
[`docs/SCRIPTS.md`](docs/SCRIPTS.md).

## Prerequisites

- **Claude Cowork** subscription (skills, scheduled tasks, memory)
- **Python 3.11+**
- A **markdown vault** (Obsidian optional)
- *(Optional)* a **local LLM** with an OpenAI-compatible API (LM Studio, Ollama)
  for RAG and the trading module
- *(Optional)* **Node.js** if you build the full dashboard

## Architecture

```
 Claude Cowork ──▶ skills/ (scheduled tasks)
        │
        ├─▶ scripts/  embed · graph · commit · changelog · email · health · trade
        │       │
        │       ├─▶ Markdown vault  (git-tracked, local)
        │       └─▶ .rag/  vectors.json + graph.json  (local, git-ignored)
        │
        └─▶ Local LLM  (embeddings + chat, OpenAI-compatible)
```

Details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Repository layout

```
atlas-os/
├── atlas_os/     the `atlas` CLI package (init, doctor, command wrappers)
├── pyproject.toml  packaging — `uv tool install` / `pipx` / `pip install -e .`
├── scripts/      RAG, graph, git, email, health-check, trading briefing
├── skills/       9 scheduled-task SKILL.md prompts (templated)
├── schemas/      frontmatter schema enforcement + docs
├── templates/    CLAUDE.md, memory structure, vault skeleton, ops dashboard
├── trading/      optional multi-agent research SDK
├── dashboard/    static ops dashboard + setup notes
└── docs/         setup, configuration, scripts, architecture, rebuild, FAQ, …
```

## Documentation

Full docs live in [`docs/`](docs/README.md). Quick links:

- [Setup](docs/SETUP.md) — install from scratch.
- [**Configuration reference**](docs/CONFIGURATION.md) — every environment
  variable: default, required/optional, and which script reads it.
- [**Script & CLI reference**](docs/SCRIPTS.md) — every script and all its flags.
- [Scheduled tasks](docs/SCHEDULED-TASKS.md) — the skills and their cadences.
- [Architecture](docs/ARCHITECTURE.md) · [Rebuild runbook](docs/REBUILD.md) ·
  [Data classification](docs/DATA-CLASSIFICATION.md) · [FAQ](docs/FAQ.md)
- [Security policy](SECURITY.md) · [Contributing](CONTRIBUTING.md) ·
  [Changelog](CHANGELOG.md)

## Screenshots / demo

_Placeholder — add your own screenshots here once you've set it up._
A static dashboard template lives at
[`templates/ops-dashboard.html`](templates/ops-dashboard.html) (open it in a
browser).

## Configuration

All configuration is via environment variables — copy
[`.env.example`](.env.example) to `.env` and edit. Every variable (purpose,
default, required/optional, and which script reads it) is documented in
[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md). Nothing personal is hardcoded
anywhere in the repo.

## Contributing

Contributions welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md). The golden
rule: **never commit personal data, credentials, or PII.**

## Security

See [`SECURITY.md`](SECURITY.md) for the data-handling policy, credential
management, and responsible-disclosure process.

## License

[MIT](LICENSE).
