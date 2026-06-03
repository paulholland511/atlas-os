# Skills Framework

A **skill** is the unit of automation in Atlas OS. It is a directory under
`skills/<slug>/` containing a single `SKILL.md` file: YAML frontmatter followed
by a Markdown prompt body of step-by-step instructions an agent follows. Skills
are Claude Cowork prompts — Claude Cowork runs them on a schedule or on demand,
and each one orchestrates the Atlas Python tooling (`atlas embed`,
`atlas commit`, `atlas graph`, `atlas health`, `atlas email`, `atlas trading`)
together with connected MCP tools (email, web search, files). Because they run
**unattended**, skills are written to make reasonable choices and carry on
rather than stopping to ask questions.

This document explains the anatomy of a `SKILL.md`, the lifecycle a skill moves
through (creation → installation → scheduling → execution → audit logging), how
skills are catalogued for agent discovery, and how to author your own.

---

## Anatomy of a `SKILL.md`

A `SKILL.md` has two parts: a small YAML frontmatter block and a Markdown body.

### Frontmatter

```yaml
---
name: nightly-rag-incremental
description: Incremental RAG embed of new/changed vault notes using a local embeddings endpoint.
---
```

| Key | Required | Purpose |
|---|---|---|
| `name` | yes | Kebab-case slug. **Must match the directory name** (`skills/<slug>/`). It is the skill's stable identifier. |
| `description` | yes | One line. Summarises what the skill does. Surfaced in the catalog and indexed for RAG discovery, so write it for a reader scanning a menu of automations. |

The frontmatter is the single source of truth for the catalog (see below), so it
is parsed verbatim — keep it to these two keys.

### Body

The body is the prompt the agent executes. It is plain Markdown and typically
contains:

- A one-line **objective**.
- A **placeholders note** listing the `{{PLACEHOLDER}}` tokens the skill uses.
- **Numbered steps**, each naming the exact tool or script to call (e.g. a
  `python3 {{ATLAS_OS}}/scripts/...` invocation, an `atlas ...` command, or an
  MCP action) and what to do with its output.
- **Constraints / failure handling** — what *not* to do, and how to degrade
  gracefully when something is unreachable (log and skip rather than corrupt
  state).
- A **sign-off** — the report the skill emits when it finishes.

Anything user- or machine-specific is written as a `{{PLACEHOLDER}}` token, never
hard-coded, so the same `SKILL.md` is portable across installs.

### Placeholder tokens

| Token | Meaning |
|---|---|
| `{{VAULT_PATH}}` | Absolute path to the knowledge vault directory. |
| `{{ATLAS_OS}}` | Absolute path to the Atlas OS repository (where scripts live). |
| `{{USER_EMAIL}}` | Recipient address for reports the skill emails. |
| `{{EMBED_HOST}}` / `{{EMBED_PORT}}` | Host and port of the local embeddings endpoint. |
| `{{LLM_PORT}}` | Port of the local chat-completions endpoint. |
| `{{OUTPUT_DIR}}` | Directory the skill writes generated artefacts into. |
| `{{WATCHLIST}}` | Symbols/topics a monitoring skill should track. |

