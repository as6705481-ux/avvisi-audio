# blueprints/quotations/routes.py
from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for, jsonify

from blueprints.quotations import bp
from services.flash_errors import flash_exception
from services.session_user import role_required

from .pdf import get_quote_print_context
from .service import (
    accept_quote,
    add_quote_line,
    create_quote_from_form,
    delete_quote_strict,
    get_quote_edit_context,
    list_quotations_with_names,
    set_quote_status_from_form,
    update_quote_header_from_form,
    update_quote_line_from_form,
    delete_quote_line,
    get_quote_add_context,
    create_event_from_quote,
    create_client_quick,
    create_contact_quick,
    create_event_quick,
    create_item_quick,
)


@bp.get("/")
@role_required("admin", "sales")
def quotations_list():
    rows, names = list_quotations_with_names(limit=500)
    return render_template("quotations/quotations.html", quotations=rows, names=names)


@bp.get("/add")
@role_required("admin", "sales")
def quotation_add_get():
    ctx = get_quote_add_context()
    return render_template("quotations/quotation_add.html", **ctx)


@bp.post("/add")
@role_required("admin", "sales")
def quotation_add_post():
    try:
        quote_id, quote_number = create_quote_from_form(request.form)
        flash(f"Cotización {quote_number} creada.", "success")
        return redirect(url_for("quotations.quotation_edit_get", quote_id=quote_id))
    except Exception as e:
        flash_exception("No se pudo crear", e)
        return redirect(url_for("quotations.quotation_add_get"))


@bp.get("/<quote_id>/edit")
@role_required("admin", "sales")
def quotation_edit_get(quote_id: str):
    ctx = get_quote_edit_context(quote_id)
    # ctx trae: quotation, lines, clients, contacts, events, owners, items
    return render_template("quotations/quotation_edit.html", **ctx)


@bp.post("/<quote_id>/edit")
@role_required("admin", "sales")
def quotation_edit_post(quote_id: str):
    """
    En el viejo aquí hacías:
    - action=add_line  => inserta línea y recomputa
    - else => update cabecera
    """
    try:
        action = (request.form.get("action") or "").strip().lower()
        is_admin = (session.get("user_role") or "") == "admin"

        if action == "add_line":
            add_quote_line(quote_id, request.form)
            flash("Línea agregada.", "success")
        else:
            update_quote_header_from_form(quote_id, request.form, allow_quote_number=is_admin)
            flash("Cabecera actualizada.", "success")

    except Exception as e:
        flash_exception("No se pudo actualizar", e)

    return redirect(url_for("quotations.quotation_edit_get", quote_id=quote_id))


@bp.post("/<quote_id>/lines/<line_id>/update")
@role_required("admin", "sales")
def quotation_line_update(quote_id: str, line_id: str):
    try:
        update_quote_line_from_form(quote_id, line_id, request.form)
        flash("Línea actualizada.", "success")
    except Exception as e:
        flash_exception("No se pudo actualizar la línea", e)
    return redirect(url_for("quotations.quotation_edit_get", quote_id=quote_id))


@bp.post("/<quote_id>/lines/<line_id>/delete")
@role_required("admin", "sales")
def quotation_line_delete(quote_id: str, line_id: str):
    try:
        delete_quote_line(quote_id, line_id)
        flash("Línea eliminada.", "success")
    except Exception as e:
        flash_exception("No se pudo eliminar la línea", e)
    return redirect(url_for("quotations.quotation_edit_get", quote_id=quote_id))


@bp.post("/<quote_id>/status")
@role_required("admin", "sales")
def quotation_set_status(quote_id: str):
    try:
        set_quote_status_from_form(quote_id, request.form)
        flash("Estado actualizado.", "success")
    except Exception as e:
        flash_exception("No se pudo cambiar estado", e)
    return redirect(url_for("quotations.quotation_edit_get", quote_id=quote_id))


@bp.post("/<quote_id>/accept")
@role_required("admin", "sales")
def quotation_accept(quote_id: str):
    try:
        accept_quote(quote_id, user_id=None)  # si tenés user_id real, pásalo
        flash("Cotización aceptada y reservas creadas (estado: firm).", "success")
    except Exception as e:
        flash_exception("Error al aceptar y reservar", e)
    return redirect(url_for("quotations.quotation_edit_get", quote_id=quote_id))


@bp.post("/<quote_id>/delete")
@role_required("admin", "sales")
def quotation_delete(quote_id: str):
    try:
        delete_quote_strict(quote_id)
        flash("Cotización eliminada.", "success")
    except Exception as e:
        flash_exception("No se pudo eliminar", e)
        return redirect(url_for("quotations.quotation_edit_get", quote_id=quote_id))
    return redirect(url_for("quotations.quotations_list"))


@bp.route("/<quote_id>/event/new", methods=["GET", "POST"])
@role_required("admin", "sales")
def quote_event_new(quote_id: str):
    """
    Copia del viejo /quotations/<id>/event/new
    """
    try:
        return create_event_from_quote(quote_id, request)
    except Exception as e:
        flash_exception("No se pudo crear/vincular evento", e)
        return redirect(url_for("quotations.quotation_edit_get", quote_id=quote_id))


@bp.get("/<quote_id>/print")
@role_required("admin", "sales")
def quotation_print(quote_id: str):
    ctx = get_quote_print_context(quote_id)
    verify_url = url_for("verify.verify_quote", quote_id=quote_id, _external=True)
    return render_template("quotations/quote_print.html", **ctx, verify_url=verify_url)


@bp.post("/api/clients")
@role_required("admin", "sales")
def api_client_create():
    try:
        row = create_client_quick(request.json or {})
        return jsonify({"ok": True, "client": row, "message": "Cliente creado.", "category": "success"}), 201
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "message": str(e), "category": "danger"}), 400


@bp.post("/api/contacts")
@role_required("admin", "sales")
def api_contact_create():
    try:
        row = create_contact_quick(request.json or {})
        return jsonify({"ok": True, "contact": row, "message": "Contacto creado.", "category": "success"}), 201
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "message": str(e), "category": "danger"}), 400


@bp.post("/api/events")
@role_required("admin", "sales")
def api_event_create():
    try:
        row = create_event_quick(request.json or {})
        return jsonify({"ok": True, "event": row, "message": "Evento creado.", "category": "success"}), 201
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "message": str(e), "category": "danger"}), 400


@bp.post("/api/items")
@role_required("admin", "sales")
def api_item_create():
    try:
        row = create_item_quick(request.json or {})
        return jsonify({"ok": True, "item": row, "message": "Producto creado.", "category": "success"}), 201
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "message": str(e), "category": "danger"}), 400
