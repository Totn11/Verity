from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = Field(validation_alias="DATABASE_URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
