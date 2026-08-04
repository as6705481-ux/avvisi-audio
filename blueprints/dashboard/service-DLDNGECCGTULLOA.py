from __future__ import annotations

import calendar
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytz

from extensions.supabase import get_service_client

_LOCAL_TZ = pytz.timezone(os.getenv("TZ_DEFAULT", "America/Tegucigalpa"))


# ── Utilidades de fecha ──────────────────────────────────────────────────────
def _parse_dt(s: str | None) -> datetime | None:
    """Parsea cualquier ISO 8601 a datetime UTC-aware. Tolera naive timestamps."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _is_in_progress(event: dict, now: datetime) -> bool:
    start = _parse_dt(event.get("start_at"))
    end   = _parse_dt(event.get("end_at"))
    if not start:
        return False
    if start > now:
        return False            # aún no ha comenzado
    if end is None:
        return True             # sin fecha fin → en curso si ya empezó
    return end >= now


def _is_upcoming(event: dict, now: datetime) -> bool:
    start = _parse_dt(event.get("start_at"))
    if not start:
        return False
    return start > now


def _is_past(event: dict, now: datetime) -> bool:
    start = _parse_dt(event.get("start_at"))
    end   = _parse_dt(event.get("end_at"))
    if not start or start > now:
        return False
    if end is None:
        return False  # sin fecha fin → se trata como en curso
    return end < now


def build_dashboard_payload(user_id: str) -> dict:
    sb  = get_service_client()
    now = datetime.now(timezone.utc)
    # Ventana operacional: 30 días atrás (captura eventos multi-día en curso)
    thirty_days_ago   = (now - timedelta(days=30)).isoformat()
    # Ventana calendario: 90 días atrás para mostrar historial en el calendario
    ninety_days_ago   = (now - timedelta(days=90)).isoformat()
    twelve_months_ago_dt = now.replace(day=1)
    for _ in range(12):
        twelve_months_ago_dt = (twelve_months_ago_dt - timedelta(days=1)).replace(day=1)
    twelve_months_ago = twelve_months_ago_dt.isoformat()

    months_labels: list[str] = []
    pivot = now.replace(day=1).date()
    for _ in range(12):
        months_labels.insert(0, f"{calendar.month_abbr[pivot.month]} {pivot.year}")
        pivot = (pivot - timedelta(days=1)).replace(day=1)

    # ── Queries paralelas ────────────────────────────────────────────────────
    def _profile():
        try:
            d = sb.table("profiles").select("full_name").eq("id", user_id).single().execute().data or {}
            return d.get("full_name") or "Usuario"
        except Exception:
            return "Usuario"

    def _quotations_recent():
        """Últimos 12 meses para ingresos."""
        try:
            return sb.table("quotations") \
                .select("id,client_id,status,total,created_at") \
                .gte("created_at", twelve_months_ago) \
                .execute().data or []
        except Exception:
            return []

    def _all_quotations_ext():
        """Últimos 12 meses: KPIs + staff + income breakdown. Límite 1 500 filas."""
        try:
            return sb.table("quotations") \
                .select("id,quote_number,client_id,status,owner_id,total,created_at") \
                .gte("created_at", twelve_months_ago) \
                .order("created_at", desc=True) \
                .limit(1500) \
                .execute().data or []
        except Exception:
            return []

    def _top_items():
        try:
            return sb.table("quotation_items") \
                .select("custom_name,quantity") \
                .gte("created_at", twelve_months_ago) \
                .limit(3000).execute().data or []
        except Exception:
            return []

    def _total_clients():
        try:
            return sb.table("clients").select("id", count="exact").execute().count or 0
        except Exception:
            return 0

    def _clients_names():
        try:
            return sb.table("clients").select("id,name").limit(2000).execute().data or []
        except Exception:
            return []

    def _all_profiles_active():
        """Todos los perfiles del equipo (sin filtrar por active para no excluir NULL)."""
        try:
            return sb.table("profiles") \
                .select("id,full_name,role,active") \
                .order("full_name") \
                .execute().data or []
        except Exception:
            return []

    def _events_operational():
        """Eventos en ventana de 90 días atrás — captura historial + en curso + futuros.
        NOTA: la tabla events NO tiene campo 'status'; se omite.
        """
        try:
            return sb.table("events") \
                .select("id,name,venue,start_at,end_at,created_by,client_id") \
                .gte("start_at", ninety_days_ago) \
                .order("start_at") \
                .limit(500).execute().data or []
        except Exception as exc:
            print(f"[dashboard] _events_operational error: {exc}")
            return []

    def _pipeline_quotations():
        try:
            return sb.table("quotations") \
                .select("id,quote_number,client_id,status,total,valid_until") \
                .in_("status", ["draft", "sent", "accepted", "converted"]) \
                .order("created_at", desc=True) \
                .limit(100).execute().data or []
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=9) as ex:
        f_profile     = ex.submit(_profile)
        f_quotes_rec  = ex.submit(_quotations_recent)
        f_quotes_ext  = ex.submit(_all_quotations_ext)
        f_items       = ex.submit(_top_items)
        f_clients_cnt = ex.submit(_total_clients)
        f_clients_nm  = ex.submit(_clients_names)
        f_profiles    = ex.submit(_all_profiles_active)
        f_events_op   = ex.submit(_events_operational)
        f_pipeline    = ex.submit(_pipeline_quotations)

    full_name      = f_profile.result()
    quotes_recent  = f_quotes_rec.result()
    all_quotes_ext = f_quotes_ext.result()
    items_rows     = f_items.result()
    total_clients  = f_clients_cnt.result()
    clients_names  = f_clients_nm.result()
    all_profiles   = f_profiles.result()
    events_op      = f_events_op.result()
    pipeline_rows  = f_pipeline.result()

    client_name_map  = {c["id"]: c["name"] for c in clients_names}
    profile_name_map = {p["id"]: p.get("full_name") or "—" for p in all_profiles}

    # ── Clasificar eventos (datetime-aware, tolerante a formatos) ─────────────
    in_progress_raw = [e for e in events_op if _is_in_progress(e, now)]
    upcoming_raw    = [e for e in events_op if _is_upcoming(e, now)]
    past_raw        = [e for e in events_op if _is_past(e, now)]

    def _fmt_local(iso_str: str | None) -> str:
        """Convierte ISO UTC a hora local para mostrar en la interfaz."""
        if not iso_str:
            return ""
        dt = _parse_dt(iso_str)
        if not dt:
            return str(iso_str)[:16].replace("T", " ")
        return dt.astimezone(_LOCAL_TZ).strftime("%d/%m/%Y %H:%M")

    def _fmt_event(e, include_owner=True) -> dict:
        owner_id = e.get("created_by")
        return {
            "id":    e.get("id"),
            "name":  e.get("name") or "—",
            "venue": e.get("venue") or "—",
            "start": _fmt_local(e.get("start_at")),
            "end":   _fmt_local(e.get("end_at")),
            "client": client_name_map.get(e.get("client_id"), "—"),
            "owner":  profile_name_map.get(owner_id, "—") if include_owner else None,
        }

    events_in_progress = [_fmt_event(e) for e in in_progress_raw]
    events_upcoming    = [_fmt_event(e) for e in upcoming_raw]
    events_past        = [_fmt_event(e) for e in past_raw]

    # ── KPIs ─────────────────────────────────────────────────────────────────
    REVENUE_STATUSES = {"accepted", "converted"}
    total_revenue   = sum(float(r.get("total") or 0) for r in quotes_recent
                          if r.get("status") in REVENUE_STATUSES)
    accepted_count  = sum(1 for r in all_quotes_ext if r.get("status") in REVENUE_STATUSES)
    total_count     = len(all_quotes_ext)
    conversion_rate = round(accepted_count / total_count * 100, 1) if total_count else 0.0
    avg_quote_value = round(
        sum(float(r.get("total") or 0) for r in all_quotes_ext) / total_count, 2
    ) if total_count else 0.0

    # ── Tarjetas de equipo ────────────────────────────────────────────────────
    ROLE_ES = {"admin": "Administrador", "sales": "Ventas", "ops": "Operaciones",
               "finance": "Finanzas", "developer": "Desarrollador"}
    team_cards = []
    for profile in all_profiles:
        # Los desarrolladores del sistema están fuera del equipo operativo.
        if (profile.get("role") or "") == "developer":
            continue
        pid = profile["id"]

        p_in_prog = [e for e in in_progress_raw if e.get("created_by") == pid]
        p_upcoming = [e for e in upcoming_raw   if e.get("created_by") == pid][:4]

        p_quotes  = [q for q in all_quotes_ext if q.get("owner_id") == pid]
        total_q   = len(p_quotes)
        closed_q  = sum(1 for q in p_quotes if q.get("status") in ("accepted", "converted"))
        revenue_p = sum(float(q.get("total") or 0) for q in p_quotes if q.get("status") in ("accepted", "converted"))
        conv      = round(closed_q / total_q * 100, 1) if total_q else 0.0

        if p_in_prog:
            card_status = "in_progress"
        elif p_upcoming:
            card_status = "upcoming"
        else:
            card_status = "available"

        team_cards.append({
            "name":     profile.get("full_name") or "Sin nombre",
            "role":     ROLE_ES.get(profile.get("role") or "", profile.get("role") or "—"),
            "role_raw": profile.get("role") or "",
            "status":   card_status,
            "in_progress": [_fmt_event(e, include_owner=False) for e in p_in_prog],
            "upcoming":    [_fmt_event(e, include_owner=False) for e in p_upcoming],
            "total_quotes":  total_q,
            "closed_quotes": closed_q,
            "conversion":    conv,
            "revenue":       round(revenue_p, 2),
        })

    # ordenar: en ejecución primero, luego con eventos próximos, luego disponibles
    _order = {"in_progress": 0, "upcoming": 1, "available": 2}
    team_cards.sort(key=lambda x: _order[x["status"]])

    # ── Estado cotizaciones (donut) ───────────────────────────────────────────
    STATUS_ES = {
        "draft": "Borrador", "sent": "Enviada", "accepted": "Aceptada",
        "declined": "Rechazada", "expired": "Expirada",
        "cancelled": "Cancelada", "converted": "Convertida",
        "void": "Anulada",
    }
    status_counts: dict[str, int] = defaultdict(int)
    for r in all_quotes_ext:
        status_counts[r.get("status") or "unknown"] += 1

    status_labels = [STATUS_ES.get(k, k) for k in status_counts]
    status_values = [status_counts[k] for k in status_counts]

    # ── Desglose de cotizaciones por estado (chips del panel) ────────────────
    _STATUS_HEX = {
        "draft":     "#6b7280",
        "sent":      "#0d6efd",
        "accepted":  "#198754",
        "converted": "#0891b2",
        "declined":  "#dc3545",
        "expired":   "#f59e0b",
        "cancelled": "#212529",
        "void":      "#b91c1c",
    }
    _STATUS_ORDER = ["draft", "sent", "accepted", "converted", "declined", "expired", "void", "cancelled"]
    status_breakdown: list[dict] = []
    _bd_seen: set[str] = set()
    for _s in _STATUS_ORDER:
        _c = status_counts.get(_s, 0)
        if _c:
            status_breakdown.append({"label": STATUS_ES.get(_s, _s), "count": _c, "color": _STATUS_HEX.get(_s, "#6b7280")})
            _bd_seen.add(_s)
    for _s, _c in status_counts.items():
        if _s not in _bd_seen and _c:
            status_breakdown.append({"label": STATUS_ES.get(_s, _s), "count": _c, "color": "#6b7280"})

    # ── Ingresos por mes ─────────────────────────────────────────────────────
    confirmed_by_ym: dict[str, float] = defaultdict(float)   # aceptadas/convertidas
    quoted_by_ym:    dict[str, float] = defaultdict(float)    # todas
    quotes_by_ym:    dict[str, int]   = defaultdict(int)
    for row in quotes_recent:
        if not row.get("created_at"):
            continue
        dt    = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
        key   = f"{dt.year:04d}-{dt.month:02d}"
        total = float(row.get("total") or 0.0)
        quoted_by_ym[key] += total
        quotes_by_ym[key] += 1
        if row.get("status") in REVENUE_STATUSES:
            confirmed_by_ym[key] += total

    def _ym(lbl: str) -> str:
        abbr, yr = lbl.split()
        m = list(calendar.month_abbr).index(abbr)
        return f"{int(yr):04d}-{m:02d}"

    incomes              = [round(confirmed_by_ym.get(_ym(l), 0.0), 2) for l in months_labels]
    total_quoted_month   = [round(quoted_by_ym.get(_ym(l), 0.0), 2)    for l in months_labels]
    quote_counts_per_month = [quotes_by_ym.get(_ym(l), 0) for l in months_labels]

    # ── KPIs adicionales de ingresos ──────────────────────────────────────────
    this_year_str       = f"{now.year:04d}-"
    ytd_revenue         = round(sum(v for k, v in confirmed_by_ym.items() if k.startswith(this_year_str)), 2)
    ytd_quotes          = sum(v for k, v in quotes_by_ym.items() if k.startswith(this_year_str))
    nonzero_incomes     = [v for v in incomes if v > 0]
    avg_monthly_revenue = round(sum(nonzero_incomes) / len(nonzero_incomes), 2) if nonzero_incomes else 0.0
    if confirmed_by_ym:
        best_key           = max(confirmed_by_ym, key=confirmed_by_ym.__getitem__)
        best_month_revenue = round(confirmed_by_ym[best_key], 2)
        _by, _bm           = map(int, best_key.split("-"))
        best_month_label   = f"{calendar.month_abbr[_bm]} {_by}"
    else:
        best_month_revenue = 0.0
        best_month_label   = "—"
    mom_pct = 0.0
    if len(incomes) >= 2 and incomes[-2] > 0:
        mom_pct = round((incomes[-1] - incomes[-2]) / incomes[-2] * 100, 1)

    # ── Top productos ─────────────────────────────────────────────────────────
    qty_by_name: dict[str, float] = defaultdict(float)
    for row in items_rows:
        qty_by_name[row.get("custom_name") or "Sin nombre"] += float(row.get("quantity") or 0.0)
    top_products       = sorted(qty_by_name.items(), key=lambda kv: kv[1], reverse=True)[:6]
    product_names      = [k for k, _ in top_products] or ["—"]
    product_quantities = [round(v, 2) for _, v in top_products] or [0]

    # Estados "muertos" que no representan negocio real y no deben sumar.
    DEAD_STATUSES = {"void", "cancelled"}

    # ── Top clientes por monto cotizado (12m, excluye anuladas/canceladas) ────
    rev_by_client: dict[str, float] = defaultdict(float)
    for row in all_quotes_ext:
        if row.get("status") in DEAD_STATUSES:
            continue
        rev_by_client[row.get("client_id") or ""] += float(row.get("total") or 0.0)
    top_cl         = sorted(rev_by_client.items(), key=lambda kv: kv[1], reverse=True)[:6]
    client_labels  = [client_name_map.get(c, (c[:8] if c else "Sin cliente")) for c, _ in top_cl] or ["—"]
    client_revenues= [round(v, 2) for _, v in top_cl] or [0]

    # ── Top vendedores por monto cotizado (12m, excluye anuladas/canceladas) ──
    rev_by_seller: dict[str, float] = defaultdict(float)
    for row in all_quotes_ext:
        if row.get("status") in DEAD_STATUSES:
            continue
        rev_by_seller[row.get("owner_id") or ""] += float(row.get("total") or 0.0)
    top_sellers     = sorted(rev_by_seller.items(), key=lambda kv: kv[1], reverse=True)[:6]
    seller_labels   = [(profile_name_map.get(s, "Sin asignar") if s else "Sin asignar") for s, _ in top_sellers] or ["—"]
    seller_revenues = [round(v, 2) for _, v in top_sellers] or [0]

    # ── Pipeline ─────────────────────────────────────────────────────────────
    _TRANS = {
        "draft":    ["sent", "cancelled"],
        "sent":     ["accepted", "declined", "expired", "cancelled"],
        "accepted": ["converted", "cancelled"],
        "converted": [],
    }
    _TRANS_ES = {
        "sent": "Enviada", "cancelled": "Cancelada", "accepted": "Aceptada",
        "declined": "Rechazada", "expired": "Expirada", "converted": "Convertida",
    }
    pipeline_order = ["draft", "sent", "accepted", "converted"]
    pipeline_by_status: dict[str, list] = {s: [] for s in pipeline_order}
    for r in pipeline_rows:
        s = r.get("status") or "draft"
        if s in pipeline_by_status:
            pipeline_by_status[s].append({
                "id":           r.get("id"),
                "quote_number": r.get("quote_number") or "—",
                "client":       client_name_map.get(r.get("client_id"), "—"),
                "total":        float(r.get("total") or 0),
                "valid_until":  (r.get("valid_until") or "")[:10],
                "transitions":  [_TRANS_ES.get(t, t) for t in _TRANS.get(s, [])],
            })

    # ── Cotizaciones recientes ─────────────────────────────────────────────────
    recent_quotes = []
    for r in all_quotes_ext[:8]:
        recent_quotes.append({
            "id":           r.get("id"),
            "quote_number": r.get("quote_number") or "—",
            "client":       client_name_map.get(r.get("client_id"), "—"),
            "status":       r.get("status") or "—",
            "total":        float(r.get("total") or 0),
            "created_at":   (r.get("created_at") or "")[:10],
        })

    return {
        "user": {"id": user_id, "name": full_name},
        # KPIs
        "total_revenue":    round(total_revenue, 2),
        "total_quotes":     total_count,
        "accepted_count":   accepted_count,
        "conversion_rate":  conversion_rate,
        "total_clients":    total_clients,
        "upcoming_events":  len(upcoming_raw),
        "avg_quote_value":  avg_quote_value,
        # Tab Operaciones
        "events_in_progress": events_in_progress,
        "events_upcoming":    events_upcoming,
        "events_past":        events_past,
        # Tab Equipo
        "team_cards": team_cards,
        # Tab Cotizaciones
        "pipeline_by_status":  pipeline_by_status,
        "pipeline_order":      pipeline_order,
        "status_labels":       status_labels,
        "status_values":       status_values,
        "status_breakdown":    status_breakdown,
        "recent_quotes":       recent_quotes,
        # Tab Ingresos
        "months":                months_labels,
        "incomes":               incomes,
        "total_quoted_month":    total_quoted_month,
        "quote_counts_per_month":quote_counts_per_month,
        "product_names":         product_names,
        "product_quantities":    product_quantities,
        "client_labels":         client_labels,
        "client_revenues":       client_revenues,
        "seller_labels":         seller_labels,
        "seller_revenues":       seller_revenues,
        # KPIs de ingresos (nuevos)
        "current_year":          now.year,
        "ytd_revenue":           ytd_revenue,
        "ytd_quotes":            ytd_quotes,
        "avg_monthly_revenue":   avg_monthly_revenue,
        "best_month_label":      best_month_label,
        "best_month_revenue":    best_month_revenue,
        "mom_pct":               mom_pct,
    }
