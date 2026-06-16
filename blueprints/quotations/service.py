# blueprints/quotations/service.py
from __future__ import annotations

import os
import re as _re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict
from config import Settings

from flask import abort, redirect, render_template, url_for

from ..clients.service import create_client
from ..contacts.service import create_contact
from ..events.service import create_event
from ..items.service import create_item, list_categories, list_suppliers
from utils.dates import parse_datetime_local

from extensions.supabase import get_service_client

# ==========================
# Defaults / constantes
# ==========================
DEFAULT_CURRENCY = "HNL"
RES_STATUS_FIRM = "firm"

VALID_STATUSES = {"draft", "sent", "accepted", "declined", "expired", "cancelled", "converted", "void"}

ALLOWED_TRANSITIONS = {
    "draft":     {"sent", "cancelled", "void"},
    "sent":      {"accepted", "declined", "expired", "cancelled", "void"},
    "accepted":  {"converted", "cancelled", "void"},
    "declined":  {"void"},
    "expired":   {"void"},
    "cancelled": {"void"},
    "converted": {"draft"},
    "void":      {"draft"},
}


# ==========================
# Helpers simples
# ==========================
def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _to_int(x: Any, default: int = 0) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def gen_quote_number(sb) -> str:
    """Genera el próximo número de cotización en formato YYYYNNN (ej: 2025001, 2025002)."""
    year = datetime.utcnow().year
    rows = (
        sb.table("quotations")
        .select("quote_number")
        .like("quote_number", f"{year}%")
        .execute()
        .data or []
    )
    max_seq = 0
    for r in rows:
        qn = r.get("quote_number") or ""
        if qn.startswith(str(year)):
            rest = qn[4:]
            # quitar caracteres no numéricos del inicio (ej: "-", "_")
            rest = _re.sub(r"^[^0-9]+", "", rest)
            m = _re.match(r"^(\d+)", rest)
            if m:
                try:
                    n = int(m.group(1))
                    if n > max_seq:
                        max_seq = n
                except ValueError:
                    pass
    return f"{year}{max_seq + 1:03d}"

def _parse_dt_local(local_str: str, tzname: str) -> str:
    """
    Recibe 'YYYY-MM-DDTHH:MM' (input datetime-local) y devuelve ISO UTC.
    """
    if not local_str:
        return None

    # ejemplo: '2026-01-23T18:30'
    dt_local = datetime.fromisoformat(local_str)

    tz = ZoneInfo(tzname or "UTC")
    dt_local = dt_local.replace(tzinfo=tz)

    dt_utc = dt_local.astimezone(ZoneInfo("UTC"))
    return dt_utc.replace(tzinfo=None).isoformat()

# ==========================
# LISTA (con names map)
# ==========================
def list_quotations_with_names(limit: int = 500):
    sb = get_service_client()

    def _quotes():
        return (
            sb.table("quotations")
            .select("id, quote_number, client_id, contact_id, event_id, owner_id, currency, status, total, deposit_due, created_at, valid_until")
            .is_("deleted_at", "null")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data or []
        )
    def _clients():  return sb.table("clients").select("id,name").execute().data or []
    def _contacts(): return sb.table("contacts").select("id,name").execute().data or []
    def _events():   return sb.table("events").select("id,name").execute().data or []
    def _profiles(): return sb.table("profiles").select("id,full_name").execute().data or []

    with ThreadPoolExecutor(max_workers=5) as ex:
        f_rows    = ex.submit(_quotes)
        f_clients = ex.submit(_clients)
        f_contacts= ex.submit(_contacts)
        f_events  = ex.submit(_events)
        f_profiles= ex.submit(_profiles)
        rows = f_rows.result()
        cli  = f_clients.result()
        con  = f_contacts.result()
        ev   = f_events.result()
        own  = f_profiles.result()

    names = {
        "clients":  {x["id"]: x["name"]       for x in cli},
        "contacts": {x["id"]: x["name"]       for x in con},
        "events":   {x["id"]: x["name"]       for x in ev},
        "profiles": {x["id"]: x["full_name"]  for x in own},
    }
    return rows, names


