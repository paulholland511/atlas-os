"""Data-gathering for the dashboard — pure, Flask-free, individually testable.

Every function here reads live state from the existing Atlas OS modules and
returns plain dictionaries / lists of dictionaries ready to hand to a Jinja2
template. Nothing here imports Flask, touches ``request``/``session``, or renders
HTML, so each function can be unit-tested in isolation (see
``tests/test_dashboard.py``).

The functions deliberately *never raise* for the ordinary "not set up yet"
cases — a missing vault, an absent vector store, an empty audit log — because the
dashboard's job is to *show* those states (amber, "no index yet"), not to crash.
Genuinely unexpected errors are allowed to propagate.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas_os import audit
from atlas_os import _skills, packs
from atlas_os._paths import scripts_dir, skills_dir

# Map a doctor status to a CSS state class used by the templates / theme.
_STATUS_CLASS: dict[str, str] = {"OK": "ok", "WARN": "warn", "FAIL": "fail"}

# The audit-trail action keyword each schedulable skill corresponds to, used to
# surface a skill's most recent *scheduled* run on the Scheduled Tasks page. A
# skill with no natural audit action simply shows "no recorded run".
_SKILL_AUDIT_ACTIONS: dict[str, str] = {
    "nightly-obsidian-index": "embed",
    "nightly-rag-incremental": "embed",
    "weekly-rag-full-reembed": "embed",
    "morning-session-capture": "session",
    "afternoon-session-capture": "session",
    "daily-session-capture": "session",
    "atlas-daily-report-email": "email",
    "daily-trading-report": "trading",
    "friday-it-newsletter": "email",
    "weekly-system-health-check": "health",
}


# ── helpers ───────────────────────────────────────────────────────────────────
def _resolve_vault() -> Path | None:
    vault = os.environ.get("VAULT_PATH")
    if not vault:
        return None
    return Path(os.path.expanduser(vault))


def _resolve_rag_dir() -> Path | None:
    """The RAG directory: ``$RAG_DIR``, else ``$VAULT_PATH/.rag``, else None."""
    rag = os.environ.get("RAG_DIR")
    if rag:
        return Path(os.path.expanduser(rag))
    vault = _resolve_vault()
    return (vault / ".rag") if vault is not None else None


def _format_age(seconds: float) -> str:
    """Human-readable age, mirroring the doctor's ``_format_age``."""
    if seconds < 0:
        return "in the future"
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h ago"
    return f"{seconds / 86400:.1f}d ago"


