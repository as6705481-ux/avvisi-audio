from __future__ import annotations

from extensions.supabase import get_service_client


def list_events():
    sb = get_service_client()
    res = (
        sb.table("events")
        .select(
            "*,"
            "clients!events_client_id_fkey(id,name),"
            "contacts!events_contact_id_fkey(id,name,email,phone)"
        )
        .order("start_at", desc=True)
        .execute()
    )

    return res.data or []


def list_contacts():
    sb = get_service_client()
    res = (
        sb.table("contacts")
        .select("* , contacts(name)")
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def list_profiles():
    sb = get_service_client()
    res = (
        sb.table("profiles")
        .select("* , profiles(name)")
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def list_clients_for_events():
    sb = get_service_client()
    res = sb.table("clients").select("id,name").order("name", desc=False).execute()
    return res.data or []


def get_event(event_id: str):
    sb = get_service_client()

    res = (
        sb.table("events")
          .select("""
            *,
            clients:id, name,
            contacts:id, name,
            profiles:created_by(id, full_name)
          """)
          .eq("id", event_id)
          .single()
          .execute()
    )
    return res.data


def create_event(payload: dict):
    sb = get_service_client()
    res = sb.table("events").insert(payload).execute()
    return (res.data or [None])[0]


def update_event(event_id: str, payload: dict):
    sb = get_service_client()
    res = sb.table("events").update(payload).eq("id", event_id).execute()
    return (res.data or [None])[0]


def delete_event(event_id: str):
    sb = get_service_client()
    sb.table("events").delete().eq("id", event_id).execute()
    return True


def get_quote_for_event(quote_id: str):
    sb = get_service_client()
    q = sb.table("quotations").select("* , clients(name)").eq("id", quote_id).single().execute().data
    return q
