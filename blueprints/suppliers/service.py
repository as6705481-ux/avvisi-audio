# blueprints/suppliers/service.py
from __future__ import annotations

from extensions.supabase import get_service_client


def list_suppliers():
    sb = get_service_client()
    res = sb.table("suppliers").select("*").order("created_at", desc=True).execute()
    return res.data or []


def get_supplier(supplier_id: str):
    sb = get_service_client()
    return sb.table("suppliers").select("*").eq("id", supplier_id).single().execute().data


def create_supplier(form: dict):
    address = {
        "street":  (form.get("street")  or "").strip(),
        "city":    (form.get("city")    or "").strip(),
        "state":   (form.get("state")   or "").strip(),
        "zip":     (form.get("zip")     or "").strip(),
        "country": (form.get("country") or "").strip(),
    }
    if not any(address.values()):
        address = None

    payload = {
        "name": (form.get("name") or "").strip(),
        "phone": (form.get("phone") or "").strip(),
        "email": (form.get("email") or "").strip().lower(),
        "tax_id": (form.get("tax_id") or "").strip(),
        "address": address,
        "notes": (form.get("notes") or "").strip(),
        # si tu tabla tiene "active", lo puedes setear aquí:
        # "active": True,
    }
    sb = get_service_client()
    res = sb.table("suppliers").insert(payload).execute()
    return (res.data or [None])[0]


def update_supplier(supplier_id: str, form: dict):
    address = {
        "street":  (form.get("street")  or "").strip(),
        "city":    (form.get("city")    or "").strip(),
        "state":   (form.get("state")   or "").strip(),
        "zip":     (form.get("zip")     or "").strip(),
        "country": (form.get("country") or "").strip(),
    }
    if not any(address.values()):
        address = None

    payload = {
        "name": (form.get("name") or "").strip(),
        "phone": (form.get("phone") or "").strip(),
        "email": (form.get("email") or "").strip().lower(),
        "tax_id": (form.get("tax_id") or "").strip(),
        "address": address,
        "notes": (form.get("notes") or "").strip(),
        "active": bool(form.get("active")),
    }
    sb = get_service_client()
    res = sb.table("suppliers").update(payload).eq("id", supplier_id).execute()
    return (res.data or [None])[0]


def set_supplier_status(supplier_id: str, active: bool):
    """
    Replica la lógica vieja:
    suppliers.active = True/False
    (y fallback por si alguien lo renombró a is_active)
    """
    sb = get_service_client()

    # 1) viejo: active
    try:
        sb.table("suppliers").update({"active": bool(active)}).eq("id", supplier_id).execute()
        return True
    except Exception:
        pass

    # 2) fallback: is_active
    sb.table("suppliers").update({"is_active": bool(active)}).eq("id", supplier_id).execute()
    return True


def delete_supplier(supplier_id: str):
    sb = get_service_client()
    sb.table("suppliers").delete().eq("id", supplier_id).execute()
    return True  # <-- FIX: quitar coma
