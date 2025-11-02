import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE")
ANON_KEY     = os.getenv("SUPABASE_ANON_KEY")

def get_public_client() -> Client:
    assert SUPABASE_URL and ANON_KEY, "Faltan SUPABASE_URL o SUPABASE_ANON_KEY"
    return create_client(SUPABASE_URL, ANON_KEY)

def get_service_client() -> Client:
    assert SUPABASE_URL and SERVICE_ROLE, "Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE"
    return create_client(SUPABASE_URL, SERVICE_ROLE)

def get_supabase() -> Client:
    """
    Crea un cliente Supabase con Service Role para backend (bypasa RLS).
    Úsalo SOLO en el servidor.
    """
    return create_client(SUPABASE_URL, SERVICE_ROLE)