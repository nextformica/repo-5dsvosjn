import logging
from typing import Protocol

from openai import AsyncOpenAI

from bot.providers import Provider

log = logging.getLogger(__name__)


class LLM(Protocol):
    async def generate(self, system: str, prompt: str) -> str: ...

    async def transcribe(self, audio: bytes, filename: str) -> str: ...

    def describe(self) -> str: ...


class OpenAICompatibleLLM:
    def __init__(self, provider: Provider, model: str | None = None) -> None:
        self.provider = provider
        self.model = model or provider.default_model
        self._client = AsyncOpenAI(api_key=provider.api_key, base_url=provider.base_url)

    async def generate(self, system: str, prompt: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_tokens=1500,
        )
        return (resp.choices[0].message.content or "").strip()

    async def transcribe(self, audio: bytes, filename: str) -> str:
        if not self.provider.supports_whisper:
            raise TranscriptionUnavailable(self.provider.title)
        resp = await self._client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename, audio),
            language="ru",
        )
        return resp.text.strip()

    def describe(self) -> str:
        return f"{self.provider.title} · {self.model}"


class MockLLM:
    """Заглушка для разработки без ключа: возвращает демо-текст."""

    async def generate(self, system: str, prompt: str) -> str:
        head = prompt.strip().splitlines()[0]
        return (
            "🧪 Режим демо (ключ LLM не задан).\n\n"
            f"{head}\n\n"
            "Здесь будет сгенерированный текст в вашем tone of voice.\n\n"
            "Запишись на френч — окошки на этой неделе ещё есть 💅\n\n"
            "#маникюр #френч"
        )

    async def transcribe(self, audio: bytes, filename: str) -> str:
        return "(демо) сделала сегодня френч, клиентка грызла ногти, мы нарастили, вышло супер"

    def describe(self) -> str:
        return "MockLLM (демо)"


class TranscriptionUnavailable(Exception):
    pass


class LLMRouter:
    """Держит активного провайдера и позволяет переключать его на лету."""

    def __init__(self, providers: dict[str, Provider], default: str, model: str = "") -> None:
        self.providers = providers
        self._active: LLM = MockLLM()
        self.active_name = "mock"
        self.switch(default, model or None)

    def switch(self, name: str, model: str | None = None) -> LLM:
        provider = self.providers.get(name)
        if provider is None:
            raise KeyError(name)
        if not provider.ready:
            log.warning("Provider %s has no API key — using MockLLM", name)
            self._active = MockLLM()
        else:
            self._active = OpenAICompatibleLLM(provider, model)
        self.active_name = name
        return self._active

    async def generate(self, system: str, prompt: str) -> str:
        return await self._active.generate(system, prompt)

    async def transcribe(self, audio: bytes, filename: str) -> str:
        """Голосовые распознаёт активный провайдер, а если он не умеет — OpenAI при наличии ключа."""
        try:
            return await self._active.transcribe(audio, filename)
        except TranscriptionUnavailable:
            openai = self.providers.get("openai")
            if openai is None or not openai.ready:
                raise
            return await OpenAICompatibleLLM(openai).transcribe(audio, filename)

    def describe(self) -> str:
        return self._active.describe()
