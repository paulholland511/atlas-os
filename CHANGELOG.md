# Changelog

All notable changes to Atlas OS are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Pluggable LLM backends** ([`atlas_os/backends.py`](atlas_os/backends.py)).
  Atlas OS now auto-detects any OpenAI-compatible LLM server, probing **LM Studio
  (`:5555`) → Ollama (`:11434`) → llama.cpp (`:8080`) → a custom
  `OPENAI_COMPATIBLE_URL`** in that order and using the first that responds. The
  module exposes `detect_backend()`, `get_client()`, `list_models()`, and a
  one-shot `run_inference()` test. Two env vars override the defaults:
  `ATLAS_LLM_BACKEND` forces a backend (`lmstudio`/`ollama`/`llamacpp`/
  `openai-compatible`, skipping detection) and `ATLAS_LLM_MODEL` overrides the
  chat model name. New CLI: `atlas backends` lists every backend with
  reachability + models, and `atlas backends test` runs an end-to-end inference.
  The RAG (`embed_vault.py`), trading (`trading_briefing.py`), and health
  (`health_check.py`) scripts now resolve their endpoint through this module.
  **Fully backward compatible:** explicit `EMBED_*` / `LM_STUDIO_*` settings still
  win, so existing setups are unchanged. Covered by
  [`tests/test_backends.py`](tests/test_backends.py).
- **Skills catalogue & framework docs.** A
  [`docs/SKILLS-CATALOGUE.md`](docs/SKILLS-CATALOGUE.md) documenting the full menu
  of **160+ skills** — 149 capability skills across seven domains (Security,
  DevOps, Frontend, Backend, Quality, Data & AI, Business), each with a one-line
  summary, what it does, and when to use it, plus the four Atlas-native skills
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
- **Audit trail** ([`atlas_os/audit.py`](atlas_os/audit.py)). An append-only
  JSONL log of every autonomous action, written to `$ATLAS_AUDIT_PATH` (default
  `$VAULT_PATH/.atlas/audit.jsonl`). Each entry records the timestamp, action,
  trigger (`scheduled`/`manual`/`cli`), status, duration, what changed, why it
  ran, and any error. Appends are serialised with an in-process lock plus an
  OS-level advisory file lock (safe across concurrent `atlas` processes) and the
  file auto-rotates at 10 MB to `audit.jsonl.1`, `.2`, …. Every script-wrapping
  command (`embed`, `commit`, `graph`, `changelog`, `health`, `trading`,
  `email`) now logs its outcome automatically; scheduled tasks tag their runs by
  setting `ATLAS_TRIGGER=scheduled`. New `atlas audit` subcommands: `show`
  (`--limit`/`--action`/`--since`), `tail` (last 5, compact), and `export`
  (`--format csv|json`, `--output`) for compliance reporting. Strengthens ISO
  27001 control A.12.4 (logging & monitoring). Covered by
  [`tests/test_audit.py`](tests/test_audit.py).
- **GitHub issue & PR templates**
  ([`.github/ISSUE_TEMPLATE/`](.github/ISSUE_TEMPLATE/),
  [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md)) — a
  structured bug report (with an environment block: OS, Python, Atlas OS
  version, install method), a feature request (use case / proposed solution /
  alternatives), and a PR checklist (tests, docs, the PII scan). An
  `ISSUE_TEMPLATE/config.yml` disables blank issues and routes security reports
  to `SECURITY.md` and questions to the FAQ.
- **README status badges** — GitHub Actions CI status, GitHub stars, and
  last-commit, alongside the existing license / Python / privacy / docs badges.
- **`atlas trading`** — wraps `scripts/trading_briefing.py` (`--ticker`,
  `--date`, `--dry-run`); the last optional pipeline script to gain a first-class
  subcommand, so the whole system is now reachable through one `atlas` command.
- **Up-front env validation.** Every vault/optional command checks its required
  environment variables before shelling out and exits with a clear message and a
  non-zero code if any are missing — a half-configured feature fails fast instead
  of part-way through.
