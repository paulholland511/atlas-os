# Security Policy

Atlas OS is built local-first and privacy-first. This document describes how
data is handled, how credentials are managed, and how to report a vulnerability.

## Data classification policy

Atlas OS distinguishes four data classes. The short version:

- **Public** — this repo (code, docs, templates). Contains no personal data.
- **Internal** — your vault notes, RAG vectors, knowledge graph. **Never leave
  your machine.**
- **Confidential** — trackers, positions, email content. Stored outside the
  repo and git-ignored.
- **Secret** — passwords and API keys. Environment variables only.

Full detail and the data-flow map: [`docs/DATA-CLASSIFICATION.md`](docs/DATA-CLASSIFICATION.md).

## What stays local vs. what is transmitted

| Data | Default behaviour |
|---|---|
| Vault notes & embeddings | **Local only.** Embeddings go to the LLM endpoint you configure — `localhost`/LAN when using a local model. |
| Knowledge graph, indexes | Local only; git-ignored. |
| Trading analyst votes | Local only, unless you opt into the cloud Portfolio Manager (off by default), which sends only anonymous votes. |
| Email | Sent via *your* SMTP account to recipients *you* specify. |
| Web search (some tasks) | Queries the public web for news; sends none of your data. |

There is **no telemetry and no analytics**. Atlas OS does not phone home, and
the maintainers receive nothing about your usage.

## Credential management

- All secrets are read from **environment variables** (`SMTP_APP_PASSWORD`,
  `ANTHROPIC_API_KEY`, etc.). Nothing is hardcoded.
- `.env` is git-ignored; only `.env.example` (with placeholder values) is
  committed.
- For Gmail SMTP, use an [app password](https://myaccount.google.com/apppasswords)
  (requires 2FA), never your account password.
- Never paste secrets into notes, `SKILL.md` prompts, or code.

## Running in containers (Docker)

The optional [`Dockerfile`](Dockerfile) / [`docker-compose.yml`](docker-compose.yml)
preserve the local-first, secrets-in-env model:

- **No secrets in the image.** `.dockerignore` excludes `.env` (and `.env.*`
  except `.env.example`) from the build context, so credentials are never baked
  into an image layer. They are supplied only at **runtime** via `--env-file .env`
  (compose `env_file:`), the same way the host shell loads them.
- **No vault data in the image.** Your vault is **bind-mounted** at run time
  (`-v …:/vault`), not copied in at build time. The image contains only the
  public repo's code/scripts — the same Public-class data already on GitHub.
- **Don't push images built with `--build-arg EXTRAS` to a public registry**
  without re-checking they contain no local state; prefer building locally.
- **Local network only.** A host LLM is reached over `host.docker.internal`;
  nothing in the container phones home. Treat the container like the CLI — it
  inherits the same data-classification rules above.

## ISO 27001 alignment

This repository is designed to support an information-security posture aligned
with ISO/IEC 27001 principles. It is a template — *you* operate the controls —
but the project is built so that doing the right thing is the default:

- **A.5 / A.8 — Information classification & handling:** a documented data
  classification scheme with explicit storage and transmission rules
  ([`docs/DATA-CLASSIFICATION.md`](docs/DATA-CLASSIFICATION.md)).
- **A.5.x — Access control & secrets:** credentials held only in environment
  variables; no secrets in source; `.env` and key/cert patterns git-ignored.
- **A.8 — Data minimisation:** the public repo contains zero personal data; the
  `.gitignore` blocks PII-bearing artefacts (spreadsheets, vector stores, vault
  content) from ever being committed.
- **A.8.13 — Backup & recoverability:** a documented rebuild/DR runbook
  ([`docs/REBUILD.md`](docs/REBUILD.md)); the vault is the single source of
  truth and all derived data is reproducible.
- **A.5.7 — Local processing:** local-first design keeps data on the device;
  external calls are explicit and opt-in.
- **Auditability:** automatic, categorised git history of the vault.

This is an alignment *statement*, not a certification. Achieving certified
compliance is the responsibility of the operator and their organisation.

## Responsible disclosure

If you discover a security vulnerability:

1. **Do not** open a public issue.
2. Email the maintainer (see the repository's GitHub profile / `git log`) or
   open a private security advisory via GitHub's **Security → Report a
   vulnerability** feature.
3. Include reproduction steps and impact. Please allow a reasonable time for a
   fix before public disclosure.

We aim to acknowledge reports promptly and will credit reporters who wish to be
named.

## Supported versions

This is a template project released as-is. Security fixes are applied to the
`main` branch.
