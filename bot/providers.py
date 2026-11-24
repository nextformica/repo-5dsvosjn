"""Пресеты LLM-провайдеров. Все они отдают OpenAI-совместимый API, поэтому клиент один."""

from dataclasses import dataclass

from bot.config import Settings


@dataclass(frozen=True)
class Provider:
    name: str
    title: str
    base_url: str
    default_model: str
    api_key: str
    needs_key: bool = True
    supports_whisper: bool = False

    @property
    def ready(self) -> bool:
        return bool(self.api_key) or not self.needs_key


def build_providers(s: Settings) -> dict[str, Provider]:
    """Собирает доступные провайдеры из настроек. LLM_API_KEY — фолбэк для любого из них."""
    fallback = s.llm_api_key
    presets = {
        "openai": Provider(
            name="openai",
            title="OpenAI (ChatGPT API)",
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            api_key=s.openai_api_key or fallback,
            supports_whisper=True,
        ),
        "gemini": Provider(
            name="gemini",
            title="Google Gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            default_model="gemini-2.0-flash",
            api_key=s.gemini_api_key or fallback,
        ),
        "deepseek": Provider(
            name="deepseek",
            title="DeepSeek",
            base_url="https://api.deepseek.com/v1",
            default_model="deepseek-chat",
            api_key=s.deepseek_api_key or fallback,
        ),
        "openrouter": Provider(
            name="openrouter",
            title="OpenRouter (много моделей, работает из РФ)",
            base_url="https://openrouter.ai/api/v1",
            default_model="openai/gpt-4o-mini",
            api_key=s.openrouter_api_key or fallback,
        ),
        "ollama": Provider(
            name="ollama",
            title="Ollama (локально)",
            base_url=s.ollama_base_url,
            default_model="llama3.1",
            api_key="ollama",
            needs_key=False,
        ),
        "lmstudio": Provider(
            name="lmstudio",
            title="LM Studio (локально)",
            base_url=s.lmstudio_base_url,
            default_model="local-model",
            api_key="lm-studio",
            needs_key=False,
        ),
    }
    if s.llm_base_url:
        presets["custom"] = Provider(
            name="custom",
            title=f"Custom ({s.llm_base_url})",
            base_url=s.llm_base_url,
            default_model=s.llm_model or "default",
            api_key=fallback or "none",
            needs_key=False,
        )
    return presets
