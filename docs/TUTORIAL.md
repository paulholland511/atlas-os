# Tutorial — Your first 24 hours with Atlas OS

This is the long-form walkthrough: from `pip install atlas-os` to a system that
indexes, commits, and reports on your knowledge vault while you sleep. It's the
missing middle between the [5-minute Quick Start](QUICKSTART.md) and real daily
use.

It assumes **no prior knowledge** of Obsidian, RAG, vector embeddings, or git
automation. Where a concept matters, this tutorial stops and explains *why* the
thing exists before showing you *how* to use it. Every command is
copy-pasteable, and after each one there's a **"what you should see"** so you can
tell whether it worked.

You don't have to do it in one sitting — it's structured as a timeline so you can
stop after any "Hour" and come back. By the end you'll have a searchable second
brain with git history, a knowledge graph, at least one scheduled task running
itself overnight, and an audit trail you can read over coffee.

> **Time budget:** the hands-on parts take about 90 minutes of actual work
> (Hours 0–4). The rest is your machine working autonomously while you don't.

---

## Table of contents

- [Before you start](#before-you-start)
- [Hour 0 — Install & init (5 min)](#hour-0--install--init-5-min)
- [Hour 1 — Your first vault (15 min)](#hour-1--your-first-vault-15-min)
- [Hour 2 — Knowledge management (20 min)](#hour-2--knowledge-management-20-min)
- [Hour 3 — Automation (15 min)](#hour-3--automation-15-min)
- [Hour 4 — Communication (10 min)](#hour-4--communication-10-min)
- [Hours 5–24 — Going autonomous](#hours-524--going-autonomous)
- [What's next](#whats-next)

---

## Before you start

Atlas OS is a set of Python tools plus a library of [Claude
Cowork](https://claude.ai/) skills. The mental model in one sentence:

> **Your notes live in a plain folder of markdown files; Atlas OS makes that
> folder searchable, version-controlled, and able to act on its own.**

There are two halves:

- **The `atlas` CLI** (this tutorial's focus) — Python tooling that runs *on your
  machine*. Indexing, embeddings, git commits, the knowledge graph, email,
  health checks. This works standalone, with no subscription.
- **Claude Cowork** — the agent runtime that *executes the skills on a schedule*.
  This is what turns "I could run `atlas commit` every night" into "it runs every
  night without me." You don't need it to follow Hours 0–2; you'll want it by
  Hour 3.

Everything is **local-first**. Your notes and their embeddings never leave your
machine unless *you* explicitly wire up an external endpoint. There's no
telemetry. See [`SECURITY.md`](../SECURITY.md) and
[`DATA-CLASSIFICATION.md`](DATA-CLASSIFICATION.md) for the guarantees.

### Prerequisites

You need three things on your machine:

- **Python 3.11 or newer** — check with `python3 --version`
- **Git** — check with `git --version`
- **A terminal** you're comfortable pasting commands into

Two things are **optional** and we'll set them up later, only if you want the
features they unlock:

- A **local LLM** (LM Studio or Ollama) — for search/RAG (Hour 2)
- A **Gmail account** — for email reports (Hour 4)

If you don't have a local LLM yet, that's fine: Atlas OS detects its absence and
simply keeps RAG switched off until you start one. Nothing breaks.

---

## Hour 0 — Install & init (5 min)

### Step 0.1 — Install Atlas OS

There are two ways in. Pick one.

**Option A — install the package (simplest):**

```bash
pip install atlas-os
```

This gives you the `atlas` command globally. If you use
[pipx](https://pipx.pypa.io/) (recommended for CLI tools, keeps it isolated):

```bash
pipx install atlas-os
```

**Option B — clone the source (if you want to read/modify the code or run the
trading SDK and dashboard):**

```bash
git clone https://github.com/paulholland511/atlas-os.git
cd atlas-os
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # core deps, pinned
pip install -e .                  # the `atlas` command, editable
```

**What you should see:** after either path, this prints a version:

```bash
atlas --version
```

```
Atlas OS 1.0.0
```

> **If `atlas` isn't found** after an editable (`-e`) install on Python 3.13+:
> some setups (notably iCloud-synced folders) hide the editable `.pth` file that
> wires up the command, and newer Python skips hidden `.pth` files. The reliable
> fallback is to call the module directly — **everywhere this tutorial says
> `atlas X`, you can run `python -m atlas_os X` instead.** Same program, same
> flags.

### Step 0.2 — Run the init wizard

One command takes a fresh machine from nothing to a working setup. You do **not**
hand-edit any config file:

```bash
atlas init
```

The wizard is interactive and walks you through, in order:

1. **Finds your vault.** It offers a smart default — an existing
   `~/Documents/Obsidian/*` folder if you have one, otherwise `~/vault` or the
   current directory. Accept it or type your own path. Don't have a vault yet?
   Just give it a path that doesn't exist; Atlas OS will create the folder and
   scaffold it.
2. **Auto-detects your local LLM.** It probes the common ports — LM Studio
   (`1234`), a generic endpoint (`5555`), Ollama (`11434`) — and wires up
   whichever is running. None running? It says so and moves on; RAG stays off
   until you start one (Hour 2).
3. **Asks about email** (optional). SMTP details for report delivery. Press enter
   to skip — you can add it in Hour 4.
4. **Writes `.env`.** All your answers land in a git-ignored `.env` file. Secrets
   never get committed.
5. **Scaffolds the vault** — creates the directory tree (`.atlas/`, `.rag/`,
   `wiki/`), the index notes, the skills catalog, and runs `git init` on the
   vault so it has its own history.
6. **Runs `atlas doctor`** automatically and prints a "you're ready" summary.

> **Prefer no prompts?** `atlas init --yes` accepts every smart default for a
> fully non-interactive run (handy for scripts and containers). `--vault PATH`
> sets the vault explicitly; `--force` overwrites an existing `.env`.

**What you should see:** a series of prompts, then a summary ending in something
like `Setup complete — run 'atlas doctor' any time to re-check.`

### Step 0.3 — Verify with the doctor

The wizard already ran this once, but `atlas doctor` is the command you'll come
back to whenever you change config or something feels off:

```bash
atlas doctor
```

**What you should see:**

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

**How to read this:** the three `✓` lines are the core, and they're green. The
three `!` (WARN) lines are *expected* right now — they're optional features you
haven't set up yet (you'll clear the RAG/Embeddings warnings in Hour 2, and Email
in Hour 4). **The only thing that should worry you is a `FAIL`.** As long as
nothing says FAIL, Hour 0 is done.

> `atlas doctor` exits non-zero if anything is FAIL, which makes it useful in
> scripts and CI as a "is my setup sane?" gate.

---

## Hour 1 — Your first vault (15 min)

### What a vault actually is

A **vault** is just a folder of markdown (`.md`) files. That's the whole format.
No database, no proprietary file type — you can open any note in any text editor,
back it up by copying the folder, and read it in 20 years without Atlas OS
installed.

[Obsidian](https://obsidian.md/) is a free, excellent app for *editing* a vault
(it gives you backlinks, graph view, live preview), and Atlas OS is designed to
sit alongside it — but **Obsidian is not required.** Atlas OS works on the raw
folder. If you've never used Obsidian, ignore it for now; we'll work in the
terminal and any editor.

Inside the vault, Atlas OS scaffolds a few special directories. You can ignore
most of them, but it helps to know what they are:

- `wiki/` — your knowledge base notes (the wizard seeds an index, a hot-topics
  cache, and a log here).
- `.rag/` — derived search data (`vectors.json`, `graph.json`). Git-ignored,
  rebuildable. More in Hour 2.
- `.atlas/` — the audit trail (`audit.jsonl`) lives here. More in Hour 3.
- `.claude/` — where installed skills land.

> **Convention:** `$VAULT_PATH` throughout this tutorial means *your* vault path —
> the one you chose in `atlas init`. It's stored in `.env`. To use it as a real
> shell variable, run `set -a; source .env; set +a` once per terminal session.

### Step 1.1 — Create your first notes

Let's add a couple of real notes so there's something to index and commit. Use
your editor, or just paste these:

```bash
# Load your vault path from .env into this shell:
set -a; source .env; set +a

# A first note:
cat > "$VAULT_PATH/wiki/atlas-os-intro.md" <<'EOF'
---
title: Getting started with Atlas OS
type: reference
tags: [meta, tutorial]
---

# Getting started with Atlas OS

Atlas OS turns a folder of markdown into a searchable, self-maintaining
knowledge base. My notes are version-controlled and embedded for semantic
search.

See also [[daily-log]].
EOF

# A second note that links to the first:
cat > "$VAULT_PATH/wiki/daily-log.md" <<'EOF'
---
title: Daily log
type: log
tags: [journal]
---

# Daily log

## 2026-06-03
Set up Atlas OS. First vault is live. Next: wire up a local LLM for search.
Linked back to [[atlas-os-intro]].
EOF
```

Two things to notice in those files:

- **Frontmatter** — the `--- ... ---` block at the top. It's metadata (title,
  type, tags). Atlas OS uses `type:` to apply per-folder schemas and to decide
  how to treat a note. You don't have to memorize the schema; `atlas schemas`
  checks it for you later.
- **Wikilinks** — `[[daily-log]]` is a link to another note by filename. These
  are what the knowledge graph is built from (Hour 2). Obsidian renders them as
  clickable links; to Atlas OS they're graph edges.

**What you should see:** two new files under `wiki/`. Confirm:

```bash
ls "$VAULT_PATH/wiki/"
```

### Step 1.2 — Your first automated commit

Here's the first piece of automation. `atlas commit` looks at everything that
changed in your vault, writes a **categorised** commit message describing it, and
commits it to the vault's git repo. You never write the message yourself.

**Why this matters:** your notes become a diffable, recoverable history. Deleted
a paragraph last Tuesday? It's in git. Want to know what you added last month?
It's in the log. This is the single highest-value habit Atlas OS gives you, and
it's the first thing most people schedule (Hour 3).

Preview it first without committing anything:

```bash
atlas commit --dry-run
```

**What you should see:** the message it *would* use, something like:

```
vault: add wiki/ (2)
[dry-run] nothing committed
```

Now do it for real:

```bash
atlas commit
```

**What you should see:**

```
vault: add wiki/ (2)
committed a1b9f2c
```

That `a1b9f2c` is the git commit hash. Your two notes are now in version history.

> **If you see a git error** about the vault not being a repository: the wizard
> normally runs `git init` for you, but if you pointed at a pre-existing folder
> it may not have. Fix it with `cd "$VAULT_PATH" && git init`, then re-run
> `atlas commit`.

### Step 1.3 — See what changed with the changelog

`atlas changelog` summarizes vault activity over a time window — a human-readable
"what's new" rather than a raw git log.

```bash
atlas changelog --since 1d
```

**What you should see:** a short summary of notes added/changed in the last day,
grouped by folder. Add `--markdown` to get it formatted for pasting into a note,
or `--json` for machine consumption:

```bash
atlas changelog --since 7d --markdown
```

That's the core loop: **write notes → `atlas commit` → `atlas changelog`.**
Everything from here builds on top of it.

---

## Hour 2 — Knowledge management (20 min)

This is where a folder of notes becomes a *searchable second brain*. Two new
ideas: **embeddings** (for semantic search) and the **knowledge graph** (for
backlinks and related notes). Both need a local LLM, so we set that up first.

### What is RAG, and why a local LLM?

**RAG** stands for *Retrieval-Augmented Generation*. The retrieval half is what
we care about here: instead of searching your notes by exact keyword, Atlas OS
converts each chunk of text into a **vector** — a list of numbers that captures
its *meaning* — using an **embeddings model**. A search query gets the same
treatment, and Atlas OS returns the chunks whose vectors are closest in meaning.

The practical payoff: you can search for "how do I back up my notes" and find the
note that says "git history of the vault" — even though it shares no words with
your query.

To compute those vectors you need an **embeddings model**, and Atlas OS runs it
**locally** so your notes never leave your machine. Two easy options follow;
**you only need one.** LM Studio has a friendly GUI; Ollama is a clean CLI.

### Step 2.1a — Option 1: LM Studio (GUI)

1. **Install [LM Studio](https://lmstudio.ai/)** and open it.
2. In the **Search / Discover** tab, search for and download an embeddings
   model. **`nomic-embed-text`** is small, fast, and the recommended default.
   *(On screen: a list of models with download buttons; pick the nomic embed one
   and click download — it's a few hundred MB.)*
3. Go to the **Developer / Local Server** tab. Load the embeddings model, then
   click **Start Server**. *(On screen: a green "Running" indicator and a URL
   like `http://localhost:1234`.)*
4. Note the **port** it reports — LM Studio defaults to `1234`.

Now point Atlas OS at it. Edit `.env` and set:

```bash
EMBED_HOST=localhost
EMBED_PORT=1234                                      # match LM Studio's port
EMBED_MODEL=text-embedding-nomic-embed-text-v1.5     # the model you loaded
```

> If LM Studio was already running when you ran `atlas init`, the wizard
> auto-filled these for you and you can skip the edit.

### Step 2.1b — Option 2: Ollama (CLI)

1. **Install [Ollama](https://ollama.com/)**, then pull an embeddings model:

   ```bash
   ollama pull nomic-embed-text
   ```

2. **Start the server** (it serves an OpenAI-compatible API on port `11434`):

   ```bash
   ollama serve
   ```

3. Ollama's port `11434` is one Atlas OS probes automatically, so often there's
   nothing to configure. If you want to be explicit, set in `.env`:

   ```bash
   EMBED_MODEL=nomic-embed-text     # the model you pulled
   # EMBED_HOST / EMBED_PORT can be left unset to use the detected backend
   ```

### Step 2.2 — Confirm the backend is detected

Atlas OS auto-detects a backend by probing **LM Studio → Ollama → llama.cpp → any
OpenAI-compatible endpoint** and using the first that answers. Check what it
found:

```bash
atlas backends
```

**What you should see:** a list of backends with the active one marked, and its
models listed — e.g. `→ lmstudio  reachable  (text-embedding-nomic-embed-text-v1.5)`.

Run an actual inference to be sure the connection works end to end:

```bash
atlas backends test
```

**What you should see:** a one-line response from the model. If this errors, the
endpoint isn't really up — recheck that the server is running and the port
matches `.env`.

> **Running more than one backend?** Pin the one you want and skip probing:
> `export ATLAS_LLM_BACKEND=ollama` (values: `lmstudio | ollama | llamacpp |
> openai-compatible`). See
> [`EXAMPLES.md`](EXAMPLES.md#choosing--forcing-a-backend).

### Step 2.3 — A smoke test before the full build

Embedding a large vault takes a few minutes, so test the wiring on just 5 files
first:

```bash
atlas embed --test 5
```

**What you should see:** progress lines as it embeds a handful of chunks, ending
without errors. If this works, the full build will too.

### Step 2.4 — Build the full vector store

```bash
atlas embed --full
```

**What this does:** it walks every note in your vault, splits each into chunks,
sends every chunk to your local embeddings endpoint, and writes the resulting
vectors to **`$VAULT_PATH/.rag/vectors.json`**. Progress prints as it goes, and
it checkpoints — so if you stop it (or your laptop sleeps), re-running picks up
where it left off rather than starting over.

**What you should see:** a running count of embedded chunks, then a summary like
`Embedded 142 chunks from 2 notes → .rag/vectors.json`.

### Understanding `vectors.json`

`vectors.json` is the heart of search. It's a plain JSON file inside your vault's
`.rag/` directory containing, for every chunk of every note:

- the **text** of the chunk,
- its **vector** (the numeric meaning-fingerprint),
- and **metadata** (which note it came from, where).

Properties worth knowing:

- **It's derived data.** It's git-ignored and fully rebuildable from your notes —
  if it's ever lost or corrupted, `atlas embed --full` recreates it. Your notes
  are the source of truth; this is just an index.
- **It's local.** It lives in your vault folder and is never uploaded anywhere.
- **It's written atomically.** Atlas OS writes to a temp file and renames it into
  place, so a crash mid-write can't leave you with a half-written index.

Verify it exists and has real size:

```bash
ls -lh "$VAULT_PATH/.rag/vectors.json"
atlas doctor          # the "RAG index" line should now be green with a count
```

**What you should see:** a non-trivial file size, and the doctor's RAG/Embeddings
WARN lines flipped to `✓`.

### Step 2.5 — Keep the index fresh (incrementally)

After the first full build, you almost never need `--full` again. Embedding only
what changed is far faster:

```bash
atlas embed --incremental
```

This is exactly what the `nightly-rag-incremental` scheduled task runs for you
automatically (Hour 3 / Hours 5–24), so in practice you'll rarely type it by
hand.

### Step 2.6 — Build the knowledge graph

The other half of knowledge management is the **graph**. Remember the `[[...]]`
wikilinks from Hour 1? `atlas graph` scans every note, extracts those links, and
builds a map of *which note links to which* — so you (and agents, and the
dashboard) can answer "what links here?" and "what's related to this?"

```bash
atlas graph
```

**What this does:** writes `$VAULT_PATH/.rag/graph.json` — a list of **nodes**
(your notes) and **edges** (the wikilinks between them). Like `vectors.json`,
it's derived, git-ignored, and rebuildable.

**What you should see:** a summary like `Graph: 2 nodes, 2 edges → .rag/graph.json`
(the two notes you created link to each other, so two edges).

> The graph is rebuilt automatically after every `atlas embed --full` /
> `--incremental`, so you usually don't run `atlas graph` by hand either — but
> now you know what it produces and why.

At this point you have a vault that is **version-controlled** (Hour 1),
**semantically searchable** (`vectors.json`), and **linked** (`graph.json`).
Everything so far you ran by hand. Hour 3 makes it run itself.

---

## Hour 3 — Automation (15 min)

### What a "skill" and a "scheduled task" are

A **skill** in Atlas OS is a saved prompt — a `SKILL.md` file — that tells a
Claude Cowork agent how to do one job (e.g. "index the vault and write a morning
briefing"). A **scheduled task** is just a skill that Claude Cowork runs on a
cadence (nightly, weekday mornings, weekly).

The key insight: **Atlas OS provides the tools (`atlas embed`, `atlas commit`,
…), and Claude Cowork provides the scheduler that invokes them.** A scheduled
task is the glue: a prompt that calls the Atlas OS CLI, run automatically.

Atlas OS ships a library of ready-made skills so you don't write prompts from
scratch.

### Step 3.1 — Browse the available skills

```bash
atlas skills list
```

**What you should see:** the shipped skills with their suggested cadences, e.g.:

```
Agent skills (16 skill(s)):

  nightly-obsidian-index  [Nightly (~02:00)]
    Nightly vault index + morning briefing of what changed in your markdown vault.
  nightly-rag-incremental  [Nightly (after the index)]
    Incremental RAG embed of new/changed vault notes using a local embeddings endpoint.
  atlas-daily-report-email  [Daily (~09:30)]
    Daily morning report email — job-search status, system health, and action items.
  weekly-system-health-check  [Weekly]
    Weekly full system health check — tests all Atlas OS subsystems and emails a report.
  ...
```

Read any skill's full prompt before trusting it to run unattended:

```bash
atlas skills show nightly-obsidian-index
```

**What you should see:** the complete `SKILL.md` — its frontmatter and the exact
instructions the agent will follow. Always skim this so you're comfortable with
what a task will do.

### Step 3.2 — Install your first scheduled task

We'll start with the most valuable one: a **daily vault commit**, so your notes
get a git snapshot every day without you remembering to run `atlas commit`.
There's a dedicated indexing skill, but the simplest standalone version is the
commit itself. Let's install the nightly index skill, which includes the commit
plus a morning briefing:

```bash
atlas skills install nightly-obsidian-index
```

**What this does:** copies the skill's `SKILL.md` into your scheduled-tasks
directory (`$VAULT_PATH/.claude/skills/nightly-obsidian-index/` by default) and
fills in the `{{PLACEHOLDER}}` tokens — like `{{VAULT_PATH}}` and `{{ATLAS_OS}}` —
from your environment. It tells you which tokens (if any) it couldn't resolve so
you can fill them in by hand.

**What you should see:**

```
Installed nightly-obsidian-index → /Users/you/.../​.claude/skills/nightly-obsidian-index/SKILL.md
Resolved: VAULT_PATH, ATLAS_OS
(no unresolved placeholders)
```

### Step 3.3 — Register the cadence with Claude Cowork

Installing a skill puts the *prompt* in place; **Claude Cowork is what runs it on
a schedule.** Ask Cowork, in plain English, to run it nightly — for example:

> "Every night at 2am, run the `nightly-obsidian-index` skill in my atlas-os
> vault, and tell me in the morning what changed."

That's the whole mechanism. If you prefer the manual route, you can also just
schedule the bare command:

> "Every day at 6pm, run `atlas commit` in my atlas-os folder and summarise what
> changed."

> **No Claude Cowork subscription?** You can still get the automation by wiring
> the same commands into `cron` or `launchd` yourself — e.g. a nightly cron entry
> that runs `atlas embed --incremental && atlas commit`. Cowork just makes it
> conversational and adds the agent reasoning (briefings, triage, reports).

### Step 3.4 — Verify it ran: the audit trail

Here's the question Atlas OS is built to answer: **"What did the system do
overnight, and did it work?"** Every script-wrapping command (`embed`, `commit`,
`graph`, `changelog`, `health`, `trading`, `email`, `session`) appends one line to an
**append-only audit log** when it finishes — whether you ran it by hand or a
schedule did.

After your manual runs from Hours 1–2, you already have entries. Look at the most
recent ones:

```bash
atlas audit tail
```

**What you should see:** the last 5 actions in compact form, e.g.:

```
02:00:11  commit    scheduled  success  1.84s   3 new · 1 modified · a1b9f2c
02:00:09  embed     scheduled  success  47.2s   142 chunks
09:31:02  email     manual     success  0.91s   sent → you@example.com
```

For more detail or filtering:

```bash
atlas audit show                          # recent entries (default last 20)
atlas audit show --action commit --since 7d   # just commits, last week
```

**What you should see:** each entry records **what** ran (`action`), **how** it
was triggered (`scheduled` / `manual` / `cli`), the **outcome**, how long it
took, **what changed**, and any **error**. Under the hood each line is JSON:

```jsonl
{"timestamp":"2026-06-03T02:00:11.482+00:00","action":"commit","trigger":"scheduled","status":"success","duration_seconds":1.84,"changes":["3 new","1 modified","commit a1b9f2c"],"context":"atlas commit --json","error":null}
```

The log lives at `$VAULT_PATH/.atlas/audit.jsonl` (override with
`$ATLAS_AUDIT_PATH`), is appended under a file lock so concurrent runs are safe,
and auto-rotates at 10 MB. You can export it for compliance:

```bash
atlas audit export --format csv -o audit-report.csv
```

This is your morning ritual: `atlas audit tail` to see what happened while you
were away.

### Step 3.5 — Capture your Cowork sessions to the vault

Going autonomous cuts both ways: as agents do more of your work in Cowork, the
record of *what was done and why* lives in chat transcripts, not your notes.
`atlas session` folds those transcripts back into the vault so they're
searchable alongside everything else.

```bash
atlas session list          # see your recent Cowork sessions
atlas session save --all    # write a note for every session so far
```

**What this does:** for each session it writes
`$VAULT_PATH/sessions/session-log-YYYY-MM-DD-<title>.md` — frontmatter tagged
`[session-log, cowork]`, a summary, the key actions taken, and the files
modified — all extracted locally, no LLM call. A watermark in
`.atlas/last_session_save.txt` means a plain `atlas session save` only picks up
what's new, so it's safe to run daily.

To automate it, the recommended default is **twice daily** — a morning and an
afternoon capture, each covering a 12-hour window so your work lands in the vault
closer to when it happened:

```bash
atlas skills install morning-session-capture
atlas skills install afternoon-session-capture
```

> "Every morning at 9am run `morning-session-capture`, and every afternoon at
> 5pm run `afternoon-session-capture`, so my Cowork work is saved to my vault."

Both run `ATLAS_TRIGGER=scheduled atlas session save --since 12h`, so each capture
shows up in your audit trail as an unattended run — and the shared watermark
means the overlapping windows never double-write a session. Prefer a single
nightly run? Install `daily-session-capture` instead (it uses `--since 24h`).
Record your choice in `.env` with `SESSION_CAPTURE_FREQUENCY` (`twice` | `daily`
| `hourly` | `manual`).

The twice-daily pair is part of the [`knowledge` pack](SCHEDULED-TASKS.md), so
`atlas skills install-pack knowledge` sets both up alongside the nightly index and
RAG embed.

---

## Hour 4 — Communication (10 min)

So far everything reports to your terminal. Now let's have Atlas OS *email* you —
so the nightly work shows up in your inbox instead of you having to go look.

### Step 4.1 — Get a Gmail app password

Atlas OS sends mail through *your own* email account over SMTP. For Gmail you
can't use your normal password — you need a 16-character **app password**, and
2-Factor Authentication must be on first. Atlas OS only ever reads it from `.env`
at send time.

1. **Turn on 2FA:** go to
   [myaccount.google.com/security](https://myaccount.google.com/security) →
   **2-Step Verification** → follow the prompts.
2. **Create the app password:** go to
   [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords),
   name it `Atlas OS`, click **Create**. Google shows a 16-character password like
   `abcd efgh ijkl mnop`.

### Step 4.2 — Put it in `.env`

Copy the password **without the spaces** and set:

```bash
SENDER_EMAIL=your-account@gmail.com   # the Gmail account that sends the mail
SENDER_NAME=Atlas
SMTP_SERVER=smtp.gmail.com            # already the default
SMTP_PORT=587                         # already the default
SMTP_APP_PASSWORD=abcdefghijklmnop    # the 16 chars, no spaces
USER_EMAIL=you@example.com            # where reports get delivered
```

### Step 4.3 — Send your first email

```bash
atlas email --to you@example.com --subject "Atlas OS test" --body "<p>It works 🎉</p>"
```

**What you should see:** `sent → you@example.com`, and the message in your inbox
within a few seconds. It also lands as a `success` line in `atlas audit tail`.

> **If it fails,** the usual culprits are: a leftover space in the app password,
> 2FA not actually enabled, or `SENDER_EMAIL` not matching the account the app
> password belongs to. Plain-text body? Add `--text`. Attachments or a mailing
> list? Use `--json` with a payload (see
> [`EXAMPLES.md`](EXAMPLES.md#smtp-setup-gmail-app-password)).

Confirm the doctor agrees email is configured now:

```bash
atlas doctor       # the "Email (SMTP)" line should be green
```

### Step 4.4 — Install the daily report skill

Now connect email to the automation. The `atlas-daily-report-email` skill
compiles a morning report — what changed, system health, action items — and
emails it to you.

```bash
atlas skills show atlas-daily-report-email   # read what it sends first
atlas skills install atlas-daily-report-email
```

Then schedule it with Claude Cowork:

> "Every morning at 9:30, run the `atlas-daily-report-email` skill and email me
> the report."

**What you should see (tomorrow morning):** a report in your inbox, and a
matching `email` entry in `atlas audit show --action email`.

---

## Hours 5–24 — Going autonomous

You've done the hands-on part. Now Atlas OS earns its keep while you're not
watching. Here's what a fully set-up system does on its own, and how to stay on
top of it without micromanaging.

### What happens overnight

With the skills from Hours 3–4 scheduled, a typical night looks like:

- **~02:00 — `nightly-obsidian-index`:** indexes new/changed notes, syncs the
  wiki, appends the hot-topics cache, **commits the vault**, and writes a morning
  briefing.
- **Just after — `nightly-rag-incremental`:** embeds only the notes that changed
  since the last run, keeping `vectors.json` (and the graph) current — fast,
  because it's incremental.
- **~09:30 — `atlas-daily-report-email`:** emails you the morning report.
- **Weekly — `weekly-system-health-check`:** probes every subsystem, emails a
  health report, and auto-fixes safe issues.

Every one of these writes to the audit trail, so none of it is a black box.

### Your morning ritual (2 minutes)

When you sit down with coffee:

```bash
atlas audit tail        # what ran overnight, and did it succeed?
atlas health            # is every subsystem healthy right now?
```

**What you should see from `atlas health`:** an OK/DEGRADED line per subsystem
(RAG pipeline, vault git, embeddings endpoint, SMTP, …). `DEGRADED` is expected
for things you haven't installed (e.g. TTS, dashboard); investigate anything
unexpected. Want it machine-readable for a dashboard? `atlas health --json`.

If an overnight task **failed**, the audit entry has the error inline:

```bash
atlas audit show --status error --since 1d
```

…then re-run that one command by hand to see the full output (e.g. `atlas embed
--incremental`). The hardening built into the scripts means failures degrade
gracefully — you get a one-line reason, not a stack trace.

### Add more skills, progressively

Don't install everything at once. The healthy pattern is **index + RAG + health
first** (you've done index + RAG; add health below), then add others as a real
need shows up:

```bash
atlas skills install nightly-rag-incremental
atlas skills install weekly-system-health-check
```

Optional skills worth knowing about as your usage grows (all from `atlas skills
list`):

- `weekly-digest-report` — a weekly HTML digest of new notes, decisions, and
  research.
- `topic-research-brief` — multi-round web research synthesized into a cited
  vault note.
- `vault-lint-report` — finds orphan notes, dead wikilinks, and frontmatter gaps.
- `daily-trading-report` — runs analyst agents on a watchlist (needs the trading
  SDK; entirely optional).

When you add, remove, or edit a skill, re-sync the in-vault catalog so agents can
discover it:

```bash
atlas skills --sync     # regenerates "Skills Catalog.md" in your vault
```

> **Why the catalog matters:** it's a single note listing every skill this
> install ships. Because it's a normal vault note, any agent that searches your
> vault (via RAG) can see the full menu of automations it can invoke — without
> you describing them each time. It's auto-generated; don't hand-edit it.

### Tips for growing your vault organically

- **Write notes the way you think, not the way a schema demands.** The schemas
  are light guard-rails (`atlas schemas --dry-run` shows gaps); don't let them
  stop you capturing a thought.
- **Link liberally.** Every `[[wikilink]]` you add makes the knowledge graph
  richer and "related notes" smarter. Linking is cheap; a link to a note that
  doesn't exist yet is a fine to-do marker.
- **Let the nightly index do the housekeeping.** You write; it commits, embeds,
  and briefs. Resist running things by hand once they're scheduled.
- **Trust the audit trail.** If you're ever unsure whether something ran, don't
  guess — `atlas audit show` has the answer with a timestamp.
- **Keep confidential files out of the repo.** Job trackers, trading watchlists,
  and anything sensitive should live *outside* the vault git repo. See
  [`DATA-CLASSIFICATION.md`](DATA-CLASSIFICATION.md).

---

## What's next

You now have an autonomous, local-first knowledge system. Where to go from here:

- **The full skills menu** — [`SKILLS-CATALOGUE.md`](SKILLS-CATALOGUE.md) lists
  160+ skills across domains; [`SKILLS-FRAMEWORK.md`](SKILLS-FRAMEWORK.md) shows
  how to author your own `SKILL.md`.
- **Scheduled tasks reference** — [`SCHEDULED-TASKS.md`](SCHEDULED-TASKS.md) for
  every shipped task, its cadence, and its placeholder tokens.
- **The trading research SDK** — [`../trading/README.md`](../trading/README.md)
  for the optional multi-agent market-research module.
- **Tune everything** — [`CONFIGURATION.md`](CONFIGURATION.md) documents every
  environment variable; [`SCRIPTS.md`](SCRIPTS.md) is the full CLI reference.
- **Go deeper on internals** — [`features/`](features/README.md) explains how
  RAG, the graph, git automation, email, and health checks actually work.
- **Contribute** — [`../CONTRIBUTING.md`](../CONTRIBUTING.md) for guidelines (and
  the golden rule: never commit personal data).
- **Something broke?** — [`FAQ.md`](FAQ.md) for troubleshooting, or
  [`REBUILD.md`](REBUILD.md) for a clean reinstall.
- **Community & issues** — file bugs, request features, or ask questions at
  [github.com/paulholland511/atlas-os/issues](https://github.com/paulholland511/atlas-os/issues).

Welcome to your second brain. Now go write some notes — Atlas OS will take care
of the rest.
