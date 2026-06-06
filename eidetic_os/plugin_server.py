"""The Eidetic OS plugin API server — a thin REST layer for the Obsidian plugin.

The companion Obsidian plugin (``obsidian-plugin/``) talks to this server to search
the RAG index, browse the fact store, read vault stats, and extract facts from a
note — all without leaving Obsidian. Like the dashboard, it is a *view* over the
modules ``eidetic`` already drives (:mod:`eidetic_os.rag` via the RAG search
script, :mod:`eidetic_os.facts`, :mod:`eidetic_os.vectordb`), never a second
source of truth, and it is meant to be bound to localhost only.

It deliberately reuses the dashboard's data-gathering layer
(:mod:`eidetic_os.dashboard.data`) for search and vector stats, so the plugin's
results are identical to the dashboard's and the CLI's. Facts are read straight
from :mod:`eidetic_os.facts`.

Endpoints (all JSON, all CORS-enabled for ``localhost``):

* ``GET  /api/health`` — liveness + version.
* ``GET  /api/search?q=<query>&limit=10&mode=hybrid`` — RAG search.
* ``GET  /api/facts?category=<cat>&limit=50`` — list stored facts.
* ``GET  /api/facts/search?q=<query>&limit=10`` — semantic fact search.
* ``GET  /api/stats`` — vault / vector / fact counts and last-embed time.
* ``POST /api/facts/extract`` — extract (and optionally store) facts from text.

Flask is an optional dependency (the ``dashboard`` extra); :func:`create_plugin_app`
raises a clear :class:`ModuleNotFoundError` with an install hint if it is absent,
so ``eidetic serve`` can turn that into a friendly message rather than a traceback.
The data helpers it leans on (``dashboard.data``, ``facts``) have no Flask
dependency, so everything below the routing layer stays importable and testable
without the extra.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from eidetic_os import __version__

if TYPE_CHECKING:
    from flask import Flask, Response

# The plugin runs in Obsidian's Electron renderer; requests originate from the
# bundled Chromium, so we allow cross-origin reads from any localhost origin (and
# the ``app://obsidian.md`` origin Obsidian itself uses). This is a localhost-only
# developer tool — the permissive policy is scoped to loopback, never the network.
_ALLOWED_ORIGIN = "*"


def _fact_payload(fact: Any, score: float | None = None) -> dict[str, Any]:
    """Shape a :class:`eidetic_os.facts.StoredFact` into a JSON-friendly dict.

    ``asdict`` gives every stored column; ``score`` (a search relevance, 0–1) is
    folded in only when the fact came from a ranked query.
    """
    payload = asdict(fact)
    if score is not None:
        payload["score"] = round(float(score), 4)
    return payload


def create_plugin_app() -> Flask:
    """Build the plugin API Flask app.

    Raises :class:`ModuleNotFoundError` (with an install hint) if Flask is not
    installed, mirroring :func:`eidetic_os.dashboard.app.create_app`, so the CLI
    can surface a friendly message.
    """
    try:
        from flask import Flask, jsonify, request
    except ImportError as exc:  # pragma: no cover - exercised via the CLI path
        raise ModuleNotFoundError(
            "The plugin server needs Flask. Install it with:\n"
            "    pip install 'eidetic-os[dashboard]'"
        ) from exc

    from eidetic_os import facts
    from eidetic_os.dashboard import data

    app = Flask(__name__)

    @app.after_request
    def _cors(response: Response) -> Response:
        """Attach permissive CORS headers so the Obsidian renderer can call us."""
        response.headers["Access-Control-Allow-Origin"] = _ALLOWED_ORIGIN
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    @app.route("/api/health", methods=["GET", "OPTIONS"])
    def health():  # noqa: ANN202 - Flask view
        """Liveness probe — the plugin polls this to drive its status bar."""
        return jsonify({
            "ok": True,
            "service": "eidetic-os-plugin",
            "version": __version__,
        })

    @app.route("/api/search", methods=["GET", "OPTIONS"])
    def search():  # noqa: ANN202
        """RAG search. ``q`` is the query; ``limit`` caps results; ``mode`` is
        ``hybrid`` (default), ``vector``, or ``keyword`` (offline BM25)."""
        query = request.args.get("q", default="", type=str).strip()
        limit = max(1, request.args.get("limit", default=10, type=int) or 10)
        mode = request.args.get("mode", default="hybrid", type=str)
        if not query:
            return jsonify({"ok": True, "query": "", "results": []})
        result = data.run_search(query, top_k=limit, mode=mode)
        return jsonify(result)

    @app.route("/api/facts", methods=["GET", "OPTIONS"])
    def list_facts():  # noqa: ANN202
        """List stored facts, newest first, optionally filtered by ``category``.

        No embedder is needed to list, so the store opens in offline mode (fast,
        no backend probe).
        """
        category = request.args.get("category", default="", type=str).strip() or None
        limit = max(1, request.args.get("limit", default=50, type=int) or 50)
        with facts.open_store(with_embedder=False) as store:
            rows = store.list_facts(category=category, limit=limit)
        return jsonify({
            "ok": True,
            "category": category,
            "count": len(rows),
            "facts": [_fact_payload(f) for f in rows],
        })

    @app.route("/api/facts/search", methods=["GET", "OPTIONS"])
    def search_facts():  # noqa: ANN202
        """Semantic search over active facts (cosine when an embedder is
        reachable, token overlap offline)."""
        query = request.args.get("q", default="", type=str).strip()
        limit = max(1, request.args.get("limit", default=10, type=int) or 10)
        if not query:
            return jsonify({"ok": True, "query": "", "results": []})
        with facts.open_store(with_embedder=True) as store:
            hits = store.query_facts(query, limit=limit)
        return jsonify({
            "ok": True,
            "query": query,
            "count": len(hits),
            "results": [_fact_payload(fact, score) for fact, score in hits],
        })

    @app.route("/api/stats", methods=["GET", "OPTIONS"])
    def stats():  # noqa: ANN202
        """Vault / vector / fact counts and the last-embed time for the plugin's
        stats view. Each block degrades independently if its source is missing."""
        vectors = data.vector_stats()
        try:
            with facts.open_store(with_embedder=False) as store:
                fact_stats = store.stats()
        except Exception as exc:  # noqa: BLE001 - never 500 the stats panel
            fact_stats = {"available": False, "error": str(exc)}
        return jsonify({
            "ok": True,
            "version": __version__,
            "vectors": vectors,
            "facts": fact_stats,
        })

    @app.route("/api/facts/extract", methods=["POST", "OPTIONS"])
    def extract():  # noqa: ANN202
        """Extract facts from posted text.

        Body (JSON): ``{"text": "...", "source": "note.md", "store": false}``.
        With ``store: true`` the facts are deduplicated and ingested into the
        store (returning the ingest tally); otherwise they are only previewed.
        """
        from flask import request as _req

        body = _req.get_json(silent=True) or {}
        text = str(body.get("text", "")).strip()
        source = str(body.get("source", "")).strip()
        should_store = bool(body.get("store", False))
        if not text:
            return jsonify({"ok": False, "error": "no text provided"}), 400

        if should_store:
            with facts.open_store(with_embedder=True) as store:
                tally = store.extract_and_ingest(text, source)
                preview = store.list_facts(limit=tally.get("inserted", 0) or 0)
            return jsonify({
                "ok": True,
                "stored": True,
                "source": source,
                "tally": tally,
                "facts": [_fact_payload(f) for f in preview],
            })

        extracted = facts.extract_facts(text, source)
        return jsonify({
            "ok": True,
            "stored": False,
            "source": source,
            "count": len(extracted),
            "facts": [asdict(f) for f in extracted],
        })

    return app