# ==========================
# Catálogos (add/edit)
# ==========================
def get_quote_add_context() -> dict:
    sb = get_service_client()

    def _clients():    return sb.table("clients").select("id,name").order("name").execute().data or []
    def _contacts():   return sb.table("contacts").select("id,client_id,name").order("name").execute().data or []
    def _events():     return sb.table("events").select("id,name,client_id,start_at,end_at").order("start_at", desc=True).limit(200).execute().data or []
    def _owners():
        rows = sb.table("profiles").select("id,full_name,role").order("full_name").execute().data or []
        # Los desarrolladores del sistema no son parte del equipo: no se ofrecen como responsables.
        return [o for o in rows if o.get("role") != "developer"]
    def _categories(): return list_categories()
    def _suppliers():  return list_suppliers()
    def _items():
        return (
            sb.table("items")
            .select("id,sku,name,item_type,unit,default_rate,low_rate,description")
            .eq("active", True)
            .order("name")
            .execute()
            .data or []
        )

    with ThreadPoolExecutor(max_workers=7) as ex:
        f_cli  = ex.submit(_clients)
        f_con  = ex.submit(_contacts)
        f_ev   = ex.submit(_events)
        f_own  = ex.submit(_owners)
        f_cat  = ex.submit(_categories)
        f_sup  = ex.submit(_suppliers)
        f_items= ex.submit(_items)

    return {
        "clients":          f_cli.result(),
        "contacts":         f_con.result(),
        "events":           f_ev.result(),
        "owners":           f_own.result(),
        "items":            f_items.result(),
        "categories":       f_cat.result(),
        "suppliers":        f_sup.result(),
        "default_currency": DEFAULT_CURRENCY,
    }


def get_quote_edit_context(quote_id: str) -> dict:
    sb = get_service_client()

    q = sb.table("quotations").select("*").eq("id", quote_id).single().execute().data
    if not q:
        raise ValueError("Cotización no encontrada.")

    ctx = get_quote_add_context()

    # líneas
    lines = (
        sb.table("quotation_items")
        .select(
            "id, item_id, custom_name, description, section, item_type, quantity, unit, unit_price, discount_pct, line_subtotal, line_tax, line_total, sort_order, days"
        )
        .eq("quotation_id", quote_id)
        .order("sort_order")
        .execute()
        .data
        or []
    )

    return {
        "q": q, 
        "quotation": q,
        "lines": lines,
        **ctx,
    }


# ==========================
# Totales
# ==========================
def recompute_totals(sb, quote_id: str):
    """Recalcula line_subtotal/line_tax/line_total por línea y actualiza
    subtotal/tax_total/discount_total/total en la cabecera de la cotización.

    NOTA: usa UPDATE individual por línea (no upsert) para evitar que
    Supabase rechace el upsert parcial por columnas NOT NULL ausentes.
    """
    rows = (
        sb.table("quotation_items")
        .select("id, quantity, unit_price, days, discount_pct")
        .eq("quotation_id", quote_id)
        .execute()
        .data
        or []
    )

    q_data = (
        sb.table("quotations")
        .select("tax_rate")
        .eq("id", quote_id)
        .single()
        .execute()
        .data
    ) or {}
    tax_rate = float(q_data.get("tax_rate") or 0)

    subtotal       = 0.0
    discount_total = 0.0
    tax_total      = 0.0
    total          = 0.0

    for ln in rows:
        qty  = float(ln.get("quantity") or 0)
        days = float(ln.get("days") or 1)
        price = float(ln.get("unit_price") or 0)
        disc  = float(ln.get("discount_pct") or 0)

        gross       = qty * days * price
        disc_amount = round(gross * disc / 100.0, 6)
        net         = gross - disc_amount
        line_tax    = round(net * tax_rate / 100.0, 6)
        line_tot    = net + line_tax

        # UPDATE directo — más confiable que upsert con columnas parciales
        sb.table("quotation_items").update({
            "line_subtotal": round(net, 6),
            "line_tax":      line_tax,
            "line_total":    round(line_tot, 6),
        }).eq("id", ln["id"]).execute()

        subtotal       += net
        discount_total += disc_amount
        tax_total      += line_tax
        total          += line_tot

    sb.table("quotations").update({
        "subtotal":       round(subtotal, 2),
        "discount_total": round(discount_total, 2),
        "tax_total":      round(tax_total, 2),
        "total":          round(total, 2),
        "updated_at":     datetime.utcnow().isoformat(),
    }).eq("id", quote_id).execute()
    return True


