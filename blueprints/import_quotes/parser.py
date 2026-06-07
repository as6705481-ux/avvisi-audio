"""
parser.py – Parsea cotizaciones históricas de Avvisi Audio en formato .xlsx o .pdf.

Formato Excel confirmado (estructura consistente en todos los archivos 2025/):
  Fila 1 (idx 0) : "Cotizacion N°" en col H (idx 7)
  Fila 2 (idx 1) : Número de cotización en col H
  Fila 3 (idx 2) : "Cliente" col B, nombre cliente col D, "Ejecutivo de Venta" col F, rep col G
  Fila 4 (idx 3) : "Lugar del Evento" col B, venue col D
  Fila 5 (idx 4) : Encabezados de fecha ("Fecha Emitida", "Duración", "Fecha Evento", ...)
  Fila 6 (idx 5) : Valores: fecha_emision col B, duración col C, fecha_evento col D, tipo col F, guests col H
  Fila 7 (idx 6) : Encabezados items (Cantidad, Dias, Descripción, Unidad, Total)
  Filas 8+ (idx 7+): Líneas de productos
  Últimas 3 filas: SubTotal, ISV, Total

Formato PDF: pdfplumber extrae tablas con la misma estructura de columnas.
"""
from __future__ import annotations

import re
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# Helpers compartidos
# ─────────────────────────────────────────────────────────────────────────────

def _parse_price(raw) -> float:
    """Convierte 'L 3 5,000.00', 35000, 'L35,000.00', etc. → float.

    El PDF a veces parte números grandes con un espacio interno ("L 3 5,000.00"
    en lugar de "L 35,000.00"). Se elimina la L, se colapsan espacios y comas.
    """
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw)
    # Quitar símbolo de Lempira, comas, luego todos los espacios internos
    s = s.replace("L", "").replace(",", "").strip()
    s = re.sub(r"\s+", "", s)
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_days(raw) -> int:
    """Extrae número de días de valores como '3', '3 dias', 1.0, etc."""
    if raw is None:
        return 1
    if isinstance(raw, (int, float)):
        return max(int(raw), 1)
    m = re.search(r"\d+", str(raw))
    return int(m.group()) if m else 1


