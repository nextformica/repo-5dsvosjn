import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import settings
from bot.db import Database
from bot.handlers import build_router
from bot.llm import build_llm

COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="profile", description="Мой профиль"),
    BotCommand(command="setup", description="Перенастроить профиль"),
    BotCommand(command="tariff", description="Тарифы и лимиты"),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    db = Database(settings.db_path)
    await db.init()
    llm = build_llm(settings.llm_api_key, settings.llm_base_url, settings.llm_model)

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp["db"] = db
    dp["llm"] = llm
    dp.include_router(build_router())

    await bot.set_my_commands(COMMANDS)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
