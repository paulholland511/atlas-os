# Atlas OS Documentation

The full documentation set. Start with the README in the repo root for the
overview, then dive in here.

## Feature deep-dives

How each feature actually works (internals, data formats, config), grounded in
the source — see [**features/**](features/README.md):

- [Knowledge vault & schemas](features/knowledge-vault.md)
- [Local RAG search](features/rag-search.md)
- [Knowledge graph](features/knowledge-graph.md)
- [Git automation](features/git-automation.md)
- [Scheduled tasks & skills catalog](features/skills-and-automation.md)
- [Email reports](features/email-reports.md)
- [Trading research SDK](features/trading-sdk.md)
- [Health check & dashboard](features/health-and-dashboard.md)

## Getting started

- [**QUICKSTART.md**](QUICKSTART.md) — zero to working setup in 5 minutes.
- [**EXAMPLES.md**](EXAMPLES.md) — copy-paste walkthroughs: Gmail SMTP, LM Studio,
  first scheduled task, first RAG embed.
- [**SETUP.md**](SETUP.md) — step-by-step installation from scratch, the
  core-vs-optional feature matrix, and a [Docker quick-start](SETUP.md#run-in-docker-optional)
  (root [`Dockerfile`](../Dockerfile) · [`docker-compose.yml`](../docker-compose.yml)).
- [**CONFIGURATION.md**](CONFIGURATION.md) — every environment variable: purpose,
  default, required/optional, and which scripts read it.
- [**SCRIPTS.md**](SCRIPTS.md) — complete CLI reference for every script and all
  their flags.
- [**FAQ.md**](FAQ.md) — common questions and troubleshooting.

## Operating it

- [**SCHEDULED-TASKS.md**](SCHEDULED-TASKS.md) — the Claude Cowork skills, their
  cadences, the placeholder tokens, and the in-vault **skills catalog** agents
  use for discovery.
- [**REBUILD.md**](REBUILD.md) — disaster-recovery / clean-install runbook.

## Design & data

- [**ARCHITECTURE.md**](ARCHITECTURE.md) — how the pieces fit together and the
  design principles.
- [**DATA-CLASSIFICATION.md**](DATA-CLASSIFICATION.md) — what data the system
  touches, where it lives, and whether it ever leaves the device.
- [**../SECURITY.md**](../SECURITY.md) — security policy, credential management,
  ISO 27001 alignment, responsible disclosure.

## Component docs

- [**../schemas/frontmatter-schemas.md**](../schemas/frontmatter-schemas.md) —
  the per-folder frontmatter schemas and how enforcement works.
- [**../trading/README.md**](../trading/README.md) — the optional trading
  research SDK.
- [**../dashboard/README.md**](../dashboard/README.md) — dashboard options.

## Contributing

- [**../CONTRIBUTING.md**](../CONTRIBUTING.md) — contribution guidelines and the
  golden rule (never commit personal data).
- [**Development & testing**](../README.md#development--testing) — running the
  `pytest` suite, `ruff`, and `pip-audit` locally (the same checks CI runs on
  every push via [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)).
- [**../CHANGELOG.md**](../CHANGELOG.md) — release history.

---

### Reading order for a first-time setup

1. Root [`README.md`](../README.md) — what Atlas OS is.
2. [`SETUP.md`](SETUP.md) — install it.
3. [`CONFIGURATION.md`](CONFIGURATION.md) — set your env vars.
4. [`SCRIPTS.md`](SCRIPTS.md) — run the pipeline.
5. [`SCHEDULED-TASKS.md`](SCHEDULED-TASKS.md) — automate it.
6. [`FAQ.md`](FAQ.md) — when something doesn't work.
