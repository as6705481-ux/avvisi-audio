from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for

from blueprints.users import bp
from services.flash_errors import flash_exception
from services.session_user import role_required

from .service import (
    USER_ROLES,
    create_user,
    delete_user,
    get_user_email_from_auth,
    get_user_profile,
    list_users,
    set_user_active,
    update_user,
)


@bp.get("/")
@role_required("admin")
def users_list():
    users = list_users()
    return render_template("users/users.html", users=users)


@bp.get("/add")
@role_required("admin")
def user_add_get():
    return render_template("users/user_add.html", roles=sorted(USER_ROLES))


@bp.post("/add")
@role_required("admin")
def user_add_post():
    try:
        create_user(request.form)
        flash("Usuario creado.", "success")
        return redirect(url_for("users.users_list"))
    except Exception as e:
        # si querés mensajes como en el viejo, podés capturar ValueError y mostrarlo directo
        flash_exception("No se pudo crear el usuario", e)
        return redirect(url_for("users.user_add_get"))


@bp.get("/<user_id>/edit")
@role_required("admin")
def user_edit_get(user_id: str):
    profile = get_user_profile(user_id)
    if not profile:
        flash("Perfil no encontrado.", "error")
        return redirect(url_for("users.users_list"))

    email = get_user_email_from_auth(user_id)
    user = {**profile, "email": email}
    return render_template("users/user_edit.html", user=user, roles=sorted(USER_ROLES))


@bp.post("/<user_id>/edit")
@role_required("admin")
def user_edit_post(user_id: str):
    try:
        update_user(user_id, request.form)
        flash("Usuario actualizado.", "success")
    except Exception as e:
        flash_exception("No se pudo actualizar", e)
    return redirect(url_for("users.users_list", user_id=user_id))


@bp.post("/<user_id>/deactivate")
@role_required("admin")
def user_deactivate(user_id: str):
    try:
        set_user_active(user_id, False)
        flash("Usuario desactivado (perfil).", "success")
    except Exception as e:
        flash_exception("No se pudo desactivar", e)
    return redirect(url_for("users.users_list"))


@bp.post("/<user_id>/activate")
@role_required("admin")
def user_activate(user_id: str):
    try:
        set_user_active(user_id, True)
        flash("Usuario activado (perfil).", "success")
    except Exception as e:
        flash_exception("No se pudo activar", e)
    return redirect(url_for("users.users_list"))


@bp.post("/<user_id>/delete")
@role_required("admin")
def user_delete(user_id: str):
    try:
        delete_user(user_id)
        flash("Usuario eliminado.", "success")
    except Exception as e:
        flash_exception("No se pudo eliminar", e)
    return redirect(url_for("users.users_list"))
