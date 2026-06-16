from __future__ import annotations

from functools import wraps

from flask import flash, redirect, session, url_for


def inject_user():
    """Hace `user` disponible en templates (id, name, role)."""
    return dict(
        user={
            "id":   session.get("user_id")   or "",
            "name": session.get("user_name") or "Usuario",
            "role": session.get("user_role") or "",
        }
    )


def login_required(view_fn):
    """Decorator: requiere sesion valida."""

    @wraps(view_fn)
    def _wrapper(*args, **kwargs):
        if not session.get("access_token") or not session.get("user_id"):
            flash("Inicia sesión para continuar.", "error")
            return redirect(url_for("auth.login_get"))
        return view_fn(*args, **kwargs)

    return _wrapper


def role_required(*roles: str):
    """Decorator: requiere sesion valida Y que el rol del usuario esté en `roles`."""

    def decorator(view_fn):
        @wraps(view_fn)
        def _wrapper(*args, **kwargs):
            if not session.get("access_token") or not session.get("user_id"):
                flash("Inicia sesión para continuar.", "error")
                return redirect(url_for("auth.login_get"))

            user_role = session.get("user_role") or ""
            # Los desarrolladores del sistema tienen acceso total (superusuario).
            if user_role == "developer":
                return view_fn(*args, **kwargs)
            if user_role not in roles:
                flash("No tienes permiso para acceder a esta sección.", "warning")
                if user_role == "ops":
                    return redirect(url_for("events.events_list"))
                if user_role == "sales":
                    return redirect(url_for("quotations.quotations_list"))
                return redirect(url_for("dashboard.dashboard"))

            return view_fn(*args, **kwargs)

        return _wrapper

    return decorator
