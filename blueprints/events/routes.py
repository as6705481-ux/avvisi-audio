from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

from blueprints.events import bp
from config import Settings
from services.flash_errors import flash_exception
from services.session_user import login_required
from utils.dates import fmt_datetime_local, parse_datetime_local

from .service import (
    create_event,
    delete_event,
    get_event,
    get_quote_for_event,
    list_clients_for_events,
    list_events,
    list_profiles,
    list_contacts,
    update_event,
)


def _event_payload_from_form(form: dict) -> dict:
    s = Settings()
    return {
        "name": (form.get("name") or "").strip(),
        "client_id": form.get("client_id") or None,
        "contact_id": form.get("contact_id") or None,
        "venue": (form.get("venue") or "").strip(),
        "start_at": parse_datetime_local(form.get("start_at") or "", s.tz_default),
        "end_at": parse_datetime_local(form.get("end_at") or "", s.tz_default),
        "notes": (form.get("notes") or "").strip(),
        "created_by": form.get("created_by") or None,
        "build_start_at": parse_datetime_local(form.get("build_start_at") or "", s.tz_default),
        "strike_end_at": parse_datetime_local(form.get("strike_end_at") or "", s.tz_default)
    }


@bp.get("/")
@login_required
def events_list():
    events = list_events()
    print(events)
    return render_template("events/events_list.html", events=events)


@bp.get("/add")
@login_required
def event_add_get():
    clients = list_clients_for_events()
    profiles = list_profiles()
    contacts = list_contacts()

    return render_template("events/event_add.html", clients=clients, owners=profiles, contacts=contacts)


@bp.post("/add")
@login_required
def event_add_post():
    try:
        payload = _event_payload_from_form(request.form)
        create_event(payload)
        flash("Evento agregado.", "success")
    except Exception as e:
        flash_exception("No se pudo agregar", e)
    return redirect(url_for("events.events_list"))


@bp.get("/<event_id>/edit")
@login_required
def event_edit_get(event_id: str):
    s = Settings()
    ev       = get_event(event_id)
    clients  = list_clients_for_events()
    contacts = list_contacts()
    profiles = list_profiles()
    # para datetime-local
    print(ev)
    # ev = ev or {}
    ev["start_at_local"] = fmt_datetime_local(ev.get("start_at"), s.tz_default)
    ev["end_at_local"] = fmt_datetime_local(ev.get("end_at"), s.tz_default)
    ev["build_local"] = fmt_datetime_local(ev.get("build_start_at"), s.tz_default)
    ev["strike_local"] = fmt_datetime_local(ev.get("strike_end_at"), s.tz_default)
    return render_template("events/event_edit.html", event=ev, clients=clients, contacts=contacts, profiles=profiles)


@bp.post("/<event_id>/edit")
@login_required
def event_edit_post(event_id: str):
    try:
        payload = _event_payload_from_form(request.form)
        update_event(event_id, payload)
        flash("Evento actualizado.", "success")
    except Exception as e:
        flash_exception("No se pudo actualizar", e)
    return redirect(url_for("events.events_list"))


@bp.post("/<event_id>/delete")
@login_required
def event_delete(event_id: str):
    try:
        delete_event(event_id)
        flash("Evento eliminado.", "success")
    except Exception as e:
        flash_exception("No se pudo eliminar", e)
    return redirect(url_for("events.events_list"))


@bp.get("/from-quote/<quote_id>")
@login_required
def event_from_quote(quote_id: str):
    """Crea evento prellenado desde una cotizacion."""
    s = Settings()
    quote = get_quote_for_event(quote_id) or {}
    clients = list_clients_for_events()

    # valores sugeridos
    event = {
        "client_id": quote.get("client_id"),
        "title": quote.get("title") or f"Evento - {quote.get('quote_number') or ''}",
        "location": quote.get("location") or "",
        "notes": quote.get("notes") or "",
        "start_at_local": fmt_datetime_local(quote.get("start_at"), s.tz_default),
        "end_at_local": fmt_datetime_local(quote.get("end_at"), s.tz_default),
        "quote_id": quote.get("id"),
    }

    return render_template(
        "events/event_from_quote.html",
        event=event,
        quote=quote,
        clients=clients,
    )