def _format_bytes(size: int) -> str:
    """Human-readable file size (B / KB / MB / GB)."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


# ── 1. system health (atlas doctor) ────────────────────────────────────────────
def health_report() -> dict[str, Any]:
    """Run the doctor checks and group them for display.

    Reuses ``atlas doctor``'s own check logic (``cli._doctor_results``) so the
    dashboard and the CLI can never disagree. Returns the categories in display
    order, each row carrying a ``state`` class (``ok`` / ``warn`` / ``fail``) for
    the green/amber/red indicators, plus an overall summary.
    """
    # Imported here (not at module load) so importing this module stays cheap and
    # free of the CLI's import-time .env loading until health is actually asked for.
    from atlas_os import cli

    results = cli._doctor_results()
    categories: dict[str, list[dict[str, Any]]] = {}
    for check in results:
        categories.setdefault(check.category, []).append({
            "name": check.name,
            "status": check.status,
            "state": _STATUS_CLASS.get(check.status, "warn"),
            "detail": check.detail,
            "next_step": check.next_step,
        })

    order = list(cli._DOCTOR_CATEGORIES)
    ordered = [
        {"name": cat, "checks": categories[cat]}
        for cat in order
        if cat in categories
    ]
    # Append any category the doctor produced that isn't in the known order.
    for cat, checks in categories.items():
        if cat not in order:
            ordered.append({"name": cat, "checks": checks})

    summary = {
        "ok": sum(1 for c in results if c.status == "OK"),
        "warn": sum(1 for c in results if c.status == "WARN"),
        "fail": sum(1 for c in results if c.status == "FAIL"),
        "total": len(results),
    }
    overall = "ok" if summary["fail"] == 0 and summary["warn"] == 0 else (
        "fail" if summary["fail"] else "warn"
    )
    return {"categories": ordered, "summary": summary, "overall": overall}


# ── 2. audit trail browser ──────────────────────────────────────────────────────
@dataclass(frozen=True)
class AuditPage:
    """One page of audit entries, plus the data the template needs to paginate."""

    entries: list[dict[str, Any]]
    page: int
    pages: int
    total: int
    per_page: int
    actions: list[str]  # distinct action names, for the filter dropdown


def audit_page(
    action: str | None = None,
    since: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> AuditPage:
    """A filtered, paginated slice of the audit log, newest first.

    ``action`` filters to one action name; ``since`` accepts the same values as
    ``atlas audit show --since`` (``24h``, ``7d``, ``2026-06-01``). An invalid
    ``since`` is treated as "no time filter" rather than raising, so a stray query
    string never 500s the page.
    """
    action = action or None
    try:
        matched = audit.read_audit(since=since or None, action=action, limit=-1)
    except ValueError:
        matched = audit.read_audit(action=action, limit=-1)

    # The distinct action set is taken from the *unfiltered* log so the dropdown
    # always offers every action, not just the one currently selected.
    everything = audit.read_audit(limit=-1)
    actions = sorted({str(e.get("action", "")) for e in everything if e.get("action")})

    matched.reverse()  # newest first for display
    total = len(matched)
    per_page = max(1, per_page)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(1, page), pages)
    start = (page - 1) * per_page
    entries = matched[start : start + per_page]

    return AuditPage(
        entries=entries,
        page=page,
        pages=pages,
        total=total,
        per_page=per_page,
        actions=actions,
    )


# ── 3. scheduled tasks ──────────────────────────────────────────────────────────
def _latest_scheduled_run(action: str | None) -> dict[str, Any] | None:
    """The most recent scheduled-trigger audit entry for an action, if any."""
    if not action:
        return None
    entries = audit.read_audit(action=action, limit=-1)
    for entry in reversed(entries):
        if entry.get("trigger") == "scheduled":
            return entry
    # Fall back to the most recent run of any trigger, so a manually-run task
    # still shows when it last executed.
    return entries[-1] if entries else None


def scheduled_tasks() -> list[dict[str, Any]]:
    """Schedulable skills with their cadence, install state, and last run.

    A "scheduled task" is a skill that carries a suggested cadence (the ones in
    ``_skills._CADENCES``). For each we report whether it is installed into the
    scheduled-tasks directory and, where the audit trail records it, when it last
    ran and whether that run succeeded.
    """
    install_root = _skills.skills_install_root()
    rows: list[dict[str, Any]] = []
    for skill in _skills.load_skills():
        if skill.cadence == "—":
            continue  # not a scheduled automation
        installed = bool(
            install_root is not None
            and (install_root / skill.slug / "SKILL.md").is_file()
        )
        last = _latest_scheduled_run(_SKILL_AUDIT_ACTIONS.get(skill.slug))
        last_run: dict[str, Any] | None = None
        if last is not None:
            status = str(last.get("status", ""))
            last_run = {
                "timestamp": str(last.get("timestamp", ""))[:19].replace("T", " "),
                "status": status,
                "state": {"success": "ok", "error": "fail", "skipped": "warn"}.get(
                    status, "warn"
                ),
                "trigger": str(last.get("trigger", "")),
            }
        rows.append({
            "slug": skill.slug,
            "name": skill.name,
            "cadence": skill.cadence,
            "installed": installed,
            "last_run": last_run,
        })
    return rows


# ── 4. skills manager ────────────────────────────────────────────────────────────
def skills_overview() -> dict[str, Any]:
    """Every installable skill (with install state) and the curated packs."""
    install_root = _skills.skills_install_root()
    skill_rows = [
        {
            "slug": s.slug,
            "name": s.name,
            "description": s.description,
            "cadence": s.cadence,
            "installed": bool(
                install_root is not None
                and (install_root / s.slug / "SKILL.md").is_file()
            ),
        }
        for s in _skills.load_skills()
    ]
    pack_rows = [
        {"name": p.name, "description": p.description, "skills": list(p.skills)}
        for p in packs.load_packs()
    ]
    return {
        "skills": skill_rows,
        "packs": pack_rows,
        "install_root": str(install_root) if install_root else None,
    }


def skill_detail(slug: str) -> dict[str, Any] | None:
    """A single skill's metadata plus its raw SKILL.md, or None if unknown."""
    skill = _skills.find_skill(slug)
    if skill is None:
        return None
    source = skills_dir() / skill.slug / "SKILL.md"
    body = source.read_text(encoding="utf-8") if source.is_file() else ""
    install_root = _skills.skills_install_root()
    installed = bool(
        install_root is not None and (install_root / skill.slug / "SKILL.md").is_file()
    )
    return {
        "slug": skill.slug,
        "name": skill.name,
        "description": skill.description,
        "cadence": skill.cadence,
        "installed": installed,
        "body": body,
    }


