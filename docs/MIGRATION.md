# Migration Guide — v0.3.0 → v1.0

This guide covers upgrading an existing Atlas OS install from **v0.3.0** to
**v1.0**. The short version:

> **v1.0 is fully backward compatible with v0.3.0.** There are **no breaking
> changes** — your existing `.env`, vault, and scheduled skills keep working
> untouched. Everything below is additive. The recommended upgrade is three
> commands:
>
> ```bash
> pip install --upgrade atlas-os   # or: pipx upgrade atlas-os
> atlas doctor --fix               # validate the setup, auto-fix safe issues
> atlas embed --incremental        # refresh the RAG index
> ```

If you only do the above, you're done. The rest of this document explains what's
new and why you might want to use it.

---

## Recommended upgrade steps

1. **Upgrade the package.**

   ```bash
   pip install --upgrade atlas-os
   ```

   If you installed with `pipx`, use `pipx upgrade atlas-os`. If you run from a
   source checkout, `git pull` then `pip install -e ".[all]"`. Verify:

   ```bash
   atlas --version
   ```

2. **Run the doctor with auto-fix.** v1.0's `atlas doctor` diagnoses far more
   than v0.3.0 and can repair safe problems for you:

   ```bash
   atlas doctor --fix
   ```

   This clears stale git locks automatically and prompts before any unsafe
   remediation (running the init wizard, creating the vault's first commit). Add
   `--json` if you want machine-readable output.

3. **Refresh the RAG index.** Re-embed any notes that changed while you were on
   v0.3.0:

   ```bash
   atlas embed --incremental
   ```

That's the whole upgrade. Nothing in your configuration needs to change.

---

## No breaking changes

v1.0 keeps every v0.3.0 contract:

- **Your `.env` is unchanged.** Every variable v0.3.0 read is still read with the
  same meaning. The new variables below are all optional with sensible defaults.
- **Explicit settings still win.** The new pluggable-backend detection only kicks
  in when you *haven't* set the endpoint explicitly — your existing `EMBED_*` and
  `LM_STUDIO_*` values continue to take precedence, so a working v0.3.0 setup
  behaves identically.
- **Command names, flags, exit codes, and JSON output shapes are stable.** As of
  v1.0 these form a documented stability contract (see
  [`CLI-REFERENCE.md`](CLI-REFERENCE.md)); a breaking change to any of them now
  requires a major version bump.
- **Your installed/scheduled skills keep running.** Existing copies under
  `SCHEDULED_DIR` are untouched.

---

## What's new in v1.0

### New features

- **Interactive `atlas init` wizard.** First-run onboarding is now a guided
  wizard: it suggests a vault default, auto-detects your local LLM, optionally
  collects SMTP settings, generates `.env`, scaffolds the vault tree, and runs
  `atlas doctor`. `--yes` accepts every default for a non-interactive run. You
  don't need this to upgrade — it's for fresh setups — but `atlas doctor --fix`
  can offer to run it if your config is incomplete.
- **`atlas doctor` — diagnose and fix.** The doctor now groups checks by category
  (Config / Git / LLM / RAG / SMTP), colour-codes each row, and prints an
  actionable next step for anything that isn't OK. New checks cover stale git
  locks, LLM backend reachability, RAG freshness, iCloud file offloading, and
  SMTP configuration. See the new flags below.
- **Pre-built skill packs.** Install a complete workflow in one command instead
  of installing skills one at a time. Three packs ship — `knowledge`,
  `communication`, and `trading`. List them with `atlas skills packs` and install
  one with `atlas skills install-pack <name>`. See
  [`SKILLS-FRAMEWORK.md`](SKILLS-FRAMEWORK.md#skill-packs).
- **End-to-end integration test suite.** A full-pipeline test layer
  (`pytest -m integration`) exercises real command flows; unit and integration
  tests can be run separately. Relevant if you develop against Atlas OS.
- **Hardened pipeline scripts.** Every script under `scripts/` now degrades
  gracefully — network timeouts, retries with backoff, atomic file writes, and
  safe git operations — instead of dumping a traceback. This is transparent at
  runtime; no configuration needed.
- **Pluggable LLM backends.** Atlas OS auto-detects any OpenAI-compatible server
  (LM Studio → Ollama → llama.cpp → a custom URL) and uses the first that
  responds. Explicit endpoint settings still win, so existing setups are
  unchanged. Inspect with `atlas backends` and `atlas backends test`.
- **Audit trail.** Every autonomous action appends one JSON line to an
  append-only, rotating audit log. Inspect it with `atlas audit show` / `tail` /
  `export`.

### New CLI flags & subcommands

| Command | New | What it does |
|---|---|---|
| `atlas doctor` | `--fix` | Auto-applies safe remediations (e.g. clearing stale git locks), prompts for unsafe ones. |
| `atlas doctor` | `--json` | Emits the full report as `{checks, summary}` for programmatic use. |
| `atlas skills` | `packs` | Lists the curated skill packs with their members and counts. |
| `atlas skills` | `install-pack <name>` | Installs every skill in a pack at once (`--force` to overwrite existing). |

(For reference, `atlas skills install` / `list` / `show` and `atlas backends` /
`atlas audit` arrived during the 0.x line and are also part of v1.0; see the full
[`CLI-REFERENCE.md`](CLI-REFERENCE.md).)

### New modules

These are internal building blocks — you don't call them directly, but they're
why v1.0's scripts are more robust. Listed here for contributors:

| Module | Purpose |
|---|---|
| [`atlas_os/retry.py`](../atlas_os/retry.py) | `RetryPolicy` + `retry` decorator / `retry_call` for exponential-backoff retries with an injectable `sleep`. |
| [`atlas_os/netio.py`](../atlas_os/netio.py) | HTTP with explicit connect/read timeouts and retries on transient failures (`429`/`5xx`). |
| [`atlas_os/fileio.py`](../atlas_os/fileio.py) | Atomic file writes (write-temp-then-rename) so an interrupted run can't corrupt state. |
| [`atlas_os/gitutil.py`](../atlas_os/gitutil.py) | Safe git helpers, including stale-lock detection used by `atlas doctor`. |
| [`atlas_os/scriptkit.py`](../atlas_os/scriptkit.py) | Shared script scaffolding for graceful degradation and consistent error handling. |
| [`atlas_os/packs.py`](../atlas_os/packs.py) | The skill-pack registry and installer behind `atlas skills packs` / `install-pack`. |

### New environment variables

All optional — every one has a default or is only needed for an opt-in feature.
Your v0.3.0 `.env` needs no edits.

| Variable | Default | Purpose |
|---|---|---|
| `ATLAS_LLM_BACKEND` | _auto-detect_ | Force a backend (`lmstudio` / `ollama` / `llamacpp` / `openai-compatible`), skipping detection. |
| `ATLAS_LLM_MODEL` | backend default | Override the chat model name. |
| `ATLAS_LLM_API_KEY` | _unset_ | API key for an OpenAI-compatible backend that requires one. |
| `OPENAI_COMPATIBLE_URL` | _unset_ | Base URL for a custom OpenAI-compatible server (the last backend tried). |
| `ATLAS_SKILLS_DIR` | `$VAULT_PATH/.claude/skills` | Where `atlas skills install` / `install-pack` write installed skills. |
| `ATLAS_AUDIT_PATH` | `$VAULT_PATH/.atlas/audit.jsonl` | Location of the append-only audit log. |
| `ATLAS_TRIGGER` | `cli` | Tags an action's trigger in the audit trail; scheduled tasks set `ATLAS_TRIGGER=scheduled`. |

See [`CONFIGURATION.md`](CONFIGURATION.md) for the complete environment-variable
reference.

---

## Rolling back

If you need to return to v0.3.0:

```bash
pip install "atlas-os==0.3.0"
```

Because v1.0 writes nothing your v0.3.0 install can't read — the audit log and
installed packs are additive files — downgrading is safe. The audit trail and any
packs you installed simply go unused until you upgrade again.

---

## See also

- [`CLI-REFERENCE.md`](CLI-REFERENCE.md) — the complete command/flag/env-var
  stability contract.
- [`CONFIGURATION.md`](CONFIGURATION.md) — every environment variable.
- [`SKILLS-FRAMEWORK.md`](SKILLS-FRAMEWORK.md) — skills and skill packs.
- [`../CHANGELOG.md`](../CHANGELOG.md) — the full release history.
