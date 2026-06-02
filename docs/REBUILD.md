# Rebuild Guide

How to stand the whole system back up from nothing — on a new machine, after a
wipe, or when onboarding a fresh vault. This is the disaster-recovery and
clean-install runbook. It assumes you have this repo and your (separately
backed-up) vault.

## 0. What you need

- This repo
- Your **vault** (its own backup/repo — Atlas OS never stores it)
- Your secrets (SMTP app password, any API keys) from your password manager
- *(Optional)* your local LLM installed

## 1. System prerequisites

```bash
# Python + git
python3 --version            # 3.11+
git --version

# (Optional) local LLM — install LM Studio or Ollama and load:
#   - an embeddings model (e.g. nomic-embed-text)
#   - a chat model
```

## 2. Repo + environment

```bash
# Install the package (gives you the `atlas` command):
uv tool install "atlas-os[all] @ git+https://github.com/paulholland511/atlas-os"
#   or from a clone:  git clone … && cd atlas-os && pip install -e ".[all]"

atlas init        # detect LLM, write .env, scaffold/refresh the vault skeleton
```

## 3. Restore the vault

```bash
# Restore from your backup to $VAULT_PATH, then ensure it's a git repo:
cd "$VAULT_PATH"
git status 2>/dev/null || (git init && git add -A && git commit -m "Restore vault")
cd -
```

If starting fresh instead, follow steps 4–5 of [`SETUP.md`](SETUP.md) to lay
down the skeleton.

## 4. Rebuild derived data

Everything below is **regenerated** from the vault — none of it is backed up or
committed, by design.

```bash
atlas schemas             # frontmatter consistency
atlas embed --full        # full RAG re-embed (needs the local LLM) — also rebuilds the graph
atlas skills --sync       # regenerate the Skills Catalog note in the vault
```

## 5. Restore secrets & credentials

- Put `SMTP_APP_PASSWORD`, `SENDER_EMAIL`, `USER_EMAIL`, and any API keys back
  into `.env` (from your password manager). **Never** restore them into notes or
  code.

## 6. Reinstall automations

- Copy the skill folders from `skills/` into your Claude scheduled-tasks
  directory, re-substitute the `{{PLACEHOLDER}}` tokens, and re-register them on
  the cadences in [`SCHEDULED-TASKS.md`](SCHEDULED-TASKS.md).
- Reinstall `~/CLAUDE.md` from `templates/CLAUDE.md.template`.
- Restore your memory directory (`MEMORY.md` + memory files).

## 7. Verify

```bash
atlas doctor      # setup validation
atlas health      # full subsystem probe
```

Aim for every subsystem UP (or DEGRADED where a component is intentionally not
installed, e.g. TTS or the dashboard).

## Recovery order summary

```
prerequisites → repo+env → vault → derived data (schemas, RAG, graph)
            → secrets → automations + CLAUDE.md + memory → verify
```

The key idea: **the vault is the source of truth; everything else is
reproducible.** Back up the vault and your secrets; rebuild the rest.
