# Quick Start — Atlas OS in 5 minutes

The shortest path from zero to a working Atlas OS: a searchable markdown vault
with git history and a scheduled task. This skips every optional feature — just
the core. For the full walkthrough see [`SETUP.md`](SETUP.md).

---

## 1. Prerequisites (1 min)

You need three things installed:

- **Python 3.11+** — check with `python3 --version`
- **Git** — check with `git --version`
- A **markdown vault** — any folder of `.md` files. [Obsidian](https://obsidian.md/)
  is the natural home but isn't required; an empty folder works (Atlas OS will
  scaffold it).

A **Claude Cowork** subscription is what *runs* the scheduled tasks, but the
Python tooling below works standalone without it.

---

## 2. Clone the repo (30 sec)

```bash
git clone https://github.com/paulholland511/atlas-os.git
cd atlas-os
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt    # core deps, pinned
pip install -e .                   # the `atlas` command
```

---

## 3. Configure 3 essential values (1 min)

```bash
cp .env.example .env
```

Open `.env` and set just these three — leave everything else at its default:

```bash
VAULT_PATH=~/Documents/Obsidian/MyVault   # where your notes live (or will)
USER_EMAIL=you@example.com                # where reports get sent
SMTP_APP_PASSWORD=your-gmail-app-password # 16-char Gmail app password
```

> Don't have a Gmail app password yet? Skip `SMTP_APP_PASSWORD` for now — email
> is the only feature that needs it, and the rest works without it. When you're
> ready, [`EXAMPLES.md`](EXAMPLES.md#smtp-setup-gmail-app-password) walks you
> through it.

`.env` is git-ignored — your secrets never get committed.

---

## 4. Run setup (1 min)

```bash
atlas init --yes    # scaffold the vault skeleton + git-init it
```

This creates your vault's index files (`.claude-index.md`, `wiki/index.md`,
`wiki/hot.md`, `Operations Dashboard.md`), generates the skills catalog, and
makes the first git commit of your vault.

---

## 5. Create your first scheduled task (1 min)

The simplest useful automation is a **daily vault backup** — commit every change
to your vault's git history. Run it manually first to see it work:

```bash
atlas commit          # commits your vault with an auto-categorised message
```

To run it on a schedule, ask Claude Cowork to run `atlas commit` daily (e.g.
"every day at 6pm, run `atlas commit` in my atlas-os folder"). Full details and a
step-by-step version: [`EXAMPLES.md`](EXAMPLES.md#first-scheduled-task-daily-vault-backup).

---

## 6. Verify it works (30 sec)

```bash
atlas doctor      # OK / WARN / FAIL per subsystem
```

You should see green checks for **Python**, **Vault path**, and **Vault git**.
WARNs for the RAG index, embeddings, and email are expected — those are optional
features you haven't set up yet. As long as nothing says **FAIL**, you're done.

```
Atlas OS — doctor

  ✓ Python         3.13 (need ≥ 3.11)
  ✓ Vault path     /Users/you/Documents/Obsidian/MyVault
  ✓ Vault git      tracked
  ! RAG index      no vectors yet — run `atlas embed --full`
  ! Embeddings     unreachable (RAG disabled until it's up)
  ! Email (SMTP)   not configured (reports won't send)

3 OK · 3 WARN · 0 FAIL
```

---

## What next?

- **Search your notes** — point Atlas OS at a local LLM and run `atlas embed --full`.
  See [`EXAMPLES.md`](EXAMPLES.md#lm-studio-connection) and [`EXAMPLES.md`](EXAMPLES.md#first-rag-embed).
- **Send email reports** — finish the [Gmail setup](EXAMPLES.md#smtp-setup-gmail-app-password).
- **Automate more** — browse the [skills catalog](SCHEDULED-TASKS.md).
- **Tune everything** — every env var is documented in [`CONFIGURATION.md`](CONFIGURATION.md).
- **Prefer containers?** Skip the venv entirely and run the CLI in Docker —
  see the [Docker section in SETUP.md](SETUP.md#run-in-docker-optional).