# ==========================
# CREATE (con líneas)
# ==========================
def _get_or_create_eventual_contact(sb, client_id: str) -> str | None:
    """Busca o crea 'Contacto Eventual' para el cliente dado."""
    if not client_id:
        return None
    try:
        rows = (
            sb.table("contacts")
            .select("id")
            .eq("client_id", client_id)
            .eq("name", "Contacto Eventual")
            .limit(1)
            .execute()
            .data or []
        )
        if rows:
            return rows[0]["id"]
        res = sb.table("contacts").insert({
            "name": "Contacto Eventual",
            "client_id": client_id,
        }).execute()
        return ((res.data or [{}])[0]).get("id")
    except Exception as exc:
        print(f"[quotations] eventual contact: {exc}")
        return None


def create_quote_from_form(form) -> tuple[str, str]:
    sb = get_service_client()

    client_id  = (form.get("client_id") or "").strip()
    contact_id = (form.get("contact_id") or "").strip() or None
    if not contact_id and client_id:
        contact_id = _get_or_create_eventual_contact(sb, client_id)
    event_id   = (form.get("event_id") or "").strip() or None
    owner_id   = (form.get("owner_id") or "").strip()
    currency   = (form.get("currency") or DEFAULT_CURRENCY).strip()[:3].upper()

    exchange  = _to_float(form.get("exchange_rate"), 1.0) or 1.0
    valid_u   = (datetime.utcnow().date() + timedelta(days=30)).isoformat()
    notes_int = (form.get("notes_internal") or "").strip() or None
    notes_cli = (form.get("notes_client") or "").strip() or None
    deposit   = _to_float(form.get("deposit_due"), 0.0)
    apply_tax = (form.get("apply_tax") or "yes").lower().strip()
    tax_rate  = 15.0 if apply_tax == "yes" else 0.0
    if not client_id or not owner_id:
        raise ValueError("Cliente y Propietario son obligatorios.")

    quote_no = gen_quote_number(sb)

    # 1) cabecera
    resp = (
        sb.table("quotations")
        .insert(
            {
                "quote_number": quote_no,
                "client_id": client_id,
                "contact_id": contact_id,
                "event_id": event_id,
                "owner_id": owner_id,
                "currency": currency,
                "exchange_rate": exchange,
                "status": "draft",
                "valid_until": valid_u,
                "notes_internal": notes_int,
                "notes_client": notes_cli,
                "deposit_due": deposit,
                "subtotal": 0.0,
                "discount_total": 0.0,
                "tax_total": 0.0,
                "tax_rate": tax_rate,
                "total": 0.0,
            },
            returning="representation",
        )
        .execute()
    )

    rows = getattr(resp, "data", None) or []
    if not rows:
        raise RuntimeError(f"Insert sin data. Detalle: {getattr(resp,'error',None)}")

    quote_id = rows[0]["id"]

    # 2) revision + 3) status history (best effort)
    try:
        sb.table("quotation_revisions").insert(
            {"quotation_id": quote_id, "version": 1, "created_by": owner_id, "comment": "Creación de cotización"}
        ).execute()
    except Exception:
        pass

    try:
        sb.table("quotation_status_history").insert(
            {"quotation_id": quote_id, "old_status": None, "new_status": "draft", "changed_by": owner_id, "note": "Creada en borrador"}
        ).execute()
    except Exception:
        pass

    # 4) líneas desde arrays (viejo)
    _insert_quote_lines_from_form(sb, quote_id, form)

    # 5) totals
    try:
        recompute_totals(sb, quote_id)
    except Exception as exc:
        print(f"[recompute_totals] error en quote {quote_id}: {exc}")

    return quote_id, quote_no


