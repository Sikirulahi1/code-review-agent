from __future__ import annotations

from urllib.parse import quote

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Supabase Session Pooler settings.
    supabase_db_host: str
    supabase_db_port: int = 5432
    supabase_db_name: str
    supabase_db_user: str
    supabase_db_password: SecretStr
    supabase_sslmode: str = "require"

    # Runtime DB engine knobs.
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10

    def _build_postgres_url(self, *, driver: str, host: str, port: int) -> str:
        password = quote(self.supabase_db_password.get_secret_value(), safe="")
        database_name = quote(self.supabase_db_name, safe="")
        user = quote(self.supabase_db_user, safe="")
        sslmode = quote(self.supabase_sslmode, safe="")
        ssl_param = "ssl" if driver == "asyncpg" else "sslmode"

        return (
            f"postgresql+{driver}://{user}:{password}@{host}:{port}/{database_name}"
            f"?{ssl_param}={sslmode}"
        )

    @property
    def database_url(self) -> str:
        return self._build_postgres_url(
            driver="asyncpg",
            host=self.supabase_db_host,
            port=self.supabase_db_port,
        )

    @property
    def alembic_database_url(self) -> str:
        return self._build_postgres_url(
            driver="psycopg",
            host=self.supabase_db_host,
            port=self.supabase_db_port,
        )


settings = Settings()
