"""Structured error output and exit codes for the standalone pipeline scripts.

Every script in ``scripts/`` should behave like a well-mannered CLI tool:

* return meaningful **exit codes** — ``0`` success, ``1`` runtime error,
  ``2`` configuration error (missing env var, bad arguments);
* emit machine-readable **JSON error info** when invoked with ``--json``;
* **never dump a raw Python traceback** at a user — turn it into a one-line
  message instead.

The :func:`error_boundary` context manager wraps a script's ``main()`` so that
any of the typed errors from :mod:`atlas_os.netio`, :mod:`atlas_os.fileio`, and
:mod:`atlas_os.gitutil` — or any unexpected exception — becomes a clean message
and the right exit code. :func:`emit_warning` is the graceful-degradation
counterpart: log that an optional step was skipped and carry on.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, NoReturn

from .fileio import FileIOError
from .gitutil import GitError
from .netio import NetworkError

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFIG = 2


def json_mode_requested(argv: list[str] | None = None) -> bool:
    """Return ``True`` if ``--json`` appears in the arguments."""
    args = sys.argv[1:] if argv is None else argv
    return "--json" in args


def emit_error(
    message: str,
    *,
    code: int = EXIT_ERROR,
    json_mode: bool = False,
    **extra: Any,
) -> int:
    """Print a structured error to stderr and return ``code``.

    With ``json_mode`` the output is ``{"status": "error", "error": ...}`` plus
    any ``extra`` fields; otherwise a plain ``ERROR: ...`` line. Returns the exit
    code so callers can ``sys.exit(emit_error(...))``.
    """
    if json_mode:
        payload: dict[str, Any] = {"status": "error", "error": message, **extra}
        print(json.dumps(payload), file=sys.stderr)
    else:
        print(f"ERROR: {message}", file=sys.stderr)
    return code


def fail(
    message: str,
    *,
    code: int = EXIT_ERROR,
    json_mode: bool = False,
    **extra: Any,
) -> NoReturn:
    """Emit a structured error and exit the process with ``code``."""
    raise SystemExit(emit_error(message, code=code, json_mode=json_mode, **extra))


def emit_warning(message: str, *, json_mode: bool = False) -> None:
    """Log a non-fatal warning to stderr (graceful degradation)."""
    if json_mode:
        print(json.dumps({"status": "warning", "warning": message}), file=sys.stderr)
    else:
        print(f"WARNING: {message}", file=sys.stderr)


@contextmanager
def error_boundary(*, json_mode: bool = False) -> Iterator[None]:
    """Convert exceptions raised inside the block into clean exits.

    Typed configuration/IO/network/git errors exit ``1`` with a tidy message;
    a ``KeyboardInterrupt`` exits ``130``; anything else becomes a one-line
    "Unexpected error" rather than a traceback. Used to wrap ``main()`` so a
    crashing pipeline never confronts the user with internals.
    """
    try:
        yield
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130) from None
    except (NetworkError, FileIOError, GitError) as exc:
        raise SystemExit(emit_error(str(exc), json_mode=json_mode)) from None
    except Exception as exc:  # noqa: BLE001 - last line of defence against tracebacks
        raise SystemExit(
            emit_error(f"Unexpected error: {exc}", json_mode=json_mode)
        ) from None
