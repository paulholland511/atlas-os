#!/usr/bin/env python3
"""Query the RAG store from the command line — hybrid search with reranking.

A thin CLI over the advanced retrieval pipeline in ``embed_vault.advanced_search``
(itself built on :mod:`atlas_os.rag`): semantic-chunked content, BM25 + vector
hybrid fusion, TF-IDF reranking, and metadata pre-filtering by folder, doc_type,
tag, file type, and modified-time window.

Backs the ``atlas search`` command. Reads the same configuration as
``embed_vault.py`` (``VAULT_PATH``, ``RAG_DIR``, ``EMBED_*``); a query embedding
needs the embeddings endpoint up (except in ``--mode keyword``, which is purely
lexical and offline).

Usage:
    rag_search.py "your query"                      # hybrid + rerank, top 5
    rag_search.py "query" --top-k 10 --mode vector  # semantic only
    rag_search.py "query" --mode keyword            # BM25 only (no endpoint)
    rag_search.py "query" --folder research --tag trading
    rag_search.py "query" --file-type md --since 30d
    rag_search.py "query" --no-rerank --json
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone

from _bootstrap import ensure_atlas_os

ensure_atlas_os()
import embed_vault  # noqa: E402  (sibling script, on sys.path via conftest/_bootstrap)
from atlas_os import scriptkit  # noqa: E402

_DURATION_UNITS = {"h": 3600, "d": 86400, "w": 604800}


def parse_since(value: str) -> float:
    """Parse a ``--since`` / ``--until`` value into a unix timestamp.

    Accepts a relative window (``24h``, ``7d``, ``2w``) interpreted as "ago", or
    an absolute ``YYYY-MM-DD`` date.
    """
    value = value.strip()
    if value and value[-1] in _DURATION_UNITS and value[:-1].isdigit():
        return time.time() - int(value[:-1]) * _DURATION_UNITS[value[-1]]
    try:
        dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"expected a window like 24h/7d/2w or a date YYYY-MM-DD, got {value!r}"
        ) from exc
    return dt.timestamp()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rag_search.py",
        description="Hybrid RAG search over the Atlas OS vault (BM25 + vector + rerank).",
    )
    p.add_argument("query", help="The search query.")
    p.add_argument("--top-k", "-k", type=int, default=5, help="Results to return (default 5).")
    p.add_argument(
        "--mode", choices=("hybrid", "vector", "keyword"), default="hybrid",
        help="Retrieval mode (default hybrid).",
    )
    p.add_argument("--folder", action="append", help="Restrict to a folder (repeatable).")
    p.add_argument("--doc-type", action="append", help="Restrict to a doc_type (repeatable).")
    p.add_argument("--tag", action="append", help="Restrict to a tag (repeatable).")
    p.add_argument(
        "--file-type", action="append",
        help="Restrict to a file extension, e.g. md or pdf (repeatable).",
    )
    p.add_argument("--since", type=parse_since, help="Only chunks modified since (24h/7d/2w/date).")
    p.add_argument("--until", type=parse_since, help="Only chunks modified before (24h/7d/2w/date).")
    p.add_argument("--no-rerank", action="store_true", help="Skip the TF-IDF rerank pass.")
    p.add_argument("--json", action="store_true", help="Emit results as JSON.")
    return p


def render_human(query: str, results: list[dict]) -> None:
    if not results:
        print(f"No results for {query!r}.")
        return
    print(f"\nTop {len(results)} result(s) for {query!r}:\n")
    for rank, r in enumerate(results, 1):
        score = r.get("rerank_score", r.get("score", 0.0))
        heading = f" › {r['heading']}" if r.get("heading") else ""
        snippet = " ".join(r.get("text", "").split())[:200]
        print(f"{rank}. [{score:.3f}] {r['file']}{heading}")
        print(f"     {snippet}\n")


def main() -> None:
    args = build_parser().parse_args()
    results = embed_vault.advanced_search(
        args.query,
        top_k=args.top_k,
        mode=args.mode,
        folders=args.folder,
        doc_types=args.doc_type,
        tags=args.tag,
        file_types=args.file_type,
        since=args.since,
        until=args.until,
        rerank=not args.no_rerank,
    )
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        render_human(args.query, results)


if __name__ == "__main__":
    if not os.environ.get("VAULT_PATH"):
        scriptkit.fail(
            "VAULT_PATH environment variable is not set. See .env.example.",
            code=scriptkit.EXIT_CONFIG,
        )
    with scriptkit.error_boundary():
        main()