def install_pack(name: str, *, force: bool = False) -> dict[str, Any]:
    """Install a skill pack and return a flat, display-ready summary.

    Wraps :func:`atlas_os.packs.install_pack`, turning its result (or the
    "no install target" / "unknown pack" errors) into a ``{ok, message}`` dict
    the route can flash without catching exceptions itself.
    """
    try:
        result = packs.install_pack(name, force=force)
    except packs.PackNotFoundError:
        return {"ok": False, "message": f"Unknown pack {name!r}."}
    except _skills.SkillInstallError as exc:
        return {"ok": False, "message": str(exc)}

    installed = len(result.installed)
    skipped = len(result.skipped)
    parts = [f"{installed} installed"]
    if skipped:
        parts.append(f"{skipped} skipped")
    return {
        "ok": installed > 0,
        "message": f"Pack {name!r}: {', '.join(parts)}.",
    }


# ── 5. vector store stats ─────────────────────────────────────────────────────────
def vector_stats() -> dict[str, Any]:
    """Chunk count, file count, cache size, DB size, and last-embed time.

    Returns ``available: False`` (rather than raising) when there is no vault, no
    RAG directory, or no ``vectors.db`` yet — the dashboard renders that as an
    amber "no index yet" panel with a hint to run ``atlas embed --full``.
    """
    from atlas_os import vectordb

    rag_dir = _resolve_rag_dir()
    if rag_dir is None:
        return {"available": False, "reason": "VAULT_PATH / RAG_DIR is not set."}

    db_path = vectordb.default_db_path(rag_dir)
    if not db_path.exists():
        return {
            "available": False,
            "reason": "no vectors yet — run `atlas embed --full` to build the index.",
            "rag_dir": str(rag_dir),
        }

    with vectordb.VectorStore(db_path) as store:
        chunk_count = store.count()
        counts = store.file_counts()
        file_count = len(counts)
        cache_size = store.cache_size()
        backend = "sqlite-vec (KNN)" if store.vec_enabled else "brute-force cosine"

    db_size = db_path.stat().st_size

    # Per-file chunk breakdown, biggest first, with each file's share of the
    # index as a percentage so the template can draw proportional bars. Capped at
    # the top 40 so a 1k-file vault doesn't render a 1k-row table.
    top_chunks = max(counts.values()) if counts else 0
    files = [
        {
            "file": path,
            "chunks": n,
            "share": (n / chunk_count * 100) if chunk_count else 0.0,
            "bar": (n / top_chunks * 100) if top_chunks else 0.0,
        }
        for path, n in list(counts.items())[:40]
    ]
    avg_chunks = (chunk_count / file_count) if file_count else 0.0

    # Last-embed timestamp (canonical file, then the iCloud-safe fallback).
    last_embed_ts = 0.0
    for name in ("last_embed.txt", "last_embed_fallback.txt"):
        candidate = rag_dir / name
        if candidate.exists():
            try:
                last_embed_ts = float(candidate.read_text().strip())
                break
            except (ValueError, OSError):
                continue

    last_embed: dict[str, Any] | None = None
    if last_embed_ts > 0:
        when = datetime.fromtimestamp(last_embed_ts, tz=timezone.utc)
        age = (datetime.now(timezone.utc) - when).total_seconds()
        last_embed = {
            "iso": when.strftime("%Y-%m-%d %H:%M UTC"),
            "age": _format_age(age),
            "stale": age > 24 * 3600,
        }

    return {
        "available": True,
        "chunk_count": chunk_count,
        "file_count": file_count,
        "cache_size": cache_size,
        "db_size": _format_bytes(db_size),
        "db_size_bytes": db_size,
        "backend": backend,
        "db_path": str(db_path),
        "last_embed": last_embed,
        "files": files,
        "files_truncated": max(0, file_count - len(files)),
        "avg_chunks": avg_chunks,
    }


