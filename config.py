import os

from dotenv import load_dotenv

load_dotenv()

class Settings:
    """Configuracion central para la app.

    Variables de entorno:
      - SECRET_KEY
      - SUPABASE_URL
      - SUPABASE_ANON_KEY
      - SUPABASE_SERVICE_KEY
      - TZ_DEFAULT (opcional)
    """

    def __init__(self) -> None:
        self.env: str = os.getenv("FLASK_ENV", os.getenv("ENV", "development"))

        # Flask
        self.secret_key: str = os.getenv("SECRET_KEY", "cambia-esto")

        # Supabase
        self.supabase_url: str | None = os.getenv("SUPABASE_URL")
        self.supabase_anon_key: str | None = os.getenv("SUPABASE_ANON_KEY")
        self.supabase_service_key: str | None = os.getenv("SUPABASE_SERVICE_KEY")

        # Fechas
        self.tz_default: str = os.getenv("TZ_DEFAULT", "America/Tegucigalpa")