def _parse_date_cell(raw) -> str | None:
    """Devuelve string ISO yyyy-mm-dd o None si no es parseable."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.strftime("%Y-%m-%d")
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _is_iso_date(s) -> bool:
    """Verifica si un string tiene formato yyyy-mm-dd."""
    if not s or not isinstance(s, str):
        return False
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", s.strip()))


# ─────────────────────────────────────────────────────────────────────────────
# EXCEL (.xlsx)
# ─────────────────────────────────────────────────────────────────────────────

def parse_xlsx(file_obj) -> dict:
    """Parsea un archivo Excel de cotización de Avvisi Audio.

    Args:
        file_obj: File-like object (BytesIO o ruta).

    Returns:
        dict con todos los campos extraídos + lista 'items'.
    """
    import openpyxl

    wb = openpyxl.load_workbook(file_obj, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    result: dict = {
        "quote_number": None,
        "client_name":  None,
        "sales_rep":    None,
        "venue":        None,
        "event_date":   None,   # ISO yyyy-mm-dd o string raw
        "event_type":   None,
        "guests":       None,
        "date_issued":  None,
        "duration":     None,
        "items":        [],
        "subtotal":     0.0,
        "tax":          0.0,
        "total":        0.0,
        "has_tax":      False,
        "errors":       [],
    }

    items_start_idx: int | None = None
    totals_idx:      int | None = None

    for i, row in enumerate(rows):
        def _cell(j, r=row):
            return r[j] if j < len(r) else None

        row_text = " ".join(str(c or "").strip().lower() for c in row)

        # ── Número de cotización ────────────────────────────────────────────
        if ("cotizacion" in row_text or "cotización" in row_text) and not result["quote_number"]:
            for j, c in enumerate(row):
                if c and ("cotizacion" in str(c).lower() or "cotización" in str(c).lower()):
                    # Número en la siguiente fila, misma columna (verificar bounds)
                    if i + 1 < len(rows):
                        next_row = rows[i + 1]
                        next_val = next_row[j] if j < len(next_row) else None
                        if next_val and str(next_val).strip():
                            result["quote_number"] = str(next_val).strip()
                    # O en la misma fila, celdas siguientes
                    for k in range(j + 1, len(row)):
                        if row[k] and str(row[k]).strip() and str(row[k]).strip() not in ("N°", "Nº", "No"):
                            result["quote_number"] = str(row[k]).strip()
                            break
                    break

        # ── Cliente y ejecutivo ─────────────────────────────────────────────
        if "cliente" in row_text and not result["client_name"]:
            for j, c in enumerate(row):
                if not c:
                    continue
                cs = str(c).strip().lower()
                if cs.startswith("cliente"):
                    # Nombre del cliente: 1-3 celdas a la derecha
                    for k in range(j + 1, min(j + 5, len(row))):
                        v = row[k]
                        if v and str(v).strip() and str(v).lower() not in ("cliente", "ejecutivo"):
                            result["client_name"] = str(v).strip()
                            break
                if "ejecutivo" in cs:
                    for k in range(j + 1, min(j + 3, len(row))):
                        v = row[k]
                        if v and str(v).strip():
                            result["sales_rep"] = str(v).strip()
                            break

        # ── Lugar del evento ────────────────────────────────────────────────
        if "lugar" in row_text and not result["venue"]:
            for j, c in enumerate(row):
                if c and "lugar" in str(c).lower():
                    for k in range(j + 1, min(j + 6, len(row))):
                        v = row[k]
                        if v and str(v).strip():
                            result["venue"] = str(v).strip()
                            break

        # ── Fila de encabezados de fecha → siguiente fila tiene los valores ─
        if (
            "fecha emitida" in row_text
            or ("emitida" in row_text and "fecha" in row_text)
            or "fecha emision" in row_text
        ) and not result["date_issued"]:
            if i + 1 < len(rows):
                nr = rows[i + 1]

                def _nr(j):
                    return nr[j] if j < len(nr) else None

                result["date_issued"] = _parse_date_cell(_nr(1))
                result["duration"]    = str(_nr(2)).strip() if _nr(2) else None

                # event_date: intentar parsear; guardar raw si no se puede
                ev_date_raw = _nr(3)
                parsed_ev   = _parse_date_cell(ev_date_raw)
                if parsed_ev:
                    result["event_date"] = parsed_ev
                elif ev_date_raw and str(ev_date_raw).strip():
                    result["event_date"] = str(ev_date_raw).strip()

                ev_type = _nr(5)
                if ev_type and str(ev_type).strip():
                    result["event_type"] = str(ev_type).strip()

                guests = _nr(7)
                if guests and str(guests).strip().lower() not in (
                    "no definido", "no determinado", "n/d", "none", ""
                ):
                    result["guests"] = str(guests).strip()

        # ── Encabezados de la tabla de ítems ───────────────────────────────
        if (
            items_start_idx is None
            and "cantidad" in row_text
            and ("descripci" in row_text or "dias" in row_text)
        ):
            items_start_idx = i + 1

        # ── Fila de subtotal (inicio de totales) ────────────────────────────
        if items_start_idx and totals_idx is None and (
            "subtotal" in row_text or "sub total" in row_text
        ):
            totals_idx = i
            # Subtotal: último valor numérico > 0 en la fila
            for c in reversed(row):
                v = _parse_price(c)
                if v > 0:
                    result["subtotal"] = v
                    break
            # ISV y Total en filas siguientes
            for offset in range(1, 6):
                ni = i + offset
                if ni >= len(rows):
                    break
                nr      = rows[ni]
                nr_text = " ".join(str(c or "").lower() for c in nr)
                if "isv" in nr_text or "impuesto" in nr_text:
                    for c in reversed(nr):
                        v = _parse_price(c)
                        if v > 0:
                            result["tax"]     = v
                            result["has_tax"] = True
                            break
                elif "total" in nr_text and "subtotal" not in nr_text and result["subtotal"]:
                    for c in reversed(nr):
                        v = _parse_price(c)
                        if v > 0 and v >= result["subtotal"]:
                            result["total"] = v
                            break
            break   # Ya encontramos totales → no seguir iterando

    # ── Parsear líneas de ítems ─────────────────────────────────────────────
    if items_start_idx is not None:
        end = totals_idx if totals_idx is not None else len(rows)
        for row in rows[items_start_idx:end]:
            if len(row) < 4:
                continue
            qty_raw  = row[1]                              # col B – Cantidad
            days_raw = row[2]                              # col C – Dias
            desc_raw = row[3]                              # col D – Descripción
            # col G (idx 6) = precio unitario; fallback a col F (idx 5) si G está vacío
            price_raw = row[6] if len(row) > 6 else None
            if _parse_price(price_raw) <= 0 and len(row) > 5:
                price_raw = row[5]  # col F como fallback (puede ser el precio o el total)

            if not desc_raw or not str(desc_raw).strip():
                continue

            desc  = str(desc_raw).strip()
            qty   = _parse_price(qty_raw)
            price = _parse_price(price_raw)

            # Filas completamente vacías (sin cantidad ni precio)
            if qty <= 0 and price <= 0:
                continue

            days = _parse_days(days_raw)

            result["items"].append({
                "description": desc,
                "quantity":    max(qty, 1.0),
                "days":        days,
                "unit_price":  price,
            })

    if not result["total"] and result["subtotal"]:
        result["total"] = result["subtotal"] + result["tax"]

    return result


# ─────────────────────────────────────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────────────────────────────────────

def parse_pdf(file_obj) -> dict:
    """Parsea un archivo PDF de cotización de Avvisi Audio con pdfplumber."""
    import pdfplumber

    result: dict = {
        "quote_number": None,
        "client_name":  None,
        "sales_rep":    None,
        "venue":        None,
        "event_date":   None,
        "event_type":   None,
        "guests":       None,
        "date_issued":  None,
        "duration":     None,
        "items":        [],
        "subtotal":     0.0,
        "tax":          0.0,
        "total":        0.0,
        "has_tax":      False,
        "errors":       [],
    }

    with pdfplumber.open(file_obj) as pdf:
        if not pdf.pages:
            result["errors"].append("PDF sin páginas.")
            return result
        page = pdf.pages[0]
        raw_text = page.extract_text() or ""
        tables   = page.extract_tables() or []

    # ── Parsear texto para info de encabezado ───────────────────────────────
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]

    for i, line in enumerate(lines):
        ll = line.lower()

        # Número de cotización
        if ("cotizacion" in ll or "cotización" in ll) and not result["quote_number"]:
            m = re.search(r"(\d{4}[-–]\d+)", line)
            if m:
                result["quote_number"] = m.group(1)
            elif i + 1 < len(lines):
                m2 = re.search(r"(\d{4}[-–]\d+)", lines[i + 1])
                if m2:
                    result["quote_number"] = m2.group(1)

        # Cliente + ejecutivo en la misma línea
        if ll.startswith("cliente") and not result["client_name"]:
            m = re.search(
                r"[Cc]liente\s+(.+?)\s+[Ee]jecutivo\s+de\s+[Vv]enta\s+(.+)",
                line,
            )
            if m:
                result["client_name"] = m.group(1).strip()
                result["sales_rep"]   = m.group(2).strip()
            else:
                parts = line.split(None, 1)
                if len(parts) > 1:
                    result["client_name"] = parts[1].strip()

        # Lugar del evento
        if ("lugar del evento" in ll or "lugar" in ll) and not result["venue"]:
            m = re.search(r"[Ll]ugar\s+del\s+[Ee]vento\s+(.+?)(?:\s+RTN\b|\s*$)", line)
            if m:
                result["venue"] = m.group(1).strip()

        # Fecha emitida → siguiente línea tiene los valores
        if ("fecha emitida" in ll or ("emitida" in ll and "fecha" in ll)) and not result["date_issued"]:
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                parts = nxt.split()
                if parts:
                    result["date_issued"] = _parse_date_cell(parts[0])
                # Tipo de evento: tercer campo significativo
                # Ej: "4/9/2025 oct-25 Congreso Tecnologico No definido"
                m = re.match(
                    r"\S+\s+\S+\s+(.+?)(?:\s+(?:No\s+[Dd]e|[Nn]o\s+[Dd]eter|\d+)\s*|\s*$)",
                    nxt,
                )
                if m:
                    result["event_type"] = m.group(1).strip()

    # ── Parsear tablas para ítems y totales ─────────────────────────────────
    for table in tables:
        items_section = False

        for row in table:
            if not row:
                continue
            clean    = [str(c or "").strip() for c in row]
            row_text = " ".join(clean).lower()

            # Encabezado de tabla de ítems
            if "cantidad" in row_text and ("dias" in row_text or "descripci" in row_text):
                items_section = True
                continue

            # SubTotal
            if "subtotal" in row_text or "sub total" in row_text:
                for c in reversed(clean):
                    v = _parse_price(c)
                    if v > 0:
                        result["subtotal"] = v
                        break
                continue

            # ISV
            if "isv" in row_text or "impuesto" in row_text:
                for c in reversed(clean):
                    v = _parse_price(c)
                    if v > 0:
                        result["tax"]     = v
                        result["has_tax"] = True
                        break
                continue

            # Total final
            if (
                "total" in row_text
                and "subtotal" not in row_text
                and "cantidad" not in row_text
                and result["subtotal"] > 0
            ):
                for c in reversed(clean):
                    v = _parse_price(c)
                    if v > 0 and v >= result["subtotal"]:
                        result["total"] = v
                        break
                continue

            if not items_section:
                continue

            # Fila de ítem: [qty, dias, descripción, precio_unitario, total_linea]
            if len(clean) < 3:
                continue

            qty_s  = clean[0]
            days_s = clean[1] if len(clean) > 1 else "1"
            desc   = clean[2] if len(clean) > 2 else ""
            price_s= clean[3] if len(clean) > 3 else "0"

            if not desc or not qty_s:
                continue

            qty   = _parse_price(qty_s)
            price = _parse_price(price_s)

            if qty <= 0 and price <= 0:
                continue

            result["items"].append({
                "description": desc,
                "quantity":    max(qty, 1.0),
                "days":        _parse_days(days_s),
                "unit_price":  price,
            })

    if not result["total"] and result["subtotal"]:
        result["total"] = result["subtotal"] + result["tax"]

    return result
