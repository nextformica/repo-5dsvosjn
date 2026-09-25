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
from bot.llm import LLMRouter
from bot.payments import PaymentRouter, build_payment_providers
from bot.providers import build_providers
from bot.webhook import build_app, start_server

log = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="profile", description="Мой профиль"),
    BotCommand(command="setup", description="Перенастроить профиль"),
    BotCommand(command="tariff", description="Тарифы и лимиты"),
]


async def build_router_from_db(db: Database) -> LLMRouter:
    """Провайдер, выбранный через /llm, переживает рестарт; иначе берётся LLM_PROVIDER из .env."""
    providers = build_providers(settings)
    name = await db.get_setting("llm_provider") or settings.llm_provider
    model = await db.get_setting("llm_model") or settings.llm_model
    if name not in providers:
        log.warning("Unknown LLM_PROVIDER=%s, falling back to openai", name)
        name, model = "openai", ""
    return LLMRouter(providers, name, model)


async def build_payments_from_db(db: Database, return_url: str) -> PaymentRouter:
    providers = build_payment_providers(settings)
    name = await db.get_setting("payment_provider") or settings.payment_provider
    if name not in providers:
        log.warning("Unknown PAYMENT_PROVIDER=%s, falling back to manual", name)
        name = "manual"
    return PaymentRouter(providers, name, return_url)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    db = Database(settings.db_path)
    await db.init()
    llm = await build_router_from_db(db)
    log.info("LLM: %s", llm.describe())

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    payments = await build_payments_from_db(db, f"https://t.me/{me.username}")
    log.info("Payments: %s", payments.active.title)

    dp = Dispatcher(storage=MemoryStorage())
    dp["db"] = db
    dp["llm"] = llm
    dp["payments"] = payments
    dp.include_router(build_router())

    runner = None
    if settings.webhook_port:
        runner = await start_server(
            build_app(db, payments, bot), settings.webhook_host, settings.webhook_port
        )

    await bot.set_my_commands(COMMANDS)
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        if runner is not None:
            await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
