"""
routes.py – Rutas del módulo de importación de cotizaciones históricas.

  GET  /importar/          → formulario de carga de archivo
  POST /importar/preview   → parsea el archivo y muestra preview editable
  POST /importar/crear     → crea los registros y redirige a la cotización
"""
from __future__ import annotations

import io

from flask import flash, redirect, render_template, request, url_for

from blueprints.import_quotes import bp
from services.session_user import role_required

from .parser import parse_xlsx, parse_pdf
from .service import (
    create_import,
    get_clients_and_profiles,
    suggest_client_id,
    suggest_owner_id,
)


# ─────────────────────────────────────────────────────────────────────────────
# GET /importar/   – Formulario de subida
# ─────────────────────────────────────────────────────────────────────────────

@bp.get("/")
@role_required("admin", "sales")
def import_get():
    clients, profiles = get_clients_and_profiles()
    return render_template(
        "import_quotes/import.html",
        parsed=None,
        clients=clients,
        profiles=profiles,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /importar/preview  – Parsear y mostrar preview
# ─────────────────────────────────────────────────────────────────────────────

@bp.post("/preview")
@role_required("admin", "sales")
def import_preview():
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Selecciona un archivo Excel (.xlsx) o PDF antes de continuar.", "warning")
        return redirect(url_for("import_quotes.import_get"))

    fname = (f.filename or "").lower()
    file_bytes = io.BytesIO(f.read())

    try:
        if fname.endswith(".xlsx") or fname.endswith(".xls"):
            parsed = parse_xlsx(file_bytes)
        elif fname.endswith(".pdf"):
            parsed = parse_pdf(file_bytes)
        else:
            flash("Formato no soportado. Usa .xlsx o .pdf", "warning")
            return redirect(url_for("import_quotes.import_get"))

    except Exception as exc:
        flash(f"Error al leer el archivo: {exc}", "danger")
        return redirect(url_for("import_quotes.import_get"))

    if not parsed.get("items"):
        flash(
            "No se encontraron productos en el archivo. "
            "Verifica que sea una cotización de Avvisi Audio.",
            "warning",
        )
        return redirect(url_for("import_quotes.import_get"))

    # Mostrar errores de parseo si los hay (no bloqueantes)
    for err in parsed.get("errors") or []:
        flash(f"Advertencia al parsear: {err}", "warning")

    clients, profiles = get_clients_and_profiles()
    suggested_client  = suggest_client_id(clients, parsed.get("client_name") or "")
    suggested_owner   = suggest_owner_id(profiles, parsed.get("sales_rep") or "")

    return render_template(
        "import_quotes/import.html",
        parsed=parsed,
        clients=clients,
        profiles=profiles,
        suggested_client=suggested_client,
        suggested_owner=suggested_owner,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /importar/crear  – Crear registros en BD
# ─────────────────────────────────────────────────────────────────────────────

@bp.post("/crear")
@role_required("admin", "sales")
def import_create():
    try:
        quote_id, quote_no = create_import(request.form)
        flash(f"Cotización {quote_no} importada correctamente.", "success")
        return redirect(url_for("quotations.quotation_edit_get", quote_id=quote_id))

    except ValueError as exc:
        flash(str(exc), "warning")
    except Exception as exc:
        flash(f"Error al importar: {exc}", "danger")

    return redirect(url_for("import_quotes.import_get"))
