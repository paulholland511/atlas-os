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

from typing import TYPE_CHECKING

from atlas_os import __version__
from atlas_os.dashboard import data

if TYPE_CHECKING:
    from flask import Flask


# The navigation shown in the sidebar of every page: (endpoint, label).
_NAV: tuple[tuple[str, str], ...] = (
    ("health", "System health"),
    ("audit", "Audit trail"),
    ("scheduled", "Scheduled tasks"),
    ("skills", "Skills"),
    ("vectors", "Vector store"),
    ("search", "RAG search"),
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
        """Make the nav, active page, and version available to every template."""
        return {
            "nav": _NAV,
            "active": request.endpoint,
            "version": __version__,
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