def _insert_quote_lines_from_form(sb, quote_id: str, form):
    item_ids   = form.getlist("item_id[]")
    days_list  = form.getlist("days[]")
    qty_list   = form.getlist("quantity[]")
    modes      = form.getlist("price_mode[]")
    prices_in  = form.getlist("unit_price[]")
    line_descs = form.getlist("line_description[]")


    raw_rows = []
    for idx, iid in enumerate(item_ids):
        iid = (iid or "").strip()
        if not iid:
            continue

        days = _to_float(days_list[idx], 1.0) if idx < len(days_list) and days_list[idx] else 1.0
        if days <= 0:
            days = 1.0

        qty = _to_float(qty_list[idx], 1.0) if idx < len(qty_list) and qty_list[idx] else 1.0
        if qty <= 0:
            continue

        mode = (modes[idx] if idx < len(modes) else "std") or "std"
        mode = mode.strip().lower()
        if mode not in ("std", "low", "custom"):
            mode = "std"

        up_custom = None
        if mode == "custom":
            rawp = prices_in[idx] if idx < len(prices_in) else ""
            up_custom = _to_float(rawp, None) if str(rawp).strip() != "" else None
            if up_custom is not None and up_custom < 0:
                up_custom = None

        desc = (line_descs[idx] if idx < len(line_descs) else "") or ""
        raw_rows.append(
            {"item_id": iid, "days": days, "qty": qty, "mode": mode, "unit_price_custom": up_custom, "desc": (desc.strip() or None)}
        )

    if not raw_rows:
        return True

    unique_ids = sorted({r["item_id"] for r in raw_rows})
    meta_rows = (
        sb.table("items")
        .select("id,name,item_type,unit,default_rate,low_rate")
        .in_("id", unique_ids)
        .execute()
        .data
        or []
    )
    meta = {m["id"]: m for m in meta_rows}

    to_insert = []
    sort_order = 1
    
    for r in raw_rows:
        it = meta.get(r["item_id"])
        if not it:
            continue

        std = _to_float(it.get("default_rate"), 0.0)
        low = _to_float(it.get("low_rate"), 0.0)

        if r["mode"] == "low":
            unit_price = low
        elif r["mode"] == "custom" and r["unit_price_custom"] is not None:
            unit_price = float(r["unit_price_custom"])
        else:
            unit_price = std

        to_insert.append(
            {
                "quotation_id": quote_id,
                "item_id": r["item_id"],
                "custom_name": it.get("name"),
                "description": r["desc"],
                "item_type": it.get("item_type"),
                "quantity": float(r["qty"]),
                "unit": it.get("unit") or "unit",
                "unit_price": float(unit_price),
                "sort_order": sort_order,
                "days": float(r["days"]),
            }
        )
        sort_order += 1

    if to_insert:
        sb.table("quotation_items").insert(to_insert).execute()

    return True


# ==========================
# EDIT: add line / update header
# ==========================
def add_quote_line(quote_id: str, form):
    sb = get_service_client()

    item_id = (form.get("item_id") or "").strip()
    qty = _to_float(form.get("quantity"), 1.0)
    days = _to_float(form.get("days"), 1.0)
    disc = _to_float(form.get("discount_pct"), 0.0)
    section = (form.get("section") or "").strip() or None
    desc = (form.get("line_description") or "").strip() or None

    if not item_id:
        raise ValueError("Selecciona un ítem.")

    it = sb.table("items").select("id,name,item_type,unit,default_rate,description").eq("id", item_id).single().execute().data
    if not it:
        raise ValueError("Ítem no válido.")

    # sort_order = len(lines)+1
    cnt = sb.table("quotation_items").select("id", count="exact").eq("quotation_id", quote_id).execute().count or 0
    sort_order = int(cnt) + 1

    sb.table("quotation_items").insert(
        {
            "quotation_id": quote_id,
            "item_id": item_id,
            "custom_name": it.get("name"),
            "description": desc,
            "section": section,
            "item_type": it.get("item_type"),
            "quantity": qty,
            "unit": it.get("unit") or "unit",
            "days": days,
            "unit_price": _to_float(it.get("default_rate"), 0.0),
            "discount_pct": disc,
            "sort_order": sort_order,
        }
    ).execute()

    recompute_totals(sb, quote_id)
    return True


def update_quote_header_from_form(quote_id: str, form, allow_quote_number: bool = False):
    sb = get_service_client()

    q = sb.table("quotations").select("id,client_id,owner_id,currency,exchange_rate,deposit_due,tax_rate,valid_until,created_at").eq("id", quote_id).single().execute().data
    if not q:
        raise ValueError("Cotización no encontrada.")

    apply_tax = (form.get("apply_tax") or "yes").lower().strip()
    new_tax_rate = 15.0 if apply_tax == "yes" else 0.0

    upd = {
        "client_id":      (form.get("client_id") or "").strip() or q["client_id"],
        "contact_id":     (form.get("contact_id") or "").strip() or None,
        "event_id":       (form.get("event_id") or "").strip() or None,
        "owner_id":       (form.get("owner_id") or q["owner_id"]).strip(),
        "currency":       (form.get("currency") or q.get("currency") or DEFAULT_CURRENCY).strip()[:3].upper(),
        "exchange_rate":  _to_float(form.get("exchange_rate"), q.get("exchange_rate") or 1.0),
        "notes_internal": (form.get("notes_internal") or None),
        "notes_client":   (form.get("notes_client") or None),
        "deposit_due":    _to_float(form.get("deposit_due"), q.get("deposit_due") or 0.0),
        "tax_rate":       new_tax_rate,
        "updated_at":     _now_iso(),
    }

    # valid_until is always emission date + 30 days; backfill if missing on old records
    if not q.get("valid_until") and q.get("created_at"):
        try:
            created_dt = datetime.fromisoformat(q["created_at"].replace("Z", "+00:00"))
            upd["valid_until"] = (created_dt.date() + timedelta(days=30)).isoformat()
        except Exception:
            pass

    # Solo admin puede cambiar el número de cotización
    if allow_quote_number:
        new_qn = (form.get("quote_number") or "").strip()
        if new_qn:
            upd["quote_number"] = new_qn

    sb.table("quotations").update(upd).eq("id", quote_id).execute()
    # Recompute siempre: tax_rate puede haber cambiado
    recompute_totals(sb, quote_id)
    return True


