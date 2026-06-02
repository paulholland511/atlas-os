# Atlas OS Documentation

The full documentation set. Start with the README in the repo root for the
overview, then dive in here.

## Getting started

- [**SETUP.md**](SETUP.md) — step-by-step installation from scratch.
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
- [**../CHANGELOG.md**](../CHANGELOG.md) — release history.

---

### Reading order for a first-time setup

1. Root [`README.md`](../README.md) — what Atlas OS is.
2. [`SETUP.md`](SETUP.md) — install it.
3. [`CONFIGURATION.md`](CONFIGURATION.md) — set your env vars.
4. [`SCRIPTS.md`](SCRIPTS.md) — run the pipeline.
5. [`SCHEDULED-TASKS.md`](SCHEDULED-TASKS.md) — automate it.
6. [`FAQ.md`](FAQ.md) — when something doesn't work.
