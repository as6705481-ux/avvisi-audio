# blueprints/suppliers/routes.py
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

from blueprints.suppliers import bp
from services.flash_errors import flash_exception
from services.session_user import role_required

from .service import (
    create_supplier,
    delete_supplier,
    get_supplier,
    list_suppliers,
    update_supplier,
    set_supplier_status,  # <-- NUEVO
)


@bp.get("/")
@role_required("admin", "ops")
def suppliers_list():
    suppliers = list_suppliers()
    return render_template("suppliers/suppliers.html", suppliers=suppliers)


@bp.get("/add")
@role_required("admin", "ops")
def supplier_add_get():
    return render_template("suppliers/supplier_add.html")


@bp.post("/add")
@role_required("admin", "ops")
def supplier_add_post():
    try:
        create_supplier(request.form)
        flash("Proveedor agregado.", "success")
    except Exception as e:
        flash_exception("No se pudo agregar", e)
    return redirect(url_for("suppliers.suppliers_list"))


@bp.get("/<supplier_id>/edit")
@role_required("admin", "ops")
def supplier_edit_get(supplier_id: str):
    supplier = get_supplier(supplier_id)
    return render_template("suppliers/supplier_edit.html", supplier=supplier)


@bp.post("/<supplier_id>/edit")
@role_required("admin", "ops")
def supplier_edit_post(supplier_id: str):
    try:
        update_supplier(supplier_id, request.form)
        flash("Proveedor actualizado.", "success")
    except Exception as e:
        flash_exception("No se pudo actualizar", e)
    return redirect(url_for("suppliers.suppliers_list"))


@bp.post("/<supplier_id>/delete")
@role_required("admin", "ops")
def supplier_delete(supplier_id: str):
    try:
        delete_supplier(supplier_id)
        flash("Proveedor eliminado.", "success")
    except Exception as e:
        flash_exception("No se pudo eliminar", e)
    return redirect(url_for("suppliers.suppliers_list"))


@bp.post("/<supplier_id>/status")
@role_required("admin", "ops")
def supplier_set_status(supplier_id: str):
    """
    POST /suppliers/<id>/status?action=activate|deactivate
    """
    action = (request.args.get("action") or "").lower()
    if action not in {"activate", "deactivate"}:
        flash("Acción inválida. Use action=activate o action=deactivate.", "error")
        return redirect(url_for("suppliers.suppliers_list"))

    new_val = True if action == "activate" else False

    try:
        set_supplier_status(supplier_id, new_val)
        flash(f"Proveedor {'activado' if new_val else 'desactivado'}.", "success")
    except Exception as e:
        flash_exception("No se pudo actualizar estado", e)

    return redirect(url_for("suppliers.suppliers_list"))
