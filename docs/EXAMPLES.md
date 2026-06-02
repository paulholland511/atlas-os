# Examples — Common Integrations

Beginner-friendly, copy-paste walkthroughs for the four things people set up
first. Each is self-contained; do them in any order.

- [SMTP setup (Gmail app password)](#smtp-setup-gmail-app-password)
- [LM Studio connection](#lm-studio-connection)
- [First scheduled task (daily vault backup)](#first-scheduled-task-daily-vault-backup)
- [First RAG embed](#first-rag-embed)

> All configuration lives in your `.env` file (copied from `.env.example`).
> After editing `.env`, the `atlas` CLI picks it up automatically — no need to
> re-source it.

---

## SMTP setup (Gmail app password)

Atlas OS sends reports and newsletters through your own email account over SMTP.
For Gmail you need a 16-character **app password** — your normal Google password
won't work, and Atlas OS never sees it (it reads it from `.env` at send time).

### Step 1 — Turn on 2-Factor Authentication

App passwords only exist once 2FA is enabled.

1. Go to **[myaccount.google.com/security](https://myaccount.google.com/security)**
2. Under **"How you sign in to Google"**, click **2-Step Verification**
3. Follow the prompts to turn it on (you'll confirm with your phone)

### Step 2 — Create an app password

1. Go to **[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)**
   (or: Security → 2-Step Verification → scroll to **App passwords**)
2. Give it a name like `Atlas OS`
3. Click **Create** — Google shows a **16-character** password like
   `abcd efgh ijkl mnop`

### Step 3 — Put it in `.env`

Copy the password **without the spaces** and set these values:

```bash
SENDER_EMAIL=your-atlas-account@gmail.com   # the Gmail account sending mail
SENDER_NAME=Atlas
SMTP_SERVER=smtp.gmail.com                   # already the default
SMTP_PORT=587                                # already the default
SMTP_APP_PASSWORD=abcdefghijklmnop           # the 16 chars, no spaces
USER_EMAIL=you@example.com                   # where reports are delivered
```

### Step 4 — Send a test email

```bash
atlas email --to you@example.com --subject "Atlas OS test" --body "<p>It works 🎉</p>"
```

> Prefer a raw payload (e.g. to attach files or send to a list)? Pass it with
> `--json`: `atlas email --json '{"to":"…","subject":"…","body_html":"…","attachments":["/path/file.pdf"]}'`.

Check your inbox. If it fails, the most common causes are: a space left in the
app password, 2FA not actually enabled, or `SENDER_EMAIL` not matching the
account the app password belongs to.

---

## LM Studio connection

RAG search and the trading SDK need a local, OpenAI-compatible LLM endpoint.
[LM Studio](https://lmstudio.ai/) is the easiest option (Ollama and llama.cpp
also work). Nothing leaves your machine.

### Step 1 — Install and download models

1. Install **[LM Studio](https://lmstudio.ai/)**
2. In the **search/discover** tab, download:
   - An **embeddings** model — `nomic-embed-text` (small, fast, recommended)
   - *(Optional, for trading)* a **chat** model — any small instruct model

### Step 2 — Start the local server

1. Open the **Developer / Local Server** tab in LM Studio
2. Load your embeddings model and click **Start Server**
3. Note the port it reports (LM Studio defaults to `1234`)

### Step 3 — Point Atlas OS at it

In `.env`, set the host/port to match LM Studio and the embeddings model name:

```bash
EMBED_HOST=localhost
EMBED_PORT=1234                                      # match LM Studio's port
EMBED_MODEL=text-embedding-nomic-embed-text-v1.5     # the model you loaded
```

> `atlas init` auto-probes the common ports (LM Studio `1234`, generic `5555`,
> Ollama `11434`) and fills these in for you if a server is already running.

### Step 4 — Test the connection

```bash
atlas embed --test 5     # embeds just 5 files as a smoke test
```

If it prints embedded chunks without errors, the endpoint is wired up correctly.
`atlas doctor` will also flip the **Embeddings** line to green.

---

## First scheduled task (daily vault backup)

A "scheduled task" in Atlas OS is just a command Claude Cowork runs on a cadence.
The simplest one with real value: a **daily vault backup** that commits every
change to git, giving you a full, diffable history of your notes.

### Step 1 — Run the backup manually

```bash
atlas commit          # stage + commit the vault with an auto-categorised message
atlas commit --dry-run   # preview the message without committing
```

`atlas commit` looks at which folders changed and writes a categorised message
(e.g. `vault: update research/ (3), wiki/ (1)`), then commits to your vault's
git repo. Run it once to confirm it works.

### Step 2 — Schedule it with Claude Cowork

Ask Claude Cowork, in plain English, to run it daily — for example:

> "Every day at 6pm, run `atlas commit` in my atlas-os folder and tell me what
> changed."

Claude Cowork registers it as a recurring task. That's the whole mechanism: a
scheduled task is a skill (a saved prompt) that calls the Atlas OS tooling.

### Step 3 — (Optional) use a pre-built skill

Atlas OS ships ready-made scheduled skills in [`skills/`](../skills/) — nightly
indexing, daily reports, weekly health checks. See
[`SCHEDULED-TASKS.md`](SCHEDULED-TASKS.md) for the catalog and how to install
one into Claude Cowork.

---

## First RAG embed

Once your [LM Studio endpoint](#lm-studio-connection) is up, build the search
index over your whole vault.

### Step 1 — Build the index

```bash
atlas embed --full
```

This chunks every note, sends each chunk to your local embeddings endpoint, and
writes the vectors to `.rag/vectors.json` inside your vault. For a large vault
this takes a few minutes; progress prints as it goes. It checkpoints, so you can
stop and resume.

> Running scripts directly instead of the CLI? `python3 scripts/embed_vault.py --full`
> does the same thing.

### Step 2 — Verify the vectors were created

```bash
atlas doctor          # the "RAG index" line should now be green with a count
```

Or check the file directly — it should exist and be non-trivial in size:

```bash
ls -lh "$VAULT_PATH/.rag/vectors.json"
```

### Step 3 — Keep it fresh

After the first full build, embed only what changed — far faster:

```bash
atlas embed --incremental
```

This is exactly what the `nightly-rag-incremental` scheduled skill runs for you
automatically. See [`SCHEDULED-TASKS.md`](SCHEDULED-TASKS.md).
