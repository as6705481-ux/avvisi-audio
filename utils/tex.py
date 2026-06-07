from __future__ import annotations

import os
import re
from datetime import datetime

from utils.money import money_str


_LATEX_SPECIALS = {
    "\\": r"\\textbackslash{}",
    "&": r"\\&",
    "%": r"\\%",
    "$": r"\\$",
    "#": r"\\#",
    "_": r"\\_",
    "{": r"\\{",
    "}": r"\\}",
    "~": r"\\textasciitilde{}",
    "^": r"\\textasciicircum{}",
}


def latex_escape(text: str | None) -> str:
    if text is None:
        return ""
    out = str(text)
    for k, v in _LATEX_SPECIALS.items():
        out = out.replace(k, v)
    return out


def render_tex(template_str: str, ctx: dict) -> str:
    """Reemplaza {{VAR}} por valores en ctx."""

    def repl(m: re.Match) -> str:
        k = m.group(1).strip()
        return str(ctx.get(k, ""))

    return re.sub(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", repl, template_str)


def generate_tex_file(template_str: str, ctx: dict, output_path: str) -> str:
    tex_final = render_tex(template_str, ctx)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(tex_final)
    return output_path


def load_template(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_iso(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None


# def compute_days_for_line(line: dict, event: dict | None) -> int:
#     s = _parse_iso(line.get("start_at")) or (_parse_iso(event.get("start_at")) if event else None)
#     e = _parse_iso(line.get("end_at")) or (_parse_iso(event.get("end_at")) if event else None)
#     if not s or not e or e <= s:
#         return 1
#     days = (e.date() - s.date()).days
#     return max(1, days)


def build_line_items_tex(lines: list[dict], currency: str, event: dict | None) -> str:
    """Genera filas LaTeX:

    Descripcion & Precio & Cantidad & Dias & Total \\
    """
    rows: list[str] = []
    for ln in lines:
        try:
            qty = int(round(float(ln.get("quantity") or 0)))
        except Exception:
            qty = 0

        print("Line item:", ln)
        days = int(round(float(ln.get("days") or 0)))

        name = latex_escape(ln.get("custom_name") or "—")
        desc = latex_escape(ln.get("description") or "")
        sect = latex_escape(ln.get("section") or "")

        description = name
        if desc:
            description += r" \\ " + desc
        if sect:
            description += r" \\ \textit{" + sect + "}"

        unit_price = money_str(ln.get("unit_price"))
        line_total = money_str(ln.get("line_total"))

        rows.append(f"{description} & {unit_price} & {qty} & {days} & {line_total} \\\\")

    return "\n".join(rows)


def project_assets_dir(current_file: str) -> str:
    """Devuelve ruta assets/ relativa al archivo que llama (ej: blueprints/quotations/pdf.py)."""
    return os.path.join(os.path.dirname(current_file), "..", "..", "..", "assets")
