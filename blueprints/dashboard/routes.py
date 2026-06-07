from __future__ import annotations

from flask import render_template, session

from blueprints.dashboard import bp
from services.session_user import role_required

from .service import build_dashboard_payload


@bp.get("/dashboard")
@role_required("admin")
def dashboard():
    p = build_dashboard_payload(session.get("user_id") or "")
    # El context_processor inject_user() queda sobreescrito al hacer **p,
    # así que reinyectamos el role desde la sesión.
    p["user"]["role"] = session.get("user_role") or ""
    return render_template("dashboard/dashboard.html", **p)
