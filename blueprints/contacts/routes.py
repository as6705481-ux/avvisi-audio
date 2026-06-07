# blueprints/contacts/routes.py
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

from blueprints.contacts import bp
from services.flash_errors import flash_exception
from services.session_user import role_required

from .service import (
    create_contact,
    delete_contact,
    get_contact,
    list_clients_for_contacts,
    list_contacts,
    update_contact,
    set_contact_primary,
)


@bp.get("/")
@role_required("admin", "sales")
def contacts_list():
    contacts = list_contacts()
    return render_template("contacts/contacts_list.html", contacts=contacts)


@bp.get("/add")
@role_required("admin", "sales")
def contact_add_get():
    clients = list_clients_for_contacts()
    return render_template("contacts/contact_add.html", clients=clients)


@bp.post("/add")
@role_required("admin", "sales")
def contact_add_post():
    try:
        create_contact(request.form)
        flash("Contacto agregado.", "success")
    except Exception as e:
        flash_exception("No se pudo agregar", e)
    return redirect(url_for("contacts.contacts_list"))


@bp.get("/<contact_id>/edit")
@role_required("admin", "sales")
def contact_edit_get(contact_id: str):
    contact = get_contact(contact_id)
    clients = list_clients_for_contacts()
    return render_template("contacts/contact_edit.html", contact=contact, clients=clients)


@bp.post("/<contact_id>/edit")
@role_required("admin", "sales")
def contact_edit_post(contact_id: str):
    try:
        update_contact(contact_id, request.form)
        flash("Contacto actualizado.", "success")
    except Exception as e:
        flash_exception("No se pudo actualizar", e)
    return redirect(url_for("contacts.contacts_list"))


@bp.post("/<contact_id>/delete")
@role_required("admin", "sales")
def contact_delete(contact_id: str):
    try:
        delete_contact(contact_id)
        flash("Contacto eliminado.", "success")
    except Exception as e:
        flash_exception("No se pudo eliminar", e)
    return redirect(url_for("contacts.contacts_list"))  # <-- FIX: quitar coma


@bp.post("/<contact_id>/primary")
@role_required("admin", "sales")
def contact_primary(contact_id: str):
    """
    POST /contacts/<id>/primary?action=set|unset
    - set   : lo marca como principal y desmarca otros del mismo cliente
    - unset : lo quita como principal (no marca otro automáticamente)
    """
    action = (request.args.get("action") or "set").lower()
    if action not in {"set", "unset"}:
        flash("Acción inválida. Use action=set o action=unset.", "error")
        return redirect(url_for("contacts.contacts_list"))

    is_primary = True if action == "set" else False

    try:
        set_contact_primary(contact_id, is_primary=is_primary)
        flash(
            "Contacto marcado como principal." if is_primary else "Contacto desmarcado como principal.",
            "success",
        )
    except Exception as e:
        flash_exception("No se pudo actualizar el contacto principal", e)

    return redirect(url_for("contacts.contacts_list"))