# ── 6. RAG search ──────────────────────────────────────────────────────────────
def run_search(query: str, top_k: int = 5, mode: str = "hybrid") -> dict[str, Any]:
    """Run ``atlas search`` for ``query`` and return parsed results.

    Shells out to the same ``scripts/rag_search.py`` the ``atlas search`` command
    drives (with ``--json``), so the dashboard's results are identical to the
    CLI's. A failure — no embeddings endpoint, no vault — is returned as
    ``{ok: False, error: …}`` rather than raised, so the search box degrades
    gracefully instead of 500-ing.
    """
    query = query.strip()
    if not query:
        return {"ok": True, "query": "", "results": []}

    script = scripts_dir() / "rag_search.py"
    if not script.is_file():
        return {"ok": False, "query": query, "error": "rag_search.py not found."}

    mode = mode if mode in ("hybrid", "vector", "keyword") else "hybrid"
    cmd = [
        sys.executable, str(script), query,
        "--top-k", str(max(1, top_k)), "--mode", mode, "--json",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, check=False
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"ok": False, "query": query, "error": f"search failed: {exc}"}

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        message = detail[-1] if detail else f"exit code {proc.returncode}"
        return {"ok": False, "query": query, "error": message}

    import json

    try:
        results = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return {"ok": False, "query": query, "error": "could not parse search output."}

    return {"ok": True, "query": query, "mode": mode, "results": _clean_results(results)}


