"""Resilient file handling for Atlas OS.

The vault lives in iCloud Drive, which makes ordinary file I/O surprisingly
hazardous:

* files may be **cloud-offloaded** ("dataless") — present in a directory listing
  but with no local content, so reading them blocks or fails;
* reading an offloaded file can raise ``OSError(EDEADLK)`` ("Resource deadlock
  avoided") while macOS tries to fault the data back in;
* a half-written ``vectors.json`` / ``audit.jsonl`` left behind by a crash
  corrupts the next run.

This module provides:

* :func:`atomic_write_text` / :func:`atomic_write_bytes` / :func:`atomic_write_json`
  — write to a sibling ``.tmp`` file, ``fsync``, then ``os.replace`` so readers
  never observe a partial file;
* :func:`read_text` / :func:`read_json` — turn "missing", "permission denied",
  "dataless / EDEADLK", and "corrupt JSON" into typed, message-bearing errors (or
  a caller-supplied default) instead of a raw traceback;
* :func:`is_dataless` — detect an iCloud-offloaded stub before touching it.
"""

from __future__ import annotations

import errno
import json
import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

# macOS marks cloud-offloaded files with the SF_DATALESS flag in st_flags.
# Python's stat module doesn't expose the constant, so we hard-code its value.
_SF_DATALESS = 0x40000000

# How long :func:`ensure_materialized` waits, by default, for an iCloud-offloaded
# file to fault back in before giving up.
DEFAULT_MATERIALIZE_TIMEOUT = 30.0


class FileIOError(OSError):
    """Base class for file errors raised with an actionable message."""


class MissingFileError(FileIOError):
    """A required file does not exist."""


class FileAccessError(FileIOError):
    """A file exists but could not be read (permissions, or iCloud offloading)."""


class CorruptFileError(FileIOError):
    """A file exists but its contents could not be parsed (e.g. invalid JSON)."""


def is_dataless(path: Path) -> bool:
    """Return ``True`` if ``path`` is a macOS iCloud-offloaded ("dataless") stub.

    On platforms without ``st_flags`` (e.g. Linux) this always returns ``False``.
    """
    try:
        flags = getattr(path.stat(), "st_flags", 0)
    except OSError:
        return False
    return bool(flags & _SF_DATALESS)


def _trigger_fault_in(path: Path) -> None:
    """Ask macOS to download an iCloud-offloaded file (best effort, non-blocking).

    ``brctl download`` nudges the iCloud daemon to start materialising the file
    without us having to ``read()`` it (which would block). If ``brctl`` is
    absent (non-macOS, or a stripped environment) we silently rely on the
    subsequent access to trigger the fault-in instead.
    """
    try:
        subprocess.run(
            ["brctl", "download", str(path)],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass  # best-effort — the poll below still governs success/failure.


def ensure_materialized(
    path: Path,
    timeout: float = DEFAULT_MATERIALIZE_TIMEOUT,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    trigger: Callable[[Path], None] = _trigger_fault_in,
    poll: float = 0.5,
) -> bool:
    """Block until ``path`` is locally present (faulted in), up to ``timeout``.

    The vault lives in iCloud Drive, so a file may be **dataless** — listed in
    the directory but with no local content. Reading it naively can stall or
    return partial data. This triggers the download and polls
    :func:`is_dataless` until the file materialises or the timeout elapses.

    Returns ``True`` once the file is materialised (the common case on Linux/CI,
    where nothing is ever dataless, is an immediate ``True``); returns ``False``
    if it is still dataless after ``timeout`` so the caller can **skip and log**
    rather than read garbage. Raises :class:`MissingFileError` if ``path`` does
    not exist at all. ``clock``/``sleep``/``trigger`` are injectable for tests.
    """
    if not path.exists():
        raise MissingFileError(f"File not found: {path}")
    if not is_dataless(path):
        return True

    trigger(path)
    deadline = clock() + timeout
    while clock() < deadline:
        if not is_dataless(path):
            return True
        sleep(poll)
    return not is_dataless(path)


def _describe_read_failure(path: Path, exc: OSError) -> FileIOError:
    """Map a low-level read OSError to a typed, message-bearing FileIOError."""
    if exc.errno == errno.EDEADLK or is_dataless(path):
        return FileAccessError(
            f"{path} is offloaded to iCloud (dataless) and could not be read. "
            "Open it in Finder to download it, or disable 'Optimize Mac Storage'."
        )
    if exc.errno == errno.EACCES:
        return FileAccessError(f"Permission denied reading {path}.")
    return FileAccessError(f"Could not read {path}: {exc}")


def read_text(
    path: Path,
    *,
    default: str | None = None,
    encoding: str = "utf-8",
) -> str:
    """Read ``path`` as text, with graceful handling of common failures.

    If the file is missing, returns ``default`` when one is given, else raises
    :class:`MissingFileError`. Permission and iCloud-offload failures raise
    :class:`FileAccessError`. Decoding errors are replaced rather than raised.
    """
    if not path.exists():
        if default is not None:
            return default
        raise MissingFileError(f"File not found: {path}")
    try:
        return path.read_text(encoding=encoding, errors="replace")
    except OSError as exc:
        raise _describe_read_failure(path, exc) from exc


def read_json(
    path: Path,
    *,
    default: Any = None,
) -> Any:
    """Read and parse a JSON file, with graceful handling of common failures.

    Missing file → ``default`` if given (else :class:`MissingFileError`).
    Unreadable file → :class:`FileAccessError`. Invalid JSON → ``default`` if
    given (else :class:`CorruptFileError`), so a crash-truncated store degrades
    to "empty" rather than exploding.
    """
    if not path.exists():
        if default is not None:
            return default
        raise MissingFileError(f"File not found: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _describe_read_failure(path, exc) from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        if default is not None:
            return default
        raise CorruptFileError(f"{path} is not valid JSON: {exc}") from exc


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Atomically write ``data`` to ``path`` (write-temp-then-rename + fsync).

    The temp file is created in the same directory so ``os.replace`` is a true
    atomic rename (same filesystem). Parent directories are created as needed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise FileAccessError(f"Could not write {path}: {exc}") from exc


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Atomically write ``text`` to ``path``."""
    atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path: Path, obj: Any, *, indent: int | None = None) -> None:
    """Atomically serialise ``obj`` to ``path`` as JSON."""
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=indent))
