from __future__ import annotations

from datetime import datetime
from typing import Any

from extensions.supabase import get_service_client

# Si USER_ROLES vive en config.py o constants.py, importalo desde ahí.
# Ejemplo:
# from config import USER_ROLES
USER_ROLES = {"admin", "sales", "ops", "developer"}  # <-- reemplazá por tu fuente real


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return default


def list_users() -> list[dict]:
    sb = get_service_client()
    res = (
        sb.table("profiles")
        .select("id, full_name, phone, role, active, email, base_salary, created_at, updated_at")
        .order("created_at")
        .execute()
    )
    return res.data or []


def get_user_profile(user_id: str) -> dict | None:
    sb = get_service_client()
    return (
        sb.table("profiles")
        .select("id, full_name, phone, role, active, email, base_salary, created_at, updated_at")
        .eq("id", user_id)
        .single()
        .execute()
        .data
    )


def get_user_email_from_auth(user_id: str) -> str | None:
    sb = get_service_client()
    try:
        u = sb.auth.admin.get_user_by_id(user_id)
        return getattr(u.user, "email", None)
    except Exception:
        return None


def create_user(form: dict[str, Any]) -> str:
    """
    Crea usuario en auth.users y upsert en profiles.
    Retorna user_id.
    """
    sb = get_service_client()

    full_name = (form.get("full_name") or "").strip() or None
    email = (form.get("email") or "").strip()
    phone = (form.get("phone") or "").strip() or None
    role = (form.get("role") or "sales").strip()
    password = form.get("password") or ""
    active = True if form.get("active") == "1" else False
    base_salary = _to_float(form.get("base_salary"))

    if role not in USER_ROLES:
        raise ValueError("Rol inválido.")

    if not email or not password:
        raise ValueError("Correo y contraseña son obligatorios.")

    created = sb.auth.admin.create_user(
        {
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"full_name": full_name, "phone": phone},
        }
    )
    uid = created.user.id

    # el trigger pudo crear profile; igual hacemos upsert para asegurar campos
    sb.table("profiles").upsert(
        {
            "id": uid,
            "full_name": full_name,
            "phone": phone,
            "role": role,
            "email": email,
            "active": active,
            "base_salary": base_salary,
            "updated_at": datetime.utcnow().isoformat(),
        }
    ).execute()

    return uid


def update_user(user_id: str, form: dict) -> bool:
    sb = get_service_client()

    profile = get_user_profile(user_id)
    if not profile:
        raise ValueError("Perfil no encontrado.")

    current_email = get_user_email_from_auth(user_id)

    full_name = (form.get("full_name") or "").strip() or None
    new_email = (form.get("email") or "").strip()
    phone = (form.get("phone") or "").strip() or None
    role = (form.get("role") or "").strip()
    active = True if form.get("active") == "1" else False
    base_salary = _to_float(form.get("base_salary"))

    new_password = (form.get("new_password") or "").strip()

    if role not in USER_ROLES:
        raise ValueError("Rol inválido.")

    sb.table("profiles").update(
        {
            "full_name": full_name,
            "phone": phone,
            "role": role,
            "active": active,
            "base_salary": base_salary,
            "updated_at": datetime.utcnow().isoformat(),
            "email": (new_email or current_email or profile.get("email")),
        }
    ).eq("id", user_id).execute()

    upd_payload = {}
    if new_email and new_email != (current_email or ""):
        upd_payload["email"] = new_email
        upd_payload["email_confirm"] = True

    if new_password:
        upd_payload["password"] = new_password

    if upd_payload:
        sb.auth.admin.update_user_by_id(user_id, upd_payload)

    return True


def set_user_active(user_id: str, active: bool) -> bool:
    sb = get_service_client()
    sb.table("profiles").update(
        {"active": active, "updated_at": datetime.utcnow().isoformat()}
    ).eq("id", user_id).execute()
    return True


def delete_user(user_id: str) -> bool:
    sb = get_service_client()
    sb.auth.admin.delete_user(user_id)
    return True
