# blueprints/quotations/pdf.py
# Obtiene todos los datos de una cotización para la vista de impresión.
from __future__ import annotations

from flask import abort

from extensions.supabase import get_service_client
from utils.dates import fmt_date_short
from utils.money import money_float, money_str


def _short(iso: str | None) -> str:
    s = fmt_date_short(iso)
    return s[:10] if s not in ("", "—") else "—"


def get_quote_print_context(quote_id: str) -> dict:
    """Devuelve el contexto completo para renderizar quote_print.html."""
    sb = get_service_client()

    q = (
        sb.table("quotations")
        .select(
            "id, quote_number, client_id, event_id, owner_id, "
            "currency, exchange_rate, status, "
            "subtotal, discount_total, deposit_due, tax_total, total, "
            "valid_until, created_at, notes_client, "
            "clients(id,name)"
        )
        .eq("id", quote_id)
        .single()
        .execute()
        .data
    )
    if not q:
        abort(404, "Cotización no encontrada")

    event: dict = {}
    if q.get("event_id"):
        event = (
            sb.table("events")
            .select("id,name,venue,start_at")
            .eq("id", q["event_id"])
            .single()
            .execute()
            .data
        ) or {}

    owner: dict = {}
    if q.get("owner_id"):
        owner = (
            sb.table("profiles")
            .select("id,full_name,phone")
            .eq("id", q["owner_id"])
            .single()
            .execute()
            .data
        ) or {}

    lines = (
        sb.table("quotation_items")
        .select(
            "id,custom_name,description,section,"
            "quantity,unit_price,line_subtotal,line_total,days"
        )
        .eq("quotation_id", quote_id)
        .order("sort_order")
        .execute()
        .data
    ) or []

    if not lines:
        abort(400, "La cotización no tiene líneas de detalle")

    currency     = (q.get("currency") or "HNL").strip().upper()[:3]
    subtotal     = money_float(q.get("subtotal"))
    discount_tot = money_float(q.get("discount_total"))
    tax_tot      = money_float(q.get("tax_total"))
    total        = money_float(q.get("total"))
    deposit      = money_float(q.get("deposit_due"))
    balance_due  = round(total - deposit, 2)

    return dict(
        q=q,
        lines=lines,
        event=event,
        owner=owner,
        client_name=(q.get("clients") or {}).get("name") or "—",
        currency=currency,
        subtotal=money_str(subtotal),
        discount_total=money_str(discount_tot),
        has_discount=discount_tot > 0,
        tax_total=money_str(tax_tot),
        total=money_str(total),
        deposit=money_str(deposit),
        has_deposit=deposit > 0,
        balance_due=money_str(balance_due),
        issued_date=_short(q.get("created_at")),
        valid_until=_short(q.get("valid_until")),
        event_date=_short(event.get("start_at")) if event else "—",
        money_str=money_str,
    )
