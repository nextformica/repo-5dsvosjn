from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    free_generations: int = 3
    admin_ids: Annotated[list[int], NoDecode] = []
    payment_contact: str = "@your_username"
    db_path: str = "data/bot.db"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_admin_ids(cls, v: object) -> object:
        if isinstance(v, str):
            return [int(x) for x in v.split(",") if x.strip()]
        return v


settings = Settings()  # type: ignore[call-arg]  # bot_token приходит из окружения / .env