- **`atlas email` flags.** Send mail with `--to` / `--subject` / `--body`
  (`--text` for plain text, repeatable `--attach`), or the original raw payload
  via `--json`.
- **Docker support.** A minimal [`Dockerfile`](Dockerfile) (Python 3.11-slim +
  git) that packages the `atlas` CLI, a [`docker-compose.yml`](docker-compose.yml)
  that bind-mounts your vault and loads `.env`, and a `.dockerignore`. Run any
  subcommand in a container without installing Python tooling on the host.
  Build-tested end-to-end (`atlas --version` / `doctor` / `commit` against a
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
- **README**: documented `atlas trading`, the new `atlas email` flags,
  env-validation behaviour, a Docker section (+ a Docker pointer under
  Installation), the Docker files in the repo-layout diagram, and updated the
  `.github/` layout line to note the issue/PR templates.
- **Docs sync across the set** to match the streamlined CLI:
  - `docs/ARCHITECTURE.md` — added the `atlas` CLI as component 0 (the unified
    entry point) and a Deployment section covering checkout / installed tool /
    Docker.
  - `docs/EXAMPLES.md`, `docs/features/email-reports.md` — updated every
    `atlas email` example to the new flags (with `--json` for raw payloads),
    fixing samples that the flag change would otherwise have broken.
  - `docs/QUICKSTART.md` — corrected the minimum Python to 3.11+ and linked the
    Docker quick-start.
  - `docs/README.md` (docs index) — linked the SETUP core-vs-optional matrix and
    the Docker files.
  - `SECURITY.md` — added a "Running in containers (Docker)" section (no secrets
    or vault data in the image; runtime-only `--env-file`; bind-mounted vault).
- **`pyproject.toml`** continues to declare the `atlas` entry point and the
  optional dependency groups (`[pdf]`, `[trading]`, `[all]`); these are now the
  documented install path (`pip install -e ".[all]"`) for the optional features.

## [0.3.0] — 2026-06-02

### Added
- **Agent skills catalog.** A self-updating `Skills Catalog.md` note generated
  into the vault, listing every skill (name, description, suggested cadence)
  read from each `skills/*/SKILL.md` frontmatter — so agents reading or
  searching the vault can discover what automations they can invoke. Carries
  `type: reference` frontmatter so the RAG indexer picks it up.
- **`atlas skills`** — list the catalog in the terminal; `atlas skills --sync`
  (re)generates the note in the vault (`--output` to override the path).
  `atlas init` now generates it automatically on setup.
- The `skills/` directory is bundled into the wheel so the catalog works in an
  installed `atlas` without the source checkout.

## [0.2.0] — 2026-06-02

### Added
- **Installable package** with a unified **`atlas` CLI** (`pyproject.toml`,
  `atlas_os/`). Install via `uv tool install` / `pipx` / `pip install -e .`.
  Subcommands `embed`, `graph`, `commit`, `changelog`, `health`, `email`, and
  `schemas` wrap the existing scripts and forward their flags; configuration
  (`.env`) is auto-loaded.
- **`atlas init`** — guided onboarding: auto-detects a local LLM (LM Studio /
  Ollama / any OpenAI-compatible endpoint), writes `.env`, scaffolds the vault
  skeleton, initialises the vault git repo, and optionally installs the
  `CLAUDE.md` template. Supports `--vault`, `--yes`, `--force`.
- **`atlas doctor`** — validates the whole setup (Python, vault, git, RAG
  index, embeddings endpoint, SMTP) and reports OK / WARN / FAIL with a
  non-zero exit on failures.
- Optional dependency extras: `atlas-os[trading]` (yfinance),
  `atlas-os[pdf]` (pdfplumber), `atlas-os[all]`.
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
  `atlas_os_data/`) so an installed `atlas` works without the source checkout;
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
- Initial public release of Atlas OS — a local-first personal AI operating
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

[Unreleased]: https://github.com/paulholland511/atlas-os/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/paulholland511/atlas-os/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/paulholland511/atlas-os/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/paulholland511/atlas-os/releases/tag/v0.1.0