def _clean_results(results: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalise raw search hits into the fields the template renders."""
    cleaned: list[dict[str, Any]] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        score = r.get("rerank_score", r.get("score", 0.0))
        snippet = " ".join(str(r.get("text", "")).split())[:300]
        cleaned.append({
            "file": str(r.get("file", "")),
            "heading": str(r.get("heading", "")),
            "score": float(score) if isinstance(score, (int, float)) else 0.0,
            "snippet": snippet,
        })
    return cleaned


# ── 7. knowledge graph ─────────────────────────────────────────────────────────
# The viewer scans the vault live for ``[[wikilinks]]`` — the same idea as
# ``scripts/build_graph.py`` (which writes ``graph.json`` for CLI/RAG tooling) —
# but reimplemented here, compact and Flask-free, so the API is always current
# without a prior ``atlas graph`` run and the function stays unit-testable.
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_GRAPH_SKIP_DIRS = frozenset({
    ".obsidian", ".git", ".rag", ".claude", ".atlas", "node_modules", ".schemas",
})

# Each note is classified into one of these types by its path; the viewer colours
# nodes and builds its legend from this single source of truth. Order matters —
# ``_classify_node`` returns the first matching type, "note" is the catch-all.
_NODE_TYPES: tuple[tuple[str, str, str], ...] = (
    ("session", "Session log", "#60a5fa"),
    ("source", "Source", "#fbbf24"),
    ("skill", "Skill", "#a78bfa"),
    ("research", "Research", "#34d399"),
    ("wiki", "Wiki", "#22c55e"),
    ("memory", "Memory", "#f472b6"),
    ("note", "Note", "#94a3b8"),
)


def _classify_node(rel_path: str) -> str:
    """Map a vault-relative note path to a node type (see :data:`_NODE_TYPES`)."""
    lower = rel_path.lower()
    parts = lower.split("/")
    name = parts[-1]
    if name == "skill.md" or "skills" in parts:
        return "skill"
    if "sessions" in parts or "session" in name or name.startswith("log"):
        return "session"
    if "sources" in parts or name.startswith("source"):
        return "source"
    if "research" in parts:
        return "research"
    if "wiki" in parts:
        return "wiki"
    if "memory" in parts:
        return "memory"
    return "note"


def _iter_vault_md(vault: Path) -> list[Path]:
    """Every ``.md`` file under the vault, skipping dot/infra directories."""
    files: list[Path] = []
    for root, dirs, names in os.walk(vault):
        dirs[:] = [d for d in dirs if d not in _GRAPH_SKIP_DIRS]
        for name in names:
            if name.endswith(".md"):
                files.append(Path(root) / name)
    return sorted(files)


def _resolve_link(target: str, file_index: dict[str, str]) -> str | None:
    """Resolve a raw ``[[wikilink]]`` target to a vault-relative path, or None."""
    cleaned = target.split("|", 1)[0].split("#", 1)[0].strip()
    if not cleaned:
        return None
    key = cleaned.lower()
    if key in file_index:
        return file_index[key]
    stem = Path(cleaned).stem.lower()
    return file_index.get(stem)


def graph_data(max_nodes: int = 2000) -> dict[str, Any]:
    """Nodes (vault notes) and edges (wikilinks) for the graph viewer / ``/api/graph``.

    Walks the vault, extracts ``[[wikilinks]]``, resolves them to files, and
    returns a graph the D3 viewer can render directly: each node carries a
    ``type`` (for colour), its link ``degree``, and in/out counts; each edge is a
    ``{source, target}`` pair of node ids (vault-relative paths). A ``types``
    legend and summary ``stats`` ride along.

    Never raises for the ordinary "nothing to show" cases — an unset vault, a
    vault with no notes — returning ``available: False`` (with a ``reason``) so
    the page renders an empty state instead of 500-ing. ``max_nodes`` caps the
    payload to the most-connected notes so a huge vault can't hang the layout.
    """
    legend = [
        {"type": t, "label": label, "color": color}
        for t, label, color in _NODE_TYPES
    ]
    result: dict[str, Any] = {
        "available": False,
        "nodes": [],
        "edges": [],
        "types": legend,
        "stats": {
            "nodes": 0, "edges": 0, "orphans": 0, "avg_degree": 0.0, "truncated": 0,
        },
    }

    vault = _resolve_vault()
    if vault is None or not vault.is_dir():
        result["reason"] = "VAULT_PATH is not set, or its folder does not exist."
        return result

    md_files = _iter_vault_md(vault)
    if not md_files:
        result["available"] = True
        result["reason"] = "no markdown notes found in the vault yet."
        return result

    rels = [str(p.relative_to(vault)) for p in md_files]

    # Index both the bare stem and the extension-less relative path, so links can
    # be written either way ([[note]] or [[folder/note]]). First file wins on a
    # stem collision; the (unique) path form is always exact.
    file_index: dict[str, str] = {}
    for rel in rels:
        file_index.setdefault(Path(rel).stem.lower(), rel)
        file_index[rel[:-3].lower()] = rel  # strip ".md"

    out_deg = dict.fromkeys(rels, 0)
    in_deg = dict.fromkeys(rels, 0)
    edges: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for path, source in zip(md_files, rels):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        targets: set[str] = set()
        for raw in _WIKILINK_RE.findall(text):
            target = _resolve_link(raw, file_index)
            if target and target != source:
                targets.add(target)
        for target in targets:
            pair = (source, target)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            edges.append({"source": source, "target": target})
            out_deg[source] += 1
            in_deg[target] += 1

    degree = {rel: out_deg[rel] + in_deg[rel] for rel in rels}

    # Cap to the most-connected notes; drop any edge whose endpoints fell away.
    truncated = 0
    kept = rels
    if len(rels) > max_nodes:
        kept = sorted(rels, key=lambda r: degree[r], reverse=True)[:max_nodes]
        kept_set = set(kept)
        edges = [
            e for e in edges if e["source"] in kept_set and e["target"] in kept_set
        ]
        truncated = len(rels) - len(kept)

    nodes = [
        {
            "id": rel,
            "label": Path(rel).stem,
            "path": rel,
            "type": _classify_node(rel),
            "degree": degree[rel],
            "in": in_deg[rel],
            "out": out_deg[rel],
        }
        for rel in kept
    ]
    orphans = sum(1 for rel in kept if degree[rel] == 0)
    total_degree = sum(degree[rel] for rel in kept)

    result.update({
        "available": True,
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "orphans": orphans,
            "avg_degree": (total_degree / len(kept)) if kept else 0.0,
            "truncated": truncated,
        },
    })
    return result
