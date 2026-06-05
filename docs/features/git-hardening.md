# Git Sync Hardening

**Source:** [`atlas_os/git_sync.py`](../../atlas_os/git_sync.py),
[`atlas_os/frontmatter.py`](../../atlas_os/frontmatter.py),
[`atlas_os/filelock.py`](../../atlas_os/filelock.py),
[`atlas_os/gitutil.py`](../../atlas_os/gitutil.py),
[`atlas_os/fileio.py`](../../atlas_os/fileio.py)
**CLI:** `atlas sync`, `atlas validate`, `atlas doctor`

Atlas runs git against your vault unattended — the nightly auto-commit, session
capture, indexer touch-ups, and (when the vault has a remote) pulls from other
devices. The whole point of this module set is one guarantee:

> **An automated git operation must never corrupt or lose work you did by hand.**

The vault also lives in iCloud Drive and is edited concurrently by Obsidian, the
indexer, and the sync engine, so "hardening" here means defending against merge
conflicts, broken frontmatter, interleaved writes, dataless files, and stale
lock files — every way an unattended write can go wrong.

---

## 1. Safe merge — favour the human

`git_sync.safe_sync(vault_path)` pulls remote changes with a **favour-local**
strategy:

```bash
atlas sync                 # pull origin/<current-branch>, favouring local
atlas sync --remote origin --branch main
atlas sync --json
```

Under the hood it runs `git merge -X ours`: where a remote (or automated) change
and a concurrent **human** edit touch the same hunk, the **local side wins**.
Non-conflicting remote changes still merge normally, so edits from your other
devices are preserved — you only ever lose the *automated* side of a true
conflict, never your own.

If a merge cannot be resolved even with `-X ours` (a structural conflict such as
modify/delete or rename/rename), `safe_sync`:

1. **aborts** the merge (`git merge --abort`) — your working tree is left exactly
   as it was;
2. records the conflict and the affected files in the **audit trail**;
3. returns `status="conflict"` so the CLI can alert you to resolve it by hand.

It **never** force-resolves against you (`-s ours` / `-X theirs` are never used
on user files). The result object:

| `status` | meaning |
|---|---|
| `up_to_date` | nothing to pull |
| `synced` | remote changes merged cleanly (local wins on conflict) |
| `conflict` | unresolvable — merge aborted, tree untouched, files listed |
| `skipped` | not a git repo, or no remote/branch |
| `error` | git failed unexpectedly (detail in `message`) |

Exit code is `0` for `synced`/`up_to_date`/`skipped`, `1` for `conflict`/`error`.

---

## 2. Frontmatter validation gate

Before **any** automated commit, every touched Markdown file's YAML frontmatter
is validated. A single malformed automated edit would propagate into the vault
and break RAG chunking, the dashboard, and Obsidian's property rendering, so this
is a **hard precondition** — no commit proceeds with frontmatter it broke.

```bash
atlas validate                 # scan every note in the vault
atlas validate --staged        # only git-staged files (use as a pre-commit hook)
atlas validate --require id,title
atlas validate --json
```

`frontmatter.validate_before_commit(vault_path)` checks each staged `.md` file for:

- **well-formed YAML** that parses to a mapping (not a list or scalar);
- **required keys** present (configurable; none by default, so existing notes
  aren't retroactively rejected);
- **valid dates** in `date`/`created`/`updated`/`modified` — a YAML date or an
  ISO-8601 string, not `"yestrday"`;
- a **terminated** frontmatter block (opening `---` with a matching closing `---`).

A file with *no* frontmatter is valid — plenty of notes are plain Markdown. Only a
block that is *present but broken* fails. `report.ok` is the gate: if any file is
invalid the commit is aborted, the prior content left in place, and the failure
logged.

---

## 3. File locking for concurrent writes

`filelock` serialises vault writers (the indexer vs. the sync engine vs. session
capture) so they don't interleave writes to the same note:

```python
from atlas_os.filelock import vault_lock

with vault_lock(note_path):
    note_path.write_text(new_body)
```

- **Atomic acquisition** — a sibling `<name>.lock` created with `O_EXCL` (atomic
  "create only if absent" on every POSIX filesystem, including iCloud).
- **Retry with backoff** — `acquire_lock(path, timeout=10)` polls with exponential
  backoff, then raises `LockTimeout` rather than blocking forever.
- **Stale-lock recovery** — a lock whose mtime is older than **5 minutes** is
  assumed abandoned by a crashed process and reclaimed, so the system self-heals.
- **Diagnostics** — the lock file records the owner pid and an ISO-8601 timestamp.

---

## 4. iCloud compatibility — wait for fault-in

The vault is iCloud-backed, so a file may be **dataless** (offloaded): present in
the listing but with no local content. A naive read stalls or returns partial
data. `fileio.ensure_materialized(path, timeout=30)`:

1. returns immediately if the file is already local (the common case, and always
   true on Linux/CI where nothing is dataless);
2. otherwise triggers the download (`brctl download`, best-effort) and **polls**
   `is_dataless` until the file materialises or the timeout elapses;
3. returns `False` if it never materialises, so the caller **skips and logs**
   rather than reading garbage.

See the documented iCloud `.venv`/`.pth` hazards for this repo — the same
dataless-file failure mode this guards against.

---

## 5. Stale git-lock cleanup

A crashed git process leaves `.git/index.lock` (or `HEAD.lock`, ref locks) behind,
which makes *every* subsequent git command fail with *"Another git process seems
to be running"*. `gitutil.clean_stale_locks(repo)` removes only locks **older than
5 minutes** — a fresh lock probably belongs to a live process and is left alone,
so cleanup never yanks a lock out from under a running command.

`safe_sync` calls it before touching the index, and it's wired into
`atlas doctor --fix` (a *safe* fix, applied automatically):

```bash
atlas doctor          # reports stale locks under "Git"
atlas doctor --fix    # clears them (plus other safe fixes)
```

---

## 6. Sync health in `atlas doctor`

`atlas doctor` grows a **Sync** category:

- **Last sync** — the timestamp of the last successful `sync` action from the
  audit trail (WARN if none recorded yet).
- **Conflicts** — any files left in an unresolved (unmerged) state, so a stuck
  merge surfaces instead of silently blocking future syncs.

---

## Audit & observability

Every aborted write, conflict, stale-lock removal, and sync outcome is appended to
the JSONL **audit trail** (`atlas_os/audit.py`) with the file, reason, and outcome:

```bash
atlas audit show --action sync
atlas audit tail
```

---

## Testing

- [`tests/test_git_sync.py`](../../tests/test_git_sync.py) — races a simulated
  remote change against a concurrent local edit (favour-local wins; unresolvable
  conflict aborts with the tree intact) plus iCloud fault-in.
- [`tests/test_frontmatter.py`](../../tests/test_frontmatter.py) — the validation
  gate (broken YAML, unterminated blocks, missing keys, bad dates).
- [`tests/test_filelock.py`](../../tests/test_filelock.py) — acquire/release,
  contention timeout, stale recovery, context manager.
- [`tests/test_gitutil.py`](../../tests/test_gitutil.py) — age-aware lock cleanup.
