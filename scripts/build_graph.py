#!/usr/bin/env python3
"""
Build a knowledge graph from wikilinks (`[[note]]`) in a markdown vault.

Walks every .md file under VAULT_PATH, resolves wikilinks to files, and writes
a graph.json with nodes, edges, adjacency, and backlinks. Used by the dashboard
and by RAG tooling to surface related notes.

Configuration is read from environment variables — no hardcoded paths.

Environment variables:
    VAULT_PATH   Absolute path to the vault (required)
    RAG_DIR      Where to write graph.json (default: $VAULT_PATH/.rag)

Usage:
    python3 build_graph.py
"""

import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from _bootstrap import ensure_atlas_os

ensure_atlas_os()
from atlas_os import fileio, scriptkit  # noqa: E402

VAULT_DIR = Path(os.path.expanduser(os.environ.get("VAULT_PATH", "."))).resolve()
RAG_DIR = Path(os.path.expanduser(os.environ.get("RAG_DIR", str(VAULT_DIR / ".rag"))))
RAG_DIR.mkdir(parents=True, exist_ok=True)
GRAPH_FILE = RAG_DIR / "graph.json"

SKIP_DIRS = {".obsidian", ".git", ".rag", ".claude", "node_modules", ".schemas"}
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def extract_wikilinks(text: str) -> list[str]:
    links = []
    for match in WIKILINK_RE.finditer(text):
        target = match.group(1)
        target = target.split("|")[0].strip()   # [[note|display]] → note
        target = target.split("#")[0].strip()   # [[note#heading]] → note
        if target:
            links.append(target)
    return links


def iter_md_files() -> list[Path]:
    files = []
    for root, dirs, filenames in os.walk(VAULT_DIR):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".md"):
                files.append(Path(root) / fn)
    return sorted(files)


def build_file_index(md_files: list[Path]) -> dict[str, str]:
    """Map lowercase stem and relative-path-no-ext → relative path string."""
    index: dict[str, str] = {}
    for fp in md_files:
        rel = str(fp.relative_to(VAULT_DIR))
        index[fp.stem.lower()] = rel
        index[str(fp.relative_to(VAULT_DIR).with_suffix("")).lower()] = rel
    return index


def resolve_link(target: str, file_index: dict[str, str]) -> str | None:
    key = target.lower()
    if key in file_index:
        return file_index[key]
    stem = Path(target).stem.lower()
    if stem in file_index:
        return file_index[stem]
    return None


def build_graph() -> tuple[dict, dict]:
    md_files = iter_md_files()
    print(f"Found {len(md_files)} markdown files")

    file_index = build_file_index(md_files)
    nodes: list[str] = [str(fp.relative_to(VAULT_DIR)) for fp in md_files]
    edges: list[dict] = []
    adjacency: dict[str, list[str]] = defaultdict(list)

    for fp in md_files:
        source = str(fp.relative_to(VAULT_DIR))
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"  Skipping {fp.name}: {e}")
            continue

        seen_targets: set[str] = set()
        for link in extract_wikilinks(text):
            target = resolve_link(link, file_index)
            if target and target != source and target not in seen_targets:
                edges.append({"source": source, "target": target})
                adjacency[source].append(target)
                seen_targets.add(target)

    degree: Counter[str] = Counter()
    for edge in edges:
        degree[edge["source"]] += 1
        degree[edge["target"]] += 0
    for node in nodes:
        degree.setdefault(node, 0)

    backlinks: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        backlinks[edge["target"]].append(edge["source"])

    graph = {
        "nodes": nodes,
        "edges": edges,
        "adjacency": dict(adjacency),
        "backlinks": dict(backlinks),
    }
    stats = {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "avg_connections": len(edges) / len(nodes) if nodes else 0.0,
        "most_connected": degree.most_common(10),
    }
    return graph, stats


def save_graph(graph: dict) -> None:
    fileio.atomic_write_json(GRAPH_FILE, graph)
    print(f"Saved graph to {GRAPH_FILE}")


def main() -> None:
    print(f"Building knowledge graph from {VAULT_DIR}")
    graph, stats = build_graph()
    save_graph(graph)

    print(f"\n  Total nodes      : {stats['total_nodes']}")
    print(f"  Total edges      : {stats['total_edges']}")
    print(f"  Avg connections  : {stats['avg_connections']:.2f}")
    print("\n  Most connected notes:")
    for note, degree in stats["most_connected"]:
        print(f"    {degree:4d}  {note}")


if __name__ == "__main__":
    if not os.environ.get("VAULT_PATH"):
        scriptkit.fail(
            "VAULT_PATH environment variable is not set. See .env.example.",
            code=scriptkit.EXIT_CONFIG,
            json_mode=scriptkit.json_mode_requested(),
        )
    with scriptkit.error_boundary(json_mode=scriptkit.json_mode_requested()):
        main()