# ==========================
# Lines update/delete
# ==========================
def update_quote_line_from_form(quote_id: str, line_id: str, form):
    sb = get_service_client()

    days = _to_int(form.get("days"), 1)
    if days <= 0:
        days = 1

    qty = _to_float(form.get("quantity"), 1.0)
    if qty <= 0:
        qty = 1.0

    price = _to_float(form.get("unit_price"), 0.0)
    if price < 0:
        price = 0.0

    payload = {
        "custom_name": (form.get("custom_name") or "").strip() or None,
        "description": (form.get("description") or "").strip() or None,
        "days": days,
        "quantity": qty,
        "unit": (form.get("unit") or "unit").strip() or "unit",
        "unit_price": price,
    }

    sb.table("quotation_items").update(payload).eq("id", line_id).eq("quotation_id", quote_id).execute()
    recompute_totals(sb, quote_id)
    return True


def delete_quote_line(quote_id: str, line_id: str):
    sb = get_service_client()
    sb.table("quotation_items").delete().eq("id", line_id).eq("quotation_id", quote_id).execute()
    recompute_totals(sb, quote_id)
    return True


# ==========================
# Status transitions
# ==========================
def set_quote_status_from_form(quote_id: str, form):
    sb = get_service_client()

    target = (form.get("status") or "").strip().lower()
    actor = (form.get("actor_id") or "").strip() or None
    note = (form.get("note") or "").strip() or None

    if target not in VALID_STATUSES:
        raise ValueError("Estado inválido.")

    q = sb.table("quotations").select("id,status").eq("id", quote_id).single().execute().data
    if not q:
        raise ValueError("Cotización no encontrada.")

    old = (q.get("status") or "").strip().lower()
    if target == old:
        return True

    if target not in ALLOWED_TRANSITIONS.get(old, set()):
        raise ValueError(f"No se puede pasar de {old} a {target}.")

    time_updates = {}
    now_iso = _now_iso()
    if target == "sent":
        time_updates["sent_at"] = now_iso
    if target == "accepted":
        time_updates["accepted_at"] = now_iso

    sb.table("quotations").update({"status": target, "updated_at": now_iso, **time_updates}).eq("id", quote_id).execute()

    try:
        sb.table("quotation_status_history").insert(
            {"quotation_id": quote_id, "old_status": old, "new_status": target, "changed_by": actor, "note": note}
        ).execute()
    except Exception:
        pass

    return True


# ==========================
# Delete (soft) / Papelera
# ==========================
def delete_quote_strict(quote_id: str):
    """Soft-delete: mueve a papelera seteando deleted_at."""
    sb = get_service_client()
    q = sb.table("quotations").select("status, quote_number").eq("id", quote_id).single().execute().data
    if not q:
        raise ValueError("Cotización no encontrada.")

    st = (q.get("status") or "").strip().lower()
    if st not in {"draft", "cancelled", "void", "expired", "declined"}:
        raise ValueError("No se puede eliminar una cotización aceptada o convertida. Primero anúlala.")

    sb.table("quotations").update({"deleted_at": _now_iso()}).eq("id", quote_id).execute()
    return True


def list_trash_quotations() -> tuple[list, dict]:
    """Devuelve cotizaciones en papelera (deleted_at IS NOT NULL)."""
    sb = get_service_client()
    rows = (
        sb.table("quotations")
        .select("id, quote_number, client_id, owner_id, status, total, created_at, deleted_at")
        .not_.is_("deleted_at", "null")
        .order("deleted_at", desc=True)
        .execute()
        .data or []
    )
    cli  = sb.table("clients").select("id,name").execute().data or []
    own  = sb.table("profiles").select("id,full_name").execute().data or []
    names = {
        "clients":  {x["id"]: x["name"]      for x in cli},
        "profiles": {x["id"]: x["full_name"] for x in own},
    }
    return rows, names


