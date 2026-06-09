from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./slopstudy.db"
    secret_key: str = "changeme"
    cors_origins: str = "*"
    version: str = "0.1.0"

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
