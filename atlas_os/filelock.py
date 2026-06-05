"""Advisory file locking for vault writes.

Atlas runs several writers against the same knowledge vault — the RAG indexer
embeds notes, the sync engine merges remote changes, session capture appends to
daily notes. When two of them touch the *same* file at the same time the later
write can silently clobber the earlier one. This module serialises those writers
with a simple, portable, **advisory** lock: a sibling ``<name>.lock`` file
created with ``O_EXCL`` (an atomic "create only if absent" on every POSIX
filesystem, including the iCloud-backed vault).

Design notes
------------
* **Atomic acquisition.** ``os.open(..., O_CREAT | O_EXCL)`` is the lock — only
  one process can win the create; everyone else gets ``FileExistsError`` and
  retries.
* **Retry with backoff.** :func:`acquire_lock` polls with exponential backoff up
  to ``timeout`` seconds, then raises :class:`LockTimeout` rather than blocking
  forever. The ``sleep`` function is injectable so tests run instantly.
* **Stale-lock recovery.** A process that crashes while holding a lock would wedge
  every future writer. A lock file whose mtime is older than
  :data:`STALE_AFTER_SECONDS` (5 minutes) is treated as abandoned and removed, so
  the system self-heals after a crash.
* **Diagnostics.** The lock file records the owner pid and an ISO-8601 timestamp,
  so a human (or ``atlas doctor``) can see who holds it and since when.

Usage::

    from atlas_os.filelock import vault_lock

    with vault_lock(note_path):
        note_path.write_text(new_body)
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# A lock whose mtime is older than this is assumed abandoned by a dead process
# and is reclaimed. Five minutes comfortably exceeds any legitimate single write.
STALE_AFTER_SECONDS = 300.0

# Defaults for :func:`acquire_lock`.
DEFAULT_TIMEOUT = 10.0
_INITIAL_BACKOFF = 0.05
_MAX_BACKOFF = 0.5


class LockTimeout(TimeoutError):
    """Raised when a lock could not be acquired within the timeout."""


def lock_path_for(path: Path) -> Path:
    """Return the sibling lock-file path Atlas uses to guard ``path``."""
    return path.with_name(path.name + ".lock")


def _is_stale(lock: Path, now: float) -> bool:
    """True if ``lock`` exists and is older than :data:`STALE_AFTER_SECONDS`."""
    try:
        age = now - lock.stat().st_mtime
    except OSError:
        return False
    return age > STALE_AFTER_SECONDS


def _reclaim_if_stale(lock: Path, now: float) -> bool:
    """Remove ``lock`` if it is stale; return ``True`` if it was reclaimed."""
    if not _is_stale(lock, now):
        return False
    try:
        lock.unlink()
        return True
    except OSError:
        return False  # someone else may have just removed it — fine.


def acquire_lock(
    path: Path,
    timeout: float = DEFAULT_TIMEOUT,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Path:
    """Acquire the advisory lock guarding ``path``; return the lock-file path.

    Tries to atomically create ``<path>.lock``. On contention it retries with
    exponential backoff until ``timeout`` seconds have elapsed, reclaiming a
    stale lock (older than :data:`STALE_AFTER_SECONDS`) if it finds one. Raises
    :class:`LockTimeout` if the lock cannot be taken in time. ``clock`` and
    ``sleep`` are injectable for deterministic tests.
    """
    lock = lock_path_for(path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = clock() + timeout
    backoff = _INITIAL_BACKOFF

    while True:
        _reclaim_if_stale(lock, time.time())
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            if clock() >= deadline:
                raise LockTimeout(
                    f"Could not acquire lock on {path} within {timeout:g}s "
                    f"({lock} is held)."
                ) from None
            sleep(min(backoff, _MAX_BACKOFF))
            backoff *= 2
            continue
        # Won the race — record owner metadata for diagnostics, then return.
        stamp = datetime.now(timezone.utc).isoformat()
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()}\nacquired={stamp}\n")
        return lock


def release_lock(path: Path) -> None:
    """Release the advisory lock guarding ``path`` (no error if already gone)."""
    lock_path_for(path).unlink(missing_ok=True)


@contextmanager
def vault_lock(
    path: Path,
    timeout: float = DEFAULT_TIMEOUT,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[Path]:
    """Context manager wrapping :func:`acquire_lock` / :func:`release_lock`.

    The lock is released even if the guarded block raises::

        with vault_lock(note_path):
            note_path.write_text(body)
    """
    acquire_lock(path, timeout, clock=clock, sleep=sleep)
    try:
        yield path
    finally:
        release_lock(path)
