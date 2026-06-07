# blueprints/items/routes.py
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

from blueprints.items import bp
from services.flash_errors import flash_exception
from services.session_user import role_required

from .service import (
    create_item,
    delete_item,
    get_item,
    list_items,
    list_categories,
    list_suppliers,
    list_stocked_items,
    update_item,
    set_item_status, 
)


@bp.get("/")
@role_required("admin", "sales", "ops")
def items_list():
    products = list_items()
    return render_template("items/items.html", products=products)


@bp.get("/add")
@role_required("admin", "sales", "ops")
def items_add_get():
    suppliers  = list_suppliers()
    categories = list_categories()
    return render_template("items/product_add.html", suppliers=suppliers, categories=categories)


@bp.post("/add")
@role_required("admin", "sales", "ops")
def items_add_post():
    try:
        create_item(request.form)
        flash("Producto agregado.", "success")
    except Exception as e:
        flash_exception("No se pudo agregar", e)
    return redirect(url_for("items.items_list"))


@bp.get("/<item_id>/edit")
@role_required("admin", "sales", "ops")
def items_edit_get(item_id: str):
    product = get_item(item_id)

    if product.get("item_type") == "consumable":
        stocked_info = list_stocked_items(
            product.get("id")
        )
    else:   
        stocked_info = {"rentable_capacity": product.get("rentable_capacity")}
        
    suppliers  = list_suppliers()
    categories = list_categories()

    return render_template(
        "items/product_edit.html",
        product=product,
        suppliers=suppliers,
        categories=categories,
        stocked_info=stocked_info
    )


@bp.post("/<item_id>/edit")
@role_required("admin", "sales", "ops")
def items_edit_post(item_id: str):
    try:
        update_item(item_id, request.form)
        flash("Producto actualizado.", "success")
    except Exception as e:
        flash_exception("No se pudo actualizar", e)
    return redirect(url_for("items.items_list"))


@bp.post("/<item_id>/delete")
@role_required("admin", "sales", "ops")
def items_delete(item_id: str):
    try:
        delete_item(item_id)
        flash("Producto eliminado.", "success")
    except Exception as e:
        flash_exception("No se pudo eliminar", e)
    return redirect(url_for("items.items_list"))  # <-- QUITAR la coma


@bp.post("/<item_id>/status")
@role_required("admin", "sales", "ops")
def items_set_status(item_id: str):
    """
    Similar al código viejo:
    POST /items/<id>/status?action=activate|deactivate
    """
    action = (request.args.get("action") or "").lower()
    if action not in {"activate", "deactivate"}:
        flash("Acción inválida. Use action=activate o action=deactivate.", "error")
        return redirect(url_for("items.items_list"))

    new_val = True if action == "activate" else False

    try:
        set_item_status(item_id, new_val)
        flash(f"Producto {'activado' if new_val else 'desactivado'}.", "success")
    except Exception as e:
        flash_exception("No se pudo actualizar estado", e)

    return redirect(url_for("items.items_list"))