> **Credentials are never tokens and never inlined.** Email skills read
> `SMTP_APP_PASSWORD` and `SENDER_EMAIL` from the environment at run time. See
> [Safety notes](#safety-notes) and [`../SECURITY.md`](../SECURITY.md).

---

## The skill lifecycle

Every skill moves through five stages.

### 1. Creation

Author a `skills/<slug>/SKILL.md` — frontmatter plus a numbered-step body using
`{{PLACEHOLDER}}` tokens. The recommended way to scaffold one is the
**skill-creator** meta-skill (see [Creating a custom skill](#creating-a-custom-skill)),
which generates the frontmatter, a step skeleton, and the placeholder tokens for
you. After creating it, re-sync the catalog so the new skill becomes
discoverable.

### 2. Installation

Install a skill by copying its `skills/<slug>/` directory into the Claude
scheduled-tasks directory (`SCHEDULED_DIR`, default
`~/Documents/Claude/Scheduled`) and **replacing every `{{PLACEHOLDER}}` token**
with the concrete value for this machine. The copy in `SCHEDULED_DIR` is the
runnable instance; the copy in the repo stays generic and tokenised.

### 3. Scheduling

Register a cadence for the installed skill so Claude Cowork knows when to run it.
Cadences (nightly / daily / weekly) are **suggestions** — pick what fits your
workflow. See [`SCHEDULED-TASKS.md`](SCHEDULED-TASKS.md) for the recommended
cadence per shipped skill and how to register it.

### 4. Execution

At the scheduled time (or on demand), Claude Cowork runs the skill's body as a
prompt. The agent follows the numbered steps, invokes the Atlas tooling and MCP
tools they name, and — because skills run unattended — resolves ambiguity by
making a reasonable choice rather than pausing. Each step that wraps a pipeline
command goes through the audited Atlas CLI.

### 5. Audit logging

Every autonomous action Atlas runs appends **one JSON line** to an append-only,
tamper-evident audit trail at `$ATLAS_AUDIT_PATH`
(default `<vault>/.atlas/audit.jsonl`). Each entry records:

- `timestamp` — ISO 8601 UTC
- `action` — what ran (e.g. `embed`, `commit`, `email`)
- `trigger` — `scheduled` | `manual` | `cli`
- `status` — `success` | `error` | `skipped`
- `duration_seconds`
- `changes[]` — what the action touched
- `context` — why it ran
- `error` — populated on failure

Appends are serialised with an in-process lock plus an OS advisory file lock, and
the file rotates at 10 MB (`audit.jsonl.1`, `.2`, …). Inspect the trail with:

```bash
atlas audit show          # recent entries (filterable by --action / --since / --limit)
atlas audit tail          # the last 5 entries, compact
atlas audit export        # dump to CSV or JSON (for compliance reporting)
```

This append-only trail supports ISO 27001 control **A.12.4** (logging &
monitoring).

---

## The skills catalog & agent discovery

So that agents (and you) can see the full menu of automations at a glance, Atlas
OS maintains a generated catalog. `atlas_os/_skills.py` parses the frontmatter of
every `skills/*/SKILL.md` and renders a `Skills Catalog.md` note into the vault.
The note carries `type: reference` frontmatter so the RAG indexer picks it up.

Because the catalog is built from each skill's frontmatter, it never drifts from
the skills themselves. It is **auto-generated — never hand-edit it.**

```bash
atlas skills          # list the catalog in the terminal
atlas skills --sync   # regenerate <vault>/Skills Catalog.md
```

`atlas init` generates the catalog on first setup. Re-run `atlas skills --sync`
after adding, editing, or removing a skill so the catalog and the RAG index stay
current.

For the rendered catalog of the skills this install ships, see
[`SKILLS-CATALOGUE.md`](SKILLS-CATALOGUE.md).

---

## Skill packs

A **pack** is a curated bundle of related skills that together set up a complete
workflow, so you can install an entire workflow in one command instead of
installing each skill one at a time. Packs are defined in `atlas_os/packs.py` —
a registry mapping a pack name to a description and an ordered list of skill
slugs. Installing a pack simply runs the per-skill installer
([stage 2 of the lifecycle](#2-installation)) for every member, with the same
`{{PLACEHOLDER}}` substitution; an already-installed member is skipped unless you
pass `--force`.

The three packs this install ships:

| Pack | Skills | Sets up |
|---|---|---|
| `knowledge` | `nightly-obsidian-index`, `nightly-rag-incremental`, `weekly-rag-full-reembed`, `vault-lint-report`, `weekly-digest-report` | Vault management — nightly commit & index, incremental + full RAG re-embedding, lint reports, and the weekly digest. |
| `communication` | `atlas-daily-report-email`, `inbox-triage-digest`, `generate-vault-report-doc` | Email & reporting — daily report email, inbox-triage digest, and vault report docs. |
| `trading` | `daily-trading-report`, `topic-research-brief` | Trading intelligence — daily trading report and on-demand topic research briefs. |

```bash
atlas skills packs                  # list the packs with their members and counts
atlas skills install-pack knowledge # install the whole knowledge workflow at once
atlas skills install-pack trading --force  # reinstall, overwriting existing copies
```

Every slug a pack names must be a real skill under `skills/` —
`atlas_os.packs.validate_packs()` enforces this, and the test-suite asserts it,
so a typo in the registry fails CI rather than at install time. To add a pack,
append an entry to `PACKS` in `atlas_os/packs.py` listing existing skill slugs;
to add a skill to a pack, add its slug to that pack's `skills` tuple.

---

## How skills reach sub-agents

There is no separate injection step or registry call. The `Skills Catalog.md`
note is **RAG-indexed reference content** in the vault. Sub-agents discover
skills the same way they discover anything else they need:

1. An agent reads `Skills Catalog.md`, or runs a vault/RAG search, to find a
   skill whose `description` matches the task at hand.
2. The catalog entry gives the skill's `name` and what it does; the agent then
   opens the corresponding `skills/<slug>/SKILL.md` to read and follow its steps.

This keeps discovery decentralised and self-describing: adding a skill and
re-running `atlas skills --sync` is all it takes for every agent to be able to
find and invoke it.

---

## Creating a custom skill

The recommended path is the **skill-creator** meta-skill — a skill whose job is
to scaffold other skills. It produces the frontmatter, a numbered-step skeleton,
and the placeholder tokens, leaving you to fill in the specifics.

1. **Scaffold.** Run the **skill-creator** meta-skill, describing what the new
   skill should automate. It generates a `skills/<slug>/SKILL.md` with valid
   frontmatter and a step skeleton.
2. **Set the slug.** Ensure the directory name and the `name` frontmatter value
   match (kebab-case).
3. **Write the description.** One clear line — it is what agents see when
   discovering the skill.
4. **Fill in the steps.** Name the exact `atlas …` commands, scripts, and MCP
   tools to call, and use `{{PLACEHOLDER}}` tokens for anything machine- or
   user-specific. Add constraints and graceful-failure handling.
5. **Add a sign-off** describing the report the skill emits when done.
6. **Sync the catalog.** Run `atlas skills --sync` so the new skill is
   catalogued and RAG-indexed.
7. **Install & schedule.** Copy `skills/<slug>/` into `SCHEDULED_DIR`, replace
   the tokens, and register a cadence (see [the lifecycle](#the-skill-lifecycle)
   and [`SCHEDULED-TASKS.md`](SCHEDULED-TASKS.md)).

For the bigger picture of how skills, scheduling, and the audit trail fit
together, see
[`features/skills-and-automation.md`](features/skills-and-automation.md).

---

## `SKILL.md` template

Copy this into `skills/<your-slug>/SKILL.md`, rename to taste, and replace the
tokens.

```markdown
---
name: your-skill-slug
description: One line describing what this skill automates (used for discovery).
---

Run <one-line objective of this skill>.

> Placeholders: `{{VAULT_PATH}}` = your vault path, `{{ATLAS_OS}}` = the Atlas OS
> repo path, `{{USER_EMAIL}}` = report recipient.

**Objective:** <what a successful run achieves>.

**Steps:**

1. Request access to `{{VAULT_PATH}}`, then gather the inputs this skill needs.
2. Run the relevant Atlas tooling, for example:
   ```bash
   ATLAS_OS={{ATLAS_OS}} atlas health
   ```
   and act on its output. Make a reasonable choice on ambiguity — do not stop to
   ask.
3. Email the result to `{{USER_EMAIL}}` (SMTP credentials are read from the
   environment as `SMTP_APP_PASSWORD` / `SENDER_EMAIL`, never written here):
   ```bash
   ATLAS_OS={{ATLAS_OS}} atlas email --to {{USER_EMAIL}} --subject "..." --body-file <report>
   ```

**Constraints:**
- Do NOT modify vault notes unless that is the skill's stated purpose.
- If a dependency is unreachable, log the error and skip — never corrupt state.

**Sign-off:** Report what ran, what changed, and any errors, in one short
summary.
```

---

## Safety notes

- **Unattended execution.** Skills run without a human in the loop. Write them to
  fail safe: validate inputs, prefer skip-and-log over destructive fallbacks, and
  state explicit constraints so an autonomous run can't wander into unintended
  changes. Every run is captured in the audit trail
  ([stage 5 above](#5-audit-logging)) — review `atlas audit show` periodically.
- **Never inline credentials.** Secrets are not placeholder tokens and must never
  appear in a `SKILL.md`. Email skills read `SMTP_APP_PASSWORD` and
  `SENDER_EMAIL` from the environment at run time. The same applies to API keys
  and tokens for any MCP tool — keep them in the environment, not in the prompt.
- **Keep confidential files out of the repo.** `SKILL.md` files in `skills/` are
  generic and tokenised by design. Concrete paths, recipients, watchlists, and
  any private data belong only in the **installed** copy under `SCHEDULED_DIR`,
  not in version control. See [`../SECURITY.md`](../SECURITY.md) for the full
  policy.