def restore_quote(quote_id: str):
    """Restaura una cotización de la papelera."""
    sb = get_service_client()
    sb.table("quotations").update({"deleted_at": None}).eq("id", quote_id).execute()
    return True


def permanent_delete_quote(quote_id: str):
    """Elimina definitivamente una cotización (solo desde papelera)."""
    sb = get_service_client()
    try:
        sb.table("quotation_items").delete().eq("quotation_id", quote_id).execute()
    except Exception:
        pass
    sb.table("quotations").delete().eq("id", quote_id).execute()
    return True


def create_event_from_quote(quote_id: str, request):
    """
    Handler estilo viejo pero usable desde blueprint.
    Retorna render_template(...) o redirect(...)
    """
    sb = get_service_client()

    q = sb.table("quotations").select("id,quote_number,client_id,contact_id,event_id").eq("id", quote_id).single().execute().data
    if not q:
        raise ValueError("Cotización no encontrada.")

    if q.get("event_id"):
        # Ajusta este endpoint al blueprint real de events si lo tenés:
        return redirect(url_for("events.event_edit_get", event_id=q["event_id"]))

    client = sb.table("clients").select("id,name").eq("id", q["client_id"]).single().execute().data
    if not client:
        raise ValueError("Cliente de la cotización no existe.")

    contacts = (
        sb.table("contacts")
        .select("id,client_id,name")
        .eq("client_id", q["client_id"])
        .order("is_primary", desc=True)
        .order("name")
        .execute()
        .data
        or []
    )

    owners = sb.table("profiles").select("id,full_name,role").order("full_name").execute().data or []
    # Los desarrolladores del sistema no son parte del equipo: no se ofrecen como responsables.
    owners = [o for o in owners if o.get("role") != "developer"]

    if request.method == "GET":
        suggested_name = f"Evento — {q['quote_number']}"
        # Ajusta tz_default si lo tenés
        return render_template(
            "events/event_from_quote.html",
            quotation=q,
            client=client,
            contacts=contacts,
            owners=owners,
            suggested_name=suggested_name,
            tz_default="UTC",
        )

    # POST
    name = (request.form.get("name") or "").strip()
    contact_id = (request.form.get("contact_id") or "").strip() or None
    venue = (request.form.get("venue") or "").strip() or None
    tzname = (request.form.get("timezone") or "UTC").strip() or "UTC"
    created_by = (request.form.get("created_by") or "").strip() or None

    start_local = (request.form.get("start_at") or "").strip()
    end_local = (request.form.get("end_at") or "").strip()
    build_local = (request.form.get("build_start_at") or "").strip()
    strike_local = (request.form.get("strike_end_at") or "").strip()

    if not name or not start_local or not end_local:
        raise ValueError("Nombre, Inicio y Fin son obligatorios.")

    # valida contacto pertenece al cliente
    if contact_id:
        cnt = (
            sb.table("contacts")
            .select("id", count="exact")
            .eq("id", contact_id)
            .eq("client_id", q["client_id"])
            .execute()
            .count
            or 0
        )
        if cnt == 0:
            raise ValueError("El contacto seleccionado no pertenece al cliente de la cotización.")

    start_iso = _parse_dt_local(start_local, tzname)
    end_iso = _parse_dt_local(end_local, tzname)
    build_iso = _parse_dt_local(build_local, tzname) if build_local else None
    strike_iso = _parse_dt_local(strike_local, tzname) if strike_local else None

    if not start_iso or not end_iso or end_iso <= start_iso:
        raise ValueError("Rango de fechas inválido.")

    ins = (
        sb.table("events")
        .insert(
            {
                "name": name,
                "client_id": q["client_id"],
                "contact_id": contact_id,
                "venue": venue,
                "start_at": start_iso,
                "end_at": end_iso,
                "timezone": tzname,
                "created_by": created_by or None,
                "notes": (request.form.get("notes") or "").strip() or None,
                "build_start_at": build_iso,
                "strike_end_at": strike_iso,
            }
        )
        .select("id")
        .single()
        .execute()
    )

    event_id = ins.data["id"]
    sb.table("quotations").update({"event_id": event_id}).eq("id", quote_id).execute()
    return redirect(url_for("quotations.quotation_edit_get", quote_id=quote_id))


