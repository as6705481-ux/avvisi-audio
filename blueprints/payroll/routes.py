from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for

from blueprints.payroll import bp
from services.flash_errors import flash_exception
from services.session_user import role_required

from .service import (
    add_employee_to_period,
    add_entry,
    create_period,
    delete_entry,
    delete_period,
    get_period_context,
    list_periods,
    set_period_status,
    update_entry,
)


@bp.get("/")
@role_required("admin")
def payroll_list():
    periods = list_periods()
    return render_template("payroll/payroll_list.html", periods=periods)


@bp.get("/new")
@role_required("admin")
def payroll_new_get():
    return render_template("payroll/payroll_new.html")


@bp.post("/new")
@role_required("admin")
def payroll_new_post():
    try:
        period_id = create_period(request.form, created_by=session.get("user_id"))
        flash("Planilla creada.", "success")
        return redirect(url_for("payroll.payroll_detail", period_id=period_id))
    except Exception as e:
        flash_exception("No se pudo crear la planilla", e)
        return redirect(url_for("payroll.payroll_new_get"))


@bp.get("/<period_id>")
@role_required("admin")
def payroll_detail(period_id: str):
    try:
        ctx = get_period_context(period_id)
    except Exception as e:
        flash_exception("No se pudo abrir la planilla", e)
        return redirect(url_for("payroll.payroll_list"))
    return render_template("payroll/payroll_detail.html", **ctx)


@bp.post("/<period_id>/employees")
@role_required("admin")
def payroll_add_employee(period_id: str):
    try:
        add_employee_to_period(period_id, request.form.get("employee_id"))
        flash("Empleado agregado a la planilla.", "success")
    except Exception as e:
        flash_exception("No se pudo agregar el empleado", e)
    return redirect(url_for("payroll.payroll_detail", period_id=period_id))


@bp.post("/<period_id>/entries")
@role_required("admin")
def payroll_add_entry(period_id: str):
    try:
        add_entry(period_id, request.form)
        flash("Línea agregada.", "success")
    except Exception as e:
        flash_exception("No se pudo agregar la línea", e)
    return redirect(url_for("payroll.payroll_detail", period_id=period_id))


@bp.post("/entries/<entry_id>/update")
@role_required("admin")
def payroll_entry_update(entry_id: str):
    try:
        period_id = update_entry(entry_id, request.form)
        flash("Línea actualizada.", "success")
        return redirect(url_for("payroll.payroll_detail", period_id=period_id))
    except Exception as e:
        flash_exception("No se pudo actualizar la línea", e)
        return redirect(url_for("payroll.payroll_list"))


@bp.post("/entries/<entry_id>/delete")
@role_required("admin")
def payroll_entry_delete(entry_id: str):
    try:
        period_id = delete_entry(entry_id)
        flash("Línea eliminada.", "success")
        return redirect(url_for("payroll.payroll_detail", period_id=period_id))
    except Exception as e:
        flash_exception("No se pudo eliminar la línea", e)
        return redirect(url_for("payroll.payroll_list"))


@bp.post("/<period_id>/status")
@role_required("admin")
def payroll_set_status(period_id: str):
    try:
        set_period_status(period_id, request.form.get("status"))
        flash("Estado actualizado.", "success")
    except Exception as e:
        flash_exception("No se pudo cambiar el estado", e)
    return redirect(url_for("payroll.payroll_detail", period_id=period_id))


@bp.post("/<period_id>/delete")
@role_required("admin")
def payroll_delete(period_id: str):
    try:
        delete_period(period_id)
        flash("Planilla eliminada.", "success")
    except Exception as e:
        flash_exception("No se pudo eliminar la planilla", e)
        return redirect(url_for("payroll.payroll_detail", period_id=period_id))
    return redirect(url_for("payroll.payroll_list"))
