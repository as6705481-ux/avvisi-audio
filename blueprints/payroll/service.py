# blueprints/payroll/service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from extensions.supabase import get_service_client

# ==========================
# Constantes
# ==========================
VALID_PAYROLL_STATUSES = {"draft", "approved", "paid"}

# Transiciones permitidas de estado de una planilla.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft":    {"approved"},
    "approved": {"draft", "paid"},
    "paid":     {"approved"},
}

VALID_ENTRY_KINDS = {"base", "event", "bonus"}


# ==========================
# Helpers
# ==========================
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return default


def _profiles_map() -> dict[str, dict]:
    """Mapa id -> perfil (nombre, base_salary, activo)."""
    sb = get_service_client()
    rows = (
        sb.table("profiles")
        .select("id, full_name, role, active, base_salary")
        .order("full_name")
        .execute()
        .data
        or []
    )
    return {r["id"]: r for r in rows}


# ==========================
# Planillas (períodos)
# ==========================
def list_periods() -> list[dict]:
    """Lista de planillas con nº de empleados y total agregado."""
    sb = get_service_client()
    periods = (
        sb.table("payroll_periods")
        .select("id, title, period_start, period_end, status, created_at")
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )
    if not periods:
        return []

    entries = (
        sb.table("payroll_entries")
        .select("period_id, employee_id, amount")
        .execute()
        .data
        or []
    )

    totals: dict[str, float] = {}
    emps: dict[str, set] = {}
    for e in entries:
        pid = e.get("period_id")
        totals[pid] = totals.get(pid, 0.0) + _to_float(e.get("amount"))
        emps.setdefault(pid, set()).add(e.get("employee_id"))

    for p in periods:
        p["total"] = round(totals.get(p["id"], 0.0), 2)
        p["employee_count"] = len(emps.get(p["id"], set()))
    return periods


def create_period(form, created_by: str | None = None) -> str:
    sb = get_service_client()
    title = (form.get("title") or "").strip()
    if not title:
        raise ValueError("El título es obligatorio.")

    payload = {
        "title": title,
        "period_start": (form.get("period_start") or "").strip() or None,
        "period_end": (form.get("period_end") or "").strip() or None,
        "notes": (form.get("notes") or "").strip() or None,
        "status": "draft",
        "created_by": created_by or None,
    }
    row = sb.table("payroll_periods").insert(payload).execute().data
    return row[0]["id"]


def _get_period(period_id: str) -> dict:
    sb = get_service_client()
    p = (
        sb.table("payroll_periods")
        .select("*")
        .eq("id", period_id)
        .single()
        .execute()
        .data
    )
    if not p:
        raise ValueError("Planilla no encontrada.")
    return p


def get_period_context(period_id: str) -> dict:
    """Período + nóminas agrupadas por empleado, totales y datos para los formularios."""
    sb = get_service_client()
    period = _get_period(period_id)

    entries = (
        sb.table("payroll_entries")
        .select("id, employee_id, kind, description, event_id, amount, created_at")
        .eq("period_id", period_id)
        .order("created_at")
        .execute()
        .data
        or []
    )

    profiles = _profiles_map()
    events = (
        sb.table("events")
        .select("id, name")
        .order("start_at", desc=True)
        .limit(300)
        .execute()
        .data
        or []
    )
    event_names = {e["id"]: e.get("name") or "—" for e in events}

    # Agrupar por empleado
    by_emp: dict[str, dict] = {}
    for e in entries:
        eid = e["employee_id"]
        prof = profiles.get(eid, {})
        slip = by_emp.setdefault(
            eid,
            {
                "employee_id": eid,
                "employee_name": prof.get("full_name") or "(sin nombre)",
                "role": prof.get("role") or "",
                "lines": [],
                "subtotal": 0.0,
            },
        )
        e["amount"] = _to_float(e.get("amount"))
        e["event_name"] = event_names.get(e.get("event_id")) if e.get("event_id") else None
        slip["lines"].append(e)
        slip["subtotal"] += e["amount"]

    payslips = sorted(by_emp.values(), key=lambda s: s["employee_name"].lower())
    for s in payslips:
        s["subtotal"] = round(s["subtotal"], 2)

    grand_total = round(sum(s["subtotal"] for s in payslips), 2)

    # Empleados aún no incluidos en la planilla (solo activos)
    included = set(by_emp.keys())
    available_employees = [
        {"id": pid, "full_name": p.get("full_name") or "(sin nombre)",
         "base_salary": _to_float(p.get("base_salary"))}
        for pid, p in profiles.items()
        if pid not in included and p.get("active", True)
    ]
    available_employees.sort(key=lambda p: p["full_name"].lower())

    return {
        "period": period,
        "payslips": payslips,
        "grand_total": grand_total,
        "available_employees": available_employees,
        "events": events,
    }


