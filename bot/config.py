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
    db_path: str = "data/bot.db"

    # Платежи (см. bot/payments/): manual | yookassa | robokassa | platega; переключается командой /pay.
    payment_provider: str = "manual"
    payment_contact: str = "@your_username"
    subscription_days: int = 30
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_sbp_only: bool = False
    robokassa_login: str = ""
    robokassa_password1: str = ""
    robokassa_password2: str = ""
    robokassa_test: bool = False
    robokassa_hash: str = "md5"
    robokassa_inc_curr_label: str = ""
    platega_merchant_id: str = ""
    platega_secret: str = ""
    platega_payment_method: int = 2
    # HTTP-сервер для вебхуков платёжек; 0 — выключен (тогда оплата проверяется кнопкой «Я оплатила»).
    webhook_port: int = 0
    webhook_host: str = "0.0.0.0"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_admin_ids(cls, v: object) -> object:
        if isinstance(v, str):
            return [int(x) for x in v.split(",") if x.strip()]
        return v


settings = Settings()  # type: ignore[call-arg]  # bot_token приходит из окружения / .env
