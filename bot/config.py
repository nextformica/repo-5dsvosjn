from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str

    # Провайдер по умолчанию (см. bot/providers.py); переключается на лету командой /llm.
    llm_provider: str = "openai"
    # Общий ключ-фолбэк и переопределения для любого провайдера.
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    # Ключи конкретных провайдеров — можно держать несколько и переключаться между ними.
    openai_api_key: str = ""
    gemini_api_key: str = ""
    deepseek_api_key: str = ""
    openrouter_api_key: str = ""
    # Локальные серверы: адрес можно поменять, если порт нестандартный.
    ollama_base_url: str = "http://localhost:11434/v1"
    lmstudio_base_url: str = "http://localhost:1234/v1"

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
