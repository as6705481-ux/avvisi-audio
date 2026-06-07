from __future__ import annotations

from flask import flash


def flash_exception(prefix: str, exc: Exception, category: str = "error") -> None:
    msg = getattr(exc, "message", None) or str(exc)
    flash(f"{prefix}: {msg}", category)
