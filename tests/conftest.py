import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("BOT_TOKEN", "42:TEST")
os.environ.setdefault("FREE_GENERATIONS", "3")
os.environ.setdefault("ADMIN_IDS", "999")
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test")

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.methods import TelegramMethod  # noqa: E402
from aiogram.methods.base import TelegramType  # noqa: E402
from aiogram.types import (  # noqa: E402
    CallbackQuery,
    Chat,
    Message,
    Update,
    User,
)

from bot.config import settings  # noqa: E402
from bot.db import Database  # noqa: E402
from bot.handlers import build_router  # noqa: E402
from bot.llm import LLMRouter  # noqa: E402
from bot.providers import build_providers  # noqa: E402


class FakeBot(Bot):
    """Перехватывает вызовы Telegram API и складывает их в список."""

    def __init__(self) -> None:
        super().__init__(token="42:TEST", default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.calls: list[TelegramMethod[Any]] = []
        self._msg_id = 1000

    async def __call__(self, method: TelegramMethod[TelegramType], request_timeout: int | None = None) -> Any:
        self.calls.append(method)
        name = type(method).__name__
        if name in ("SendMessage", "EditMessageText"):
            self._msg_id += 1
            return Message(
                message_id=self._msg_id,
                date=datetime.now(UTC),
                chat=Chat(id=getattr(method, "chat_id", 1), type="private"),
                from_user=User(id=42, is_bot=True, first_name="Bot"),
                text=getattr(method, "text", None),
            ).as_(self)
        return True

    def all_texts(self) -> str:
        return "\n".join(
            m.text for m in self.calls if type(m).__name__ in ("SendMessage", "EditMessageText") and m.text
        )


class Harness:
    def __init__(self, bot: FakeBot, dp: Dispatcher, user_id: int = 1) -> None:
        self.bot = bot
        self.dp = dp
        self.user = User(id=user_id, is_bot=False, first_name="Мастер", username="master")
        self.chat = Chat(id=user_id, type="private")
        self._upd = 0
        self._msg = 0

    async def send(self, text: str) -> None:
        self._upd += 1
        self._msg += 1
        msg = Message(
            message_id=self._msg, date=datetime.now(UTC), chat=self.chat, from_user=self.user, text=text
        )
        await self.dp.feed_update(self.bot, Update(update_id=self._upd, message=msg))

    async def click(self, data: str) -> None:
        self._upd += 1
        self._msg += 1
        bot_msg = Message(
            message_id=self._msg,
            date=datetime.now(UTC),
            chat=self.chat,
            from_user=User(id=42, is_bot=True, first_name="Bot"),
            text="…",
        )
        cb = CallbackQuery(
            id=str(self._upd), from_user=self.user, chat_instance="x", message=bot_msg, data=data
        )
        await self.dp.feed_update(self.bot, Update(update_id=self._upd, callback_query=cb))


@pytest.fixture(scope="session")
def dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(build_router())
    return dp


@pytest.fixture
async def harness(tmp_path: Path, dispatcher: Dispatcher) -> AsyncIterator[Harness]:
    db = Database(str(tmp_path / "test.db"))
    await db.init()
    dispatcher["db"] = db
    # openai без ключа → MockLLM; deepseek с фейковым ключом даёт проверить переключение
    dispatcher["llm"] = LLMRouter(build_providers(settings), settings.llm_provider)
    storage = dispatcher.storage
    assert isinstance(storage, MemoryStorage)
    storage.storage.clear()
    bot = FakeBot()
    yield Harness(bot, dispatcher)
    await bot.session.close()
