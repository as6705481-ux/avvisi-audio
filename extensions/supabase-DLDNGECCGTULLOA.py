"""Clientes Supabase.

Este modulo reemplaza el viejo `db.py`.

Uso:
  from extensions.supabase import get_public_client, get_service_client
"""

from __future__ import annotations

from functools import lru_cache

from config import Settings

from supabase import create_client, Client


@lru_cache(maxsize=1)
def _settings() -> Settings:
    """Configuración: sí se cachea (es sólo lectura de env vars)."""
    return Settings()


def _require(value: str | None, name: str) -> str:
    if value:
        return value
    raise RuntimeError(
        f"Falta variable de entorno {name}. Definela antes de levantar Flask."
    )


def get_public_client() -> Client:
    """Crea un cliente fresco por llamada para evitar conexiones caducadas en Windows."""
    s = _settings()
    url = _require(s.supabase_url, "SUPABASE_URL")
    key = _require(s.supabase_anon_key, "SUPABASE_ANON_KEY")
    return create_client(url, key)


def get_service_client() -> Client:
    """Crea un cliente fresco por llamada para evitar conexiones caducadas en Windows."""
    s = _settings()
    url = _require(s.supabase_url, "SUPABASE_URL")
    key = _require(s.supabase_service_key, "SUPABASE_SERVICE_KEY")
    return create_client(url, key)
