"""Clientes Supabase.

Este modulo reemplaza el viejo `db.py`.

Uso:
  from extensions.supabase import get_public_client, get_service_client

NOTA DE RENDIMIENTO
-------------------
Antes se creaba un cliente nuevo en CADA llamada para evitar conexiones
caducadas. Medido, eso costaba ~390 ms por cliente y hacía que una consulta
trivial pasara de ~330 ms a ~1080 ms. Con 80+ puntos de llamada, era la
principal causa de lentitud de la app.

supabase-py 2.x usa httpx por debajo, cuyo pool de conexiones ya detecta y
reemplaza conexiones cerradas por el servidor, así que cachear el cliente es
seguro (httpx.Client es thread-safe, incluido el uso desde ThreadPoolExecutor
del dashboard). Si alguna vez hiciera falta forzar una reconexión, está
`reset_clients()`.
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


@lru_cache(maxsize=1)
def get_public_client() -> Client:
    """Cliente anónimo (cacheado; reutiliza el pool de conexiones de httpx)."""
    s = _settings()
    url = _require(s.supabase_url, "SUPABASE_URL")
    key = _require(s.supabase_anon_key, "SUPABASE_ANON_KEY")
    return create_client(url, key)


@lru_cache(maxsize=1)
def get_service_client() -> Client:
    """Cliente con service role (cacheado; reutiliza el pool de conexiones)."""
    s = _settings()
    url = _require(s.supabase_url, "SUPABASE_URL")
    key = _require(s.supabase_service_key, "SUPABASE_SERVICE_KEY")
    return create_client(url, key)


def reset_clients() -> None:
    """Descarta los clientes cacheados (fuerza reconexión en la próxima llamada)."""
    get_public_client.cache_clear()
    get_service_client.cache_clear()
