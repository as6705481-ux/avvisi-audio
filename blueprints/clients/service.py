# blueprints/clients/service.py
from __future__ import annotations

from extensions.supabase import get_service_client


def list_clients():
    sb = get_service_client()
    res = sb.table("clients").select("*").order("created_at", desc=True).execute()
    return res.data or []


def get_client(client_id: str):
    sb = get_service_client()
    return sb.table("clients").select("*").eq("id", client_id).single().execute().data


def create_client(form: dict):
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
        "tax_id": (form.get("tax_id") or "").strip(),
        "phone": (form.get("phone") or "").strip(),
        "email": (form.get("email") or "").strip().lower(),
        "billing_address": address,
        "organization_id": (form.get("organization_id") or "").strip(),
        "is_eventual": bool(form.get("is_eventual")),
    }
    sb = get_service_client()
    res = sb.table("clients").insert(payload).execute()
    return (res.data or [None])[0]


def update_client(client_id: str, form: dict):
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
        "tax_id": (form.get("tax_id") or "").strip(),
        "phone": (form.get("phone") or "").strip(),
        "email": (form.get("email") or "").strip().lower(),
        "billing_address": address,
        "organization_id": (form.get("organization_id") or "").strip(),
        "is_eventual": bool(form.get("is_eventual")),
    }
    sb = get_service_client()
    res = sb.table("clients").update(payload).eq("id", client_id).execute()
    return (res.data or [None])[0]


def delete_client(client_id: str):
    sb = get_service_client()
    sb.table("clients").delete().eq("id", client_id).execute()
    return True
