"""Tests for atlas_os.filelock — advisory locking with stale-lock recovery."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from atlas_os import filelock


class TestAcquireRelease:
    def test_acquire_creates_lock_file(self, tmp_path: Path) -> None:
        target = tmp_path / "note.md"
        lock = filelock.acquire_lock(target)
        assert lock == filelock.lock_path_for(target)
        assert lock.exists()
        assert f"pid={os.getpid()}" in lock.read_text(encoding="utf-8")
        filelock.release_lock(target)
        assert not lock.exists()

    def test_release_is_idempotent(self, tmp_path: Path) -> None:
        target = tmp_path / "note.md"
        filelock.release_lock(target)  # never acquired — no error
        filelock.acquire_lock(target)
        filelock.release_lock(target)
        filelock.release_lock(target)  # double release — no error

    def test_contended_lock_times_out(self, tmp_path: Path) -> None:
        target = tmp_path / "note.md"
        filelock.acquire_lock(target)
        slept: list[float] = []
        with pytest.raises(filelock.LockTimeout):
            # Held lock + a clock that immediately exceeds the deadline.
            clock = iter([0.0, 0.0, 100.0, 200.0])
            filelock.acquire_lock(
                target, timeout=1,
                clock=lambda: next(clock), sleep=slept.append,
            )

    def test_acquire_after_release_succeeds(self, tmp_path: Path) -> None:
        target = tmp_path / "note.md"
        filelock.acquire_lock(target)
        filelock.release_lock(target)
        # Should win immediately the second time.
        lock = filelock.acquire_lock(target, timeout=1)
        assert lock.exists()


class TestStaleRecovery:
    def test_stale_lock_is_reclaimed(self, tmp_path: Path) -> None:
        target = tmp_path / "note.md"
        lock = filelock.lock_path_for(target)
        lock.write_text("pid=99999\n", encoding="utf-8")
        old = time.time() - (filelock.STALE_AFTER_SECONDS + 60)
        os.utime(lock, (old, old))

        # Even though a lock file exists, it is stale → acquisition succeeds.
        acquired = filelock.acquire_lock(target, timeout=1)
        assert acquired.exists()
        assert f"pid={os.getpid()}" in acquired.read_text(encoding="utf-8")

    def test_fresh_lock_is_not_reclaimed(self, tmp_path: Path) -> None:
        target = tmp_path / "note.md"
        lock = filelock.lock_path_for(target)
        lock.write_text("pid=99999\n", encoding="utf-8")  # fresh mtime (now)

        with pytest.raises(filelock.LockTimeout):
            clock = iter([0.0, 0.0, 100.0])
            filelock.acquire_lock(
                target, timeout=1, clock=lambda: next(clock), sleep=lambda _s: None
            )


class TestVaultLockContextManager:
    def test_releases_on_normal_exit(self, tmp_path: Path) -> None:
        target = tmp_path / "note.md"
        with filelock.vault_lock(target):
            assert filelock.lock_path_for(target).exists()
        assert not filelock.lock_path_for(target).exists()

    def test_releases_on_exception(self, tmp_path: Path) -> None:
        target = tmp_path / "note.md"
        with pytest.raises(ValueError):
            with filelock.vault_lock(target):
                assert filelock.lock_path_for(target).exists()
                raise ValueError("boom")
        assert not filelock.lock_path_for(target).exists()
