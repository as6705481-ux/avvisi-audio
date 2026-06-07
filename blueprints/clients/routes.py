# blueprints/clients/routes.py
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

from blueprints.clients import bp
from services.flash_errors import flash_exception
from services.session_user import role_required

from .service import create_client, delete_client, get_client, list_clients, update_client


@bp.get("/")
@role_required("admin", "sales")
def clients():
    clients = list_clients()
    return render_template("clients/clients.html", clients=clients)


@bp.get("/add")
@role_required("admin", "sales")
def client_add_get():
    return render_template("clients/client_add.html")


@bp.post("/add")
@role_required("admin", "sales")
def client_add_post():
    try:
        create_client(request.form)
        flash("Cliente agregado.", "success")
    except Exception as e:
        flash_exception("No se pudo agregar", e)
    return redirect(url_for("clients.clients"))


@bp.get("/<client_id>/edit")
@role_required("admin", "sales")
def client_edit_get(client_id: str):
    client = get_client(client_id)
    return render_template("clients/client_edit.html", client=client)


@bp.post("/<client_id>/edit")
@role_required("admin", "sales")
def client_edit_post(client_id: str):
    try:
        update_client(client_id, request.form)
        flash("Cliente actualizado.", "success")
    except Exception as e:
        flash_exception("No se pudo actualizar", e)
    return redirect(url_for("clients.clients"))


@bp.post("/<client_id>/delete")
@role_required("admin", "sales")
def client_delete(client_id: str):
    try:
        delete_client(client_id)
        flash("Cliente eliminado.", "success")
    except Exception as e:
        flash_exception("No se pudo eliminar", e)
    return redirect(url_for("clients.clients"))