# ==========================
# ACCEPT + reservas (tal cual viejo, compactado)
# ==========================
def _fetch_quote_core(sb, quote_id: str):
    q = sb.table("quotations").select("id,quote_number,status,event_id,client_id").eq("id", quote_id).single().execute().data
    if not q:
        raise ValueError("Cotización no encontrada.")
    if (q.get("status") or "").strip().lower() == "accepted":
        raise ValueError("La cotización ya está aceptada.")
    if not q.get("event_id"):
        raise ValueError("La cotización no tiene evento vinculado.")
    ev = sb.table("events").select("id,name,start_at,end_at,timezone").eq("id", q["event_id"]).single().execute().data
    if not ev:
        raise ValueError("El evento vinculado no existe.")
    if not ev.get("start_at") or not ev.get("end_at"):
        raise ValueError("El evento no tiene fechas de inicio/fin válidas.")
    return q, ev


def _fetch_quote_lines_with_items(sb, quote_id: str):
    rows = (
        sb.table("quotation_items")
        .select("id, item_id, item_type, quantity, unit, unit_price, discount_pct, start_at, end_at, section")
        .eq("quotation_id", quote_id)
        .order("sort_order")
        .execute()
        .data
        or []
    )
    if not rows:
        raise ValueError("La cotización no tiene líneas.")

    item_ids = sorted({r["item_id"] for r in rows if r.get("item_id")})
    meta = {}
    if item_ids:
        meta_rows = (
            sb.table("items")
            .select("id,item_type,default_rate,unit,active,rentable_capacity")
            .in_("id", item_ids)
            .execute()
            .data
            or []
        )
        meta = {m["id"]: m for m in meta_rows}
    return rows, meta


def _expand_bundle_components(sb, bundle_ids):
    if not bundle_ids:
        return {}
    comps = (
        sb.table("bundle_items")
        .select("bundle_id,item_id,quantity")
        .in_("bundle_id", sorted(bundle_ids))
        .execute()
        .data
        or []
    )
    out = {}
    for c in comps:
        out.setdefault(c["bundle_id"], []).append({"item_id": c["item_id"], "quantity": float(c["quantity"])})
    return out


def _compute_item_capacity(sb, item_id: str, fallback_assets: bool = True) -> int:
    it = sb.table("items").select("rentable_capacity").eq("id", item_id).single().execute().data
    cap = it.get("rentable_capacity") if it else None
    if cap is not None:
        try:
            return int(cap)
        except Exception:
            pass
    if not fallback_assets:
        return 0
    cnt = sb.table("assets").select("id", count="exact").eq("item_id", item_id).eq("active", True).execute().count or 0
    return int(cnt)


def _sum_overlapping_reserved(sb, item_id: str, start_iso: str, end_iso: str) -> int:
    rows = (
        sb.table("reservations")
        .select("id,quantity,start_at,end_at,status")
        .eq("item_id", item_id)
        .in_("status", ["tentative", "firm"])
        .lte("end_at", end_iso)      # aproximación
        .gte("start_at", start_iso)  # aproximación
        .execute()
        .data
        or []
    )
    total = 0
    for r in rows:
        s = r.get("start_at")
        e = r.get("end_at")
        if not s or not e:
            continue
        if s < end_iso and e > start_iso:
            total += int(r.get("quantity") or 0)
    return total


def _build_needed_reservations(sb, q_lines, items_meta, event, quote_id: str):
    start_ev = event["start_at"]
    end_ev = event["end_at"]

    needs = []
    bundles = [r for r in q_lines if r.get("item_type") == "bundle"]
    bundle_ids = [r["item_id"] for r in bundles if r.get("item_id")]
    bundle_map = _expand_bundle_components(sb, bundle_ids)

    for r in q_lines:
        s = r.get("start_at") or start_ev
        e = r.get("end_at") or end_ev
        if not s or not e or e <= s:
            continue

        if r.get("item_type") == "rentable":
            needs.append({"item_id": r["item_id"], "quantity": int(round(_to_float(r.get("quantity"), 0))), "start_at": s, "end_at": e})
        elif r.get("item_type") == "bundle":
            comps = bundle_map.get(r["item_id"], [])
            qty_parent = _to_float(r.get("quantity"), 0)
            for c in comps:
                comp_id = c["item_id"]
                comp_qty = _to_float(c["quantity"], 0) * qty_parent
                meta = items_meta.get(comp_id)
                if not meta:
                    continue
                if meta.get("item_type") != "rentable":
                    continue
                needs.append({"item_id": comp_id, "quantity": int(round(comp_qty)), "start_at": s, "end_at": e})

    compact = {}
    for n in needs:
        key = (n["item_id"], n["start_at"], n["end_at"])
        compact[key] = compact.get(key, 0) + int(n["quantity"])

    out = []
    for (item_id, s, e), qtty in compact.items():
        out.append({"item_id": item_id, "quantity": qtty, "start_at": s, "end_at": e, "quotation_id": quote_id, "event_id": event["id"]})
    return out


