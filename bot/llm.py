import logging
from typing import Protocol

from openai import AsyncOpenAI

log = logging.getLogger(__name__)


class LLM(Protocol):
    async def generate(self, system: str, prompt: str) -> str: ...

    async def transcribe(self, audio: bytes, filename: str) -> str: ...


class OpenAICompatibleLLM:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def generate(self, system: str, prompt: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_tokens=1500,
        )
        return (resp.choices[0].message.content or "").strip()

    async def transcribe(self, audio: bytes, filename: str) -> str:
        resp = await self._client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename, audio),
            language="ru",
        )
        return resp.text.strip()


class MockLLM:
    """Заглушка для локальной разработки без ключа: возвращает демо-текст."""

    async def generate(self, system: str, prompt: str) -> str:
        head = prompt.strip().splitlines()[0]
        return (
            "🧪 Режим демо (LLM_API_KEY не задан).\n\n"
            f"{head}\n\n"
            "Здесь будет сгенерированный текст в вашем tone of voice.\n\n"
            "Запишись на френч — окошки на этой неделе ещё есть 💅\n\n"
            "#маникюр #френч"
        )

    async def transcribe(self, audio: bytes, filename: str) -> str:
        return "(демо) сделала сегодня френч, клиентка грызла ногти, мы нарастили, вышло супер"


def build_llm(api_key: str, base_url: str, model: str) -> LLM:
    if not api_key:
        log.warning("LLM_API_KEY is empty — using MockLLM")
        return MockLLM()
    return OpenAICompatibleLLM(api_key=api_key, base_url=base_url, model=model)
