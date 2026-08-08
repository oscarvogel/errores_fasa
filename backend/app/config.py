from functools import lru_cache
from re import fullmatch

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "FASA Error Monitor"
    app_env: str = "production"
    cors_origins: str = "http://localhost:5173,http://localhost:8088"

    db_host: str
    db_port: int = 3306
    db_name: str
    db_user: str
    db_password: str
    db_charset: str = "utf8mb4"

    error_table: str = "sys_errores"
    error_id_column: str = "id_error"
    branches_table: str = "sucursales"

    # Credenciales comunes para leer los MySQL de las sucursales.
    # El host/puerto se obtiene de la tabla `sucursales`.
    remote_db_name: str = "fasa"
    remote_db_user: str = "error_dashboard"
    remote_db_password: str = ""
    remote_db_charset: str = "utf8mb4"
    remote_error_table: str = "sys_errores"
    remote_connect_timeout: int = 8
    sync_batch_size: int = 1000

    # Cache local de errores remotos. No escribe en el MySQL de producción.
    sync_db_path: str = "/data/sync.db"

    @field_validator("error_table", "error_id_column", "branches_table", "remote_error_table")
    @classmethod
    def validate_sql_identifier(cls, value: str) -> str:
        if not fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            raise ValueError("Solo se permiten identificadores SQL simples")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def database_url(self) -> str:
        from urllib.parse import quote_plus

        password = quote_plus(self.db_password)
        user = quote_plus(self.db_user)
        return (
            f"mysql+pymysql://{user}:{password}@{self.db_host}:{self.db_port}/"
            f"{self.db_name}?charset={self.db_charset}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
