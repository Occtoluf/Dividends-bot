from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    tbank_token: str = Field(alias="TBANK_TOKEN")
    telegram_token: str = Field(alias="TELEGRAM_TOKEN")
    telegram_user_id: int = Field(alias="TELEGRAM_USER_ID")
    db_path: Path = Field(default=Path("data/dividends.db"), alias="DB_PATH")

    catalog_ttl_hours: int = 24
    dividends_ttl_hours: int = 1
    fuzzy_score_cutoff: int = 60
    suggestion_limit: int = 5


settings = Settings()  # type: ignore[call-arg]
