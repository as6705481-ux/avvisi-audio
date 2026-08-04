from __future__ import annotations

import os

from flask import flash, redirect, render_template, request, session, url_for

from blueprints.auth import bp
from extensions.supabase import get_public_client, get_service_client


@bp.get("/login")
def login_get():
    return render_template("auth/auth_login.html")


@bp.post("/login")
def login_post():
    email    = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    print("Login attempt for:", email, password)

    if not email or not password:
        flash("Correo y contraseña son requeridos", "error")
        return redirect(url_for("auth.login_get"))

    sb_pub = get_public_client()

    try:
        auth_res = sb_pub.auth.sign_in_with_password({"email": email, "password": password})

        session["access_token"] = auth_res.session.access_token
        session["user_id"]      = auth_res.user.id

        # Guardar nombre y rol en sesion
        sb_service = get_service_client()
        prof = (
            sb_service.table("profiles")
            .select("full_name,role,active")
            .eq("id", session["user_id"])
            .single()
            .execute()
        )
        profile_data = prof.data or {}
        session["user_name"] = profile_data.get("full_name") or "Usuario"
        session["user_role"] = profile_data.get("role") or "sales"

        if not profile_data.get("active", True):
            session.clear()
            flash("Tu cuenta está desactivada. Contacta al administrador.", "error")
            return redirect(url_for("auth.login_get"))

        flash("Bienvenido 👋", "success")

        # Redirigir según rol
        role = session["user_role"]

        # Recordatorio de cotizaciones pendientes de seguimiento (toast al entrar).
        # admin/developer: todas; ventas: sólo las suyas; ops: no aplica.
        if role in ("admin", "sales", "developer"):
            try:
                from blueprints.quotations.service import pending_followups
                owner = None if role in ("admin", "developer") else session["user_id"]
                pf = pending_followups(owner)
                if pf["total"]:
                    partes = []
                    if pf["sent"]:    partes.append(f"{pf['sent']} enviada(s)")
                    if pf["expired"]: partes.append(f"{pf['expired']} vencida(s)")
                    if pf["draft"]:   partes.append(f"{pf['draft']} en borrador")
                    flash(
                        f"Tienes {pf['total']} cotización(es) pendientes de seguimiento: "
                        + ", ".join(partes) + ". Revísalas para saber si fueron aceptadas o rechazadas.",
                        "warning" if pf["expired"] else "info",
                    )
            except Exception as exc:
                print(f"[login] recordatorio seguimiento: {exc}")


        if role == "ops":
            return redirect(url_for("events.events_list"))
        if role == "sales":
            return redirect(url_for("quotations.quotations_list"))
        return redirect(url_for("dashboard.dashboard"))

    except Exception as e:
        msg = getattr(e, "message", None) or str(e)
        if "Email not confirmed" in msg:
            flash(
                "Tu correo no está confirmado. Revisa tu bandeja o reenvía el enlace de verificación.",
                "error",
            )
        elif "Invalid login credentials" in msg:
            flash("Credenciales inválidas. Verifica correo/contraseña.", "error")
        else:
            flash(f"Error de autenticación: {msg}", "error")
        return redirect(url_for("auth.login_get"))


@bp.get("/register")
def register_get():
    return render_template("auth/auth_register.html")


@bp.post("/register")
def register_post():
    sb = get_public_client()
    full_name = (request.form.get("full_name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    password2 = request.form.get("password2") or ""

    if not full_name or not email or not password:
        flash("Todos los campos son obligatorios.", "error")
        return redirect(url_for("auth.register_get"))
    if password != password2:
        flash("Las contraseñas no coinciden.", "error")
        return redirect(url_for("auth.register_get"))
    if len(password) < 8:
        flash("La contraseña debe tener al menos 8 caracteres.", "error")
        return redirect(url_for("auth.register_get"))

    redirect_url = request.host_url.rstrip("/") + "/login"

    try:
        res = sb.auth.sign_up(
            {
                "email": email,
                "password": password,
                "options": {
                    "data": {"full_name": full_name},
                    "email_redirect_to": redirect_url,
                },
            }
        )

        if not res.user:
            flash("Registro creado. Revisa tu correo para confirmar tu cuenta.", "success")
            return redirect(url_for("auth.login_get"))

        if res.session and res.session.access_token:
            session["access_token"] = res.session.access_token
            session["user_id"] = res.user.id
            session["user_name"] = full_name or "Usuario"
            flash("Cuenta creada y sesión iniciada.", "success")
            return redirect(url_for("items.items_list"))

        flash("Cuenta creada. Revisa tu correo para confirmar e iniciar sesión.", "success")
        return redirect(url_for("auth.login_get"))

    except Exception as e:
        msg = getattr(e, "message", None) or str(e)
        if "User already registered" in msg or "already registered" in msg:
            flash("Este correo ya está registrado.", "error")
        elif "weak password" in msg.lower():
            flash("Contraseña débil. Usa al menos 8 caracteres con números y letras.", "error")
        else:
            flash(f"Error al registrar: {msg}", "error")
        return redirect(url_for("auth.register_get"))


@bp.get("/reset-password")
def reset_password():
    return render_template(
        "auth/auth_reset_password.html",
        SUPABASE_URL=os.environ.get("SUPABASE_URL", ""),
        SUPABASE_ANON_KEY=os.environ.get("SUPABASE_ANON_KEY", ""),
    )


@bp.get("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada.", "success")
    return redirect(url_for("auth.login_get"))