def delete_period(period_id: str) -> bool:
    sb = get_service_client()
    # ON DELETE CASCADE elimina las líneas asociadas.
    sb.table("payroll_periods").delete().eq("id", period_id).execute()
    return True


def set_period_status(period_id: str, target: str) -> bool:
    sb = get_service_client()
    target = (target or "").strip().lower()
    if target not in VALID_PAYROLL_STATUSES:
        raise ValueError("Estado inválido.")

    p = _get_period(period_id)
    old = (p.get("status") or "draft").strip().lower()
    if target == old:
        return True
    if target not in ALLOWED_TRANSITIONS.get(old, set()):
        raise ValueError(f"No se puede pasar de {old} a {target}.")

    sb.table("payroll_periods").update(
        {"status": target, "updated_at": _now_iso()}
    ).eq("id", period_id).execute()
    return True


def _assert_editable(period_id: str) -> None:
    """No permitir editar líneas de una planilla ya pagada."""
    p = _get_period(period_id)
    if (p.get("status") or "").strip().lower() == "paid":
        raise ValueError("La planilla está pagada; no se puede modificar. Revierte el estado primero.")


# ==========================
# Líneas de planilla
# ==========================
def add_employee_to_period(period_id: str, employee_id: str) -> bool:
    """Agrega un empleado creando su línea 'base' con el sueldo base del perfil."""
    sb = get_service_client()
    _assert_editable(period_id)

    employee_id = (employee_id or "").strip()
    if not employee_id:
        raise ValueError("Empleado inválido.")

    prof = (
        sb.table("profiles")
        .select("id, full_name, base_salary")
        .eq("id", employee_id)
        .single()
        .execute()
        .data
    )
    if not prof:
        raise ValueError("Empleado no encontrado.")

    # Evitar duplicar la línea base si el empleado ya está en la planilla.
    existing = (
        sb.table("payroll_entries")
        .select("id")
        .eq("period_id", period_id)
        .eq("employee_id", employee_id)
        .limit(1)
        .execute()
        .data
    )
    if existing:
        raise ValueError("El empleado ya está en la planilla.")

    sb.table("payroll_entries").insert(
        {
            "period_id": period_id,
            "employee_id": employee_id,
            "kind": "base",
            "description": "Salario base",
            "amount": _to_float(prof.get("base_salary")),
        }
    ).execute()
    return True


def add_entry(period_id: str, form) -> bool:
    """Agrega una línea de tipo 'event' o 'bonus' a un empleado."""
    sb = get_service_client()
    _assert_editable(period_id)

    employee_id = (form.get("employee_id") or "").strip()
    kind = (form.get("kind") or "bonus").strip().lower()
    if not employee_id:
        raise ValueError("Empleado inválido.")
    if kind not in {"event", "bonus"}:
        raise ValueError("Tipo de línea inválido.")

    event_id = (form.get("event_id") or "").strip() or None
    if kind != "event":
        event_id = None

    sb.table("payroll_entries").insert(
        {
            "period_id": period_id,
            "employee_id": employee_id,
            "kind": kind,
            "description": (form.get("description") or "").strip() or None,
            "event_id": event_id,
            "amount": _to_float(form.get("amount")),
        }
    ).execute()
    return True


def _entry_period_id(entry_id: str) -> str:
    sb = get_service_client()
    row = (
        sb.table("payroll_entries")
        .select("period_id")
        .eq("id", entry_id)
        .single()
        .execute()
        .data
    )
    if not row:
        raise ValueError("Línea no encontrada.")
    return row["period_id"]


def update_entry(entry_id: str, form) -> str:
    """Actualiza descripción/monto (y evento) de una línea. Devuelve el period_id."""
    sb = get_service_client()
    period_id = _entry_period_id(entry_id)
    _assert_editable(period_id)

    updates: dict[str, Any] = {"amount": _to_float(form.get("amount"))}
    if "description" in form:
        updates["description"] = (form.get("description") or "").strip() or None
    if "event_id" in form:
        updates["event_id"] = (form.get("event_id") or "").strip() or None

    sb.table("payroll_entries").update(updates).eq("id", entry_id).execute()
    return period_id


def delete_entry(entry_id: str) -> str:
    """Elimina una línea. Devuelve el period_id para redirigir."""
    sb = get_service_client()
    period_id = _entry_period_id(entry_id)
    _assert_editable(period_id)
    sb.table("payroll_entries").delete().eq("id", entry_id).execute()
    return period_id


# ==========================
# Sueldo base (perfiles)
# ==========================
def update_base_salary(employee_id: str, amount: Any) -> bool:
    sb = get_service_client()
    sb.table("profiles").update(
        {"base_salary": _to_float(amount), "updated_at": _now_iso()}
    ).eq("id", employee_id).execute()
    return True
