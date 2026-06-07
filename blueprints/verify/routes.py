"""
blueprints/verify/routes.py
Página pública de verificación de autenticidad de cotizaciones.
No requiere login — accesible por cualquier persona con el enlace/QR.
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import render_template

from blueprints.verify import bp
from extensions.supabase import get_service_client
from utils.money import money_float, money_str


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%d/%m/%Y")
    except Exception:
        return str(iso)[:10]


@bp.get("/<quote_id>")
def verify_quote(quote_id: str):
    """
    Página pública de verificación.
    Muestra los datos reales de la cotización tal como están en la base de datos.
    Si el UUID no existe → pantalla de "no encontrada".
    """
    sb = get_service_client()

    try:
        q = (
            sb.table("quotations")
            .select(
                "id, quote_number, status, created_at, valid_until, "
                "subtotal, discount_total, tax_total, total, currency, "
                "owner_id, "
                "clients(id, name)"
            )
            .eq("id", quote_id)
            .single()
            .execute()
            .data
        )
    except Exception:
        q = None

    if not q:
        return render_template("verify/verify.html", found=False, quote_id=quote_id), 404

    # Líneas (sin datos sensibles)
    lines = (
        sb.table("quotation_items")
        .select("custom_name, quantity, days, unit_price, line_total, sort_order")
        .eq("quotation_id", quote_id)
        .order("sort_order")
        .execute()
        .data
    ) or []

    # Responsable (solo nombre)
    owner_name = "—"
    if q.get("owner_id"):
        try:
            p = (
                sb.table("profiles")
                .select("full_name")
                .eq("id", q["owner_id"])
                .single()
                .execute()
                .data
            )
            owner_name = (p or {}).get("full_name") or "—"
        except Exception:
            pass

    currency     = (q.get("currency") or "HNL").upper()
    subtotal_f   = money_float(q.get("subtotal"))
    tax_f        = money_float(q.get("tax_total"))
    discount_f   = money_float(q.get("discount_total"))
    total_f      = money_float(q.get("total"))

    # Estado semáforo
    status = (q.get("status") or "").lower()
    STATUS_ES = {
        "draft":     "Borrador",
        "sent":      "Enviada",
        "accepted":  "Aceptada",
        "declined":  "Rechazada",
        "expired":   "Expirada",
        "cancelled": "Cancelada",
        "converted": "Convertida",
        "void":      "Anulada",
    }
    is_valid   = status in {"sent", "accepted", "converted"}
    is_warning = status in {"draft", "expired"}
    is_invalid = status in {"declined", "cancelled", "void"}

    return render_template(
        "verify/verify.html",
        found       = True,
        q           = q,
        lines       = lines,
        owner_name  = owner_name,
        client_name = (q.get("clients") or {}).get("name") or "—",
        currency    = currency,
        subtotal    = money_str(subtotal_f),
        tax_total   = money_str(tax_f),
        discount    = money_str(discount_f),
        has_discount= discount_f > 0,
        total       = money_str(total_f),
        issued_date = _fmt_date(q.get("created_at")),
        valid_until = _fmt_date(q.get("valid_until")),
        status_label= STATUS_ES.get(status, status.capitalize()),
        is_valid    = is_valid,
        is_warning  = is_warning,
        is_invalid  = is_invalid,
        money_str   = money_str,
    )
