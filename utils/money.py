from __future__ import annotations


def money_float(x) -> float:
    """Convierte a float seguro (None -> 0)."""
    try:
        return round(float(x or 0), 2)
    except Exception:
        return 0.0


def money_str(x) -> str:
    """Formatea con 2 decimales y separador de miles."""
    try:
        return f"{float(x or 0):,.2f}"
    except Exception:
        return "0.00"