def _check_availability_or_raise(sb, reservations_needed):
    item_ids = sorted({r["item_id"] for r in reservations_needed})
    capacities = {iid: _compute_item_capacity(sb, iid) for iid in item_ids}

    shortages = []
    for r in reservations_needed:
        item_id = r["item_id"]
        cap = capacities.get(item_id, 0)
        already = _sum_overlapping_reserved(sb, item_id, r["start_at"], r["end_at"])
        need = int(r["quantity"])
        if need + already > cap:
            shortages.append({"item_id": item_id, "capacity": cap, "already": already, "request": need, "start_at": r["start_at"], "end_at": r["end_at"]})

    if shortages:
        lines = []
        for s in shortages:
            lines.append(
                f"- Item {s['item_id']} sin capacidad: cap={s['capacity']} reservado={s['already']} requerido={s['request']} ({s['start_at']} → {s['end_at']})"
            )
        raise ValueError("No hay capacidad suficiente para algunos ítems rentables:\n" + "\n".join(lines))


def _create_reservations(sb, reservations_needed):
    quote_id = reservations_needed[0]["quotation_id"]
    sb.table("reservations").delete().eq("quotation_id", quote_id).execute()

    payload = []
    for r in reservations_needed:
        payload.append(
            {
                "item_id": r["item_id"],
                "quotation_id": r["quotation_id"],
                "event_id": r["event_id"],
                "start_at": r["start_at"],
                "end_at": r["end_at"],
                "quantity": int(r["quantity"]),
                "status": RES_STATUS_FIRM,
            }
        )
    if payload:
        sb.table("reservations").insert(payload).execute()


def _accept_quote(sb, quote_id: str, user_id: str | None = None):
    sb.table("quotations").update({"status": "accepted", "accepted_at": _now_iso()}).eq("id", quote_id).execute()
    try:
        sb.table("quotation_status_history").insert(
            {"quotation_id": quote_id, "old_status": "draft", "new_status": "accepted", "changed_by": user_id, "note": "Aceptada y reservas generadas"}
        ).execute()
    except Exception:
        pass


def accept_quote(quote_id: str, user_id: str | None = None):
    sb = get_service_client()

    q, ev = _fetch_quote_core(sb, quote_id)
    lines, meta = _fetch_quote_lines_with_items(sb, quote_id)

    needs = _build_needed_reservations(sb, lines, meta, ev, quote_id)
    if not needs:
        raise ValueError("No hay líneas rentables (o válidas) para reservar.")

    _check_availability_or_raise(sb, needs)
    _create_reservations(sb, needs)
    _accept_quote(sb, quote_id, user_id=user_id)
    return True

def create_client_quick(form: Dict[str, Any]) -> dict:
    res = create_client(form)
    return res

def create_contact_quick(form: Dict[str, Any]) -> dict:
    ins = create_contact(form)
    return ins

def create_event_quick(payload: Dict[str, Any]) -> dict:
    s = Settings()
    payload = {
        "name": (payload.get("name") or "").strip(),
        "client_id": payload.get("client_id") or None,
        "contact_id": payload.get("contact_id") or None,
        "venue": (payload.get("venue") or "").strip(),
        "start_at": parse_datetime_local(payload.get("start_at") or "", s.tz_default),
        "end_at": parse_datetime_local(payload.get("end_at") or "", s.tz_default),
        "notes": (payload.get("notes") or "").strip(),
        "created_by": payload.get("created_by") or None,
        "build_start_at": parse_datetime_local(payload.get("build_start_at") or "", s.tz_default),
        "strike_end_at": parse_datetime_local(payload.get("strike_end_at") or "", s.tz_default)
    }
    ins = create_event(payload)
    return ins


def create_item_quick(payload: Dict[str, Any]) -> dict:
    ins = create_item(payload)
    return ins
