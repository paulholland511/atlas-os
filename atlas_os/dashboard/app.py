"""The dashboard Flask application.

A thin routing layer over :mod:`atlas_os.dashboard.data`: every view function
gathers its data with one of the pure ``data.*`` helpers and renders a Jinja2
template. There is no database, no auth, and no client-side framework — the app
is meant to be run locally (``atlas dashboard``) and bound to localhost.

Build one with :func:`create_app`. Flask is imported at module load, so this
module (unlike :mod:`atlas_os.dashboard.data`) requires the optional
``atlas-os[dashboard]`` extra.
"""

from __future__ import annotations

import os
import platform
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from atlas_os import __version__
from atlas_os.dashboard import data

if TYPE_CHECKING:
    from flask import Flask


# The sidebar navigation, grouped into labelled sections. Each item is
# (endpoint, label, one-line description); the description shows as a tooltip and
# under the label on wide screens. ``icon(endpoint)`` resolves the glyph.
_NAV_GROUPS: tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...] = (
    (
        "Monitor",
        (
            ("health", "System health", "Live atlas doctor checks"),
            ("audit", "Audit trail", "Every autonomous action"),
            ("scheduled", "Scheduled tasks", "Automations & last runs"),
        ),
    ),
    (
        "Knowledge",
        (
            ("graph", "Knowledge graph", "How your notes connect"),
            ("vectors", "Vector store", "The RAG index"),
            ("search", "RAG search", "Search your vault"),
        ),
    ),
    (
        "Library",
        (("skills", "Skills", "Installable agent skills"),),
    ),
)

# Flat (endpoint, label) view of the nav — kept for any caller that wants the
# old shape, and used to know whether an endpoint is a top-level nav target.
_NAV: tuple[tuple[str, str], ...] = tuple(
    (endpoint, label)
    for _group, items in _NAV_GROUPS
    for endpoint, label, _desc in items
)


def create_app() -> Flask:
    """Build and configure the dashboard Flask app.

    Raises a clear :class:`ModuleNotFoundError` (with an install hint) if Flask
    is not installed, so ``atlas dashboard`` can turn that into a friendly
    message rather than a bare traceback.
    """
    try:
        from flask import (
            Flask,
            abort,
            flash,
            jsonify,
            redirect,
            render_template,
            request,
            url_for,
        )
    except ImportError as exc:  # pragma: no cover - exercised via the CLI path
        raise ModuleNotFoundError(
            "The dashboard needs Flask. Install it with:\n"
            "    pip install 'atlas-os[dashboard]'"
        ) from exc

    app = Flask(__name__)
    # Only used to sign the flash-message cookie for a localhost-only tool; not a
    # security boundary. A fixed dev key keeps flashes working across reloads.
    app.config["SECRET_KEY"] = "atlas-os-dashboard-local"

    @app.context_processor
    def _inject_globals() -> dict[str, object]:
        """Make the nav, active page, version, and footer facts available everywhere."""
        vault = os.environ.get("VAULT_PATH") or ""
        return {
            "nav": _NAV,
            "nav_groups": _NAV_GROUPS,
            "active": request.endpoint,
            "version": __version__,
            "now": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "py_version": platform.python_version(),
            "vault_path": os.path.expanduser(vault) if vault else None,
        }

    # ── routes ─────────────────────────────────────────────────────────────────
    @app.route("/")
    def index():  # noqa: ANN202 - Flask view
        return redirect(url_for("health"))

    @app.route("/health")
    def health():  # noqa: ANN202
        return render_template("health.html", report=data.health_report())

    @app.route("/audit")
    def audit():  # noqa: ANN202
        page = request.args.get("page", default=1, type=int) or 1
        action = request.args.get("action", default="", type=str)
        since = request.args.get("since", default="", type=str)
        result = data.audit_page(action=action, since=since, page=page)
        return render_template(
            "audit.html", page=result, action=action, since=since
        )

    @app.route("/scheduled")
    def scheduled():  # noqa: ANN202
        return render_template("scheduled.html", tasks=data.scheduled_tasks())

    @app.route("/skills")
    def skills():  # noqa: ANN202
        return render_template("skills.html", overview=data.skills_overview())

    @app.route("/skills/<slug>")
    def skill_detail(slug: str):  # noqa: ANN202
        detail = data.skill_detail(slug)
        if detail is None:
            abort(404)
        return render_template("skill_detail.html", skill=detail)

    @app.route("/skills/install-pack/<name>", methods=["POST"])
    def install_pack(name: str):  # noqa: ANN202
        force = request.form.get("force") == "1"
        result = data.install_pack(name, force=force)
        flash(result["message"], "ok" if result["ok"] else "error")
        return redirect(url_for("skills"))

    @app.route("/graph")
    def graph():  # noqa: ANN202
        return render_template("graph.html")

    @app.route("/api/graph")
    def api_graph():  # noqa: ANN202
        return jsonify(data.graph_data())

    @app.route("/vectors")
    def vectors():  # noqa: ANN202
        return render_template("vectors.html", stats=data.vector_stats())

    @app.route("/search")
    def search():  # noqa: ANN202
        query = request.args.get("q", default="", type=str)
        mode = request.args.get("mode", default="hybrid", type=str)
        top_k = request.args.get("top_k", default=5, type=int) or 5
        result = (
            data.run_search(query, top_k=top_k, mode=mode) if query.strip() else None
        )
        return render_template(
            "search.html", result=result, query=query, mode=mode, top_k=top_k
        )

    @app.errorhandler(404)
    def not_found(_err: object):  # noqa: ANN202
        return render_template("404.html"), 404

    return app
