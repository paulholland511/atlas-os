"""Tests for scripts/rag_search.py — the search-utility CLI argument handling."""

from __future__ import annotations

import argparse
import time

import pytest

import rag_search


class TestParseSince:
    def test_relative_hours(self) -> None:
        before = time.time() - 24 * 3600
        got = rag_search.parse_since("24h")
        assert abs(got - before) < 5  # within a few seconds of "24h ago"

    def test_relative_days_and_weeks(self) -> None:
        assert rag_search.parse_since("7d") < time.time()
        assert rag_search.parse_since("2w") < rag_search.parse_since("7d")

    def test_absolute_date(self) -> None:
        ts = rag_search.parse_since("2026-01-01")
        # Round-trips to the same calendar date (UTC).
        assert time.strftime("%Y-%m-%d", time.gmtime(ts)) == "2026-01-01"

    def test_invalid_raises(self) -> None:
        with pytest.raises(argparse.ArgumentTypeError):
            rag_search.parse_since("not-a-date")


class TestParser:
    def test_defaults(self) -> None:
        args = rag_search.build_parser().parse_args(["my query"])
        assert args.query == "my query"
        assert args.top_k == 5
        assert args.mode == "hybrid"
        assert not args.no_rerank

    def test_repeatable_filters(self) -> None:
        args = rag_search.build_parser().parse_args(
            ["q", "--folder", "research", "--folder", "wiki", "--tag", "ai"]
        )
        assert args.folder == ["research", "wiki"]
        assert args.tag == ["ai"]

    def test_mode_choices_enforced(self) -> None:
        with pytest.raises(SystemExit):
            rag_search.build_parser().parse_args(["q", "--mode", "bogus"])
