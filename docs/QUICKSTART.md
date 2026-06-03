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

## 3. Run the setup wizard (1 min)

One command does everything — no hand-editing `.env` required:

```bash
atlas init
```

The interactive wizard walks you through the whole setup:

1. **Finds your vault** — offers a smart default (an existing
   `~/Documents/Obsidian/*` folder, `~/vault`, or the current directory) that
   you can accept or override.
2. **Auto-detects your LLM** — probes the common local ports (LM Studio `:5555`,
   Ollama `:11434`, llama.cpp `:8080`) and wires up whichever is running. None
   running? No problem — RAG just stays off until you start one.
3. **Asks about email** (optional) — SMTP settings for report delivery; skip it
   and everything else still works.
4. **Generates `.env`** from your answers (git-ignored — secrets never get
   committed).
5. **Scaffolds the vault** — creates the directory tree (`.atlas/`, `.rag/`,
   `wiki/`), the index files (`.claude-index.md`, `wiki/index.md`, `wiki/hot.md`,
   `Operations Dashboard.md`), the skills catalog, and git-inits the vault.
6. **Runs `atlas doctor`** automatically and prints a "you're ready" summary.

Prefer to skip every prompt? `atlas init --yes` accepts all the smart defaults
for a fully non-interactive run (handy for scripts and fresh containers). Add
`--vault PATH` to set the vault explicitly, or `--force` to overwrite an existing
`.env`.

> Want email reports? You'll need a 16-char Gmail app password — the wizard asks
> for it, or you can add it to `.env` later.
> [`EXAMPLES.md`](EXAMPLES.md#smtp-setup-gmail-app-password) walks you through it.

---

## 4. Create your first scheduled task (1 min)

The simplest useful automation is a **daily vault backup** — commit every change
to your vault's git history. Run it manually first to see it work:

```bash
atlas commit          # commits your vault with an auto-categorised message
```

To run it on a schedule, ask Claude Cowork to run `atlas commit` daily (e.g.
"every day at 6pm, run `atlas commit` in my atlas-os folder"). Full details and a
step-by-step version: [`EXAMPLES.md`](EXAMPLES.md#first-scheduled-task-daily-vault-backup).

---

## 5. Re-check anytime with the doctor (30 sec)

The wizard already ran this for you at the end of `atlas init`, but you can
re-run it whenever you change your config:

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
