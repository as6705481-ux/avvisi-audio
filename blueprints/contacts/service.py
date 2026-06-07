# blueprints/contacts/service.py
from __future__ import annotations

from extensions.supabase import get_service_client


def list_contacts():
    sb = get_service_client()
    res = (
        sb.table("contacts")
        .select("id, client_id, name, email, phone, role, is_primary, created_at, clients(id,name)")
        .order("created_at", desc=True)
        .execute()
    )
    rows = res.data or []

    # Normaliza para el HTML: contact["client_name"]
    for c in rows:
        client = c.get("clients") or {}
        c["client_name"] = client.get("name") or "—"

    return rows



def list_clients_for_contacts():
    sb = get_service_client()
    res = sb.table("clients").select("id,name").order("name", desc=False).execute()
    return res.data or []


def get_contact(contact_id: str):
    sb = get_service_client()
    return sb.table("contacts").select("*").eq("id", contact_id).single().execute().data


def create_contact(form: dict):
    client_id = (form.get("client_id") or "").strip() or None
    is_primary = True if (form.get("is_primary") == "1" or form.get("is_primary") is True) else False

    payload = {
        "client_id": client_id,
        "name": (form.get("name") or "").strip(),
        "phone": (form.get("phone") or "").strip(),
        "email": (form.get("email") or "").strip().lower(),
        "role": (form.get("role") or "").strip(),
        "is_primary": is_primary,
    }

    sb = get_service_client()

    # Si viene como principal, desmarcar otros del mismo cliente (como el viejo)
    if is_primary and client_id:
        sb.table("contacts").update({"is_primary": False}).eq("client_id", client_id).eq("is_primary", True).execute()

    res = sb.table("contacts").insert(payload).execute()
    return (res.data or [None])[0]


def update_contact(contact_id: str, form: dict):
    client_id = (form.get("client_id") or "").strip() or None
    is_primary = True if (form.get("is_primary") == "1" or form.get("is_primary") is True) else False

    payload = {
        "client_id": client_id,
        "name": (form.get("name") or "").strip(),
        "phone": (form.get("phone") or "").strip(),
        "email": (form.get("email") or "").strip().lower(),
        "role": (form.get("role") or "").strip(),
        "is_primary": is_primary,
    }

    sb = get_service_client()

    # Si se marca como principal, asegurar único por cliente (como el viejo)
    if is_primary and client_id:
        sb.table("contacts").update({"is_primary": False}) \
            .eq("client_id", client_id) \
            .eq("is_primary", True) \
            .neq("id", contact_id) \
            .execute()

    res = sb.table("contacts").update(payload).eq("id", contact_id).execute()
    return (res.data or [None])[0]


def set_contact_primary(contact_id: str, is_primary: bool = True):
    """
    Replica contact_set_primary del código viejo, con opción de unset.
    """
    sb = get_service_client()

    # obtener client_id del contacto
    c = sb.table("contacts").select("id,client_id").eq("id", contact_id).single().execute().data
    if not c:
        raise ValueError("Contacto no encontrado.")
    client_id = c.get("client_id")

    if not client_id:
        # contacto sin cliente asociado: solo set/unset en ese contacto
        sb.table("contacts").update({"is_primary": bool(is_primary)}).eq("id", contact_id).execute()
        return True

    if is_primary:
        sb.table("contacts").update({"is_primary": False}).eq("client_id", client_id).eq("is_primary", True).execute()

    sb.table("contacts").update({"is_primary": bool(is_primary)}).eq("id", contact_id).execute()
    return True


def delete_contact(contact_id: str):
    sb = get_service_client()
    sb.table("contacts").delete().eq("id", contact_id).execute()
    return True
