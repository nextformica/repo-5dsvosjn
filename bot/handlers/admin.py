import logging

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.config import settings
from bot.db import Database
from bot.llm import LLMRouter

log = logging.getLogger(__name__)
router = Router()
router.message.filter(lambda m: m.from_user is not None and m.from_user.id in settings.admin_ids)


@router.message(Command("grant"))
async def cmd_grant(message: Message, command: CommandObject, db: Database) -> None:
    args = (command.args or "").split()
    if len(args) not in (1, 2) or not all(a.isdigit() for a in args):
        await message.answer("Использование: /grant <user_id> [days=30]")
        return
    user_id = int(args[0])
    days = int(args[1]) if len(args) == 2 else 30
    if await db.get_user(user_id) is None:
        await message.answer("Пользователь не найден — он должен сначала написать боту /start.")
        return
    until = await db.grant_premium(user_id, days)
    await message.answer(f"Премиум для {user_id} активен до {until:%d.%m.%Y}")
    assert message.bot is not None
    try:
        await message.bot.send_message(user_id, f"👑 Подписка активна до {until:%d.%m.%Y}. Хорошей работы!")
    except TelegramAPIError:
        log.warning("Could not notify user %s about premium", user_id)


@router.message(Command("llm"))
async def cmd_llm(message: Message, command: CommandObject, db: Database, llm: LLMRouter) -> None:
    args = (command.args or "").split()
    if not args:
        lines = [f"Сейчас: <b>{llm.describe()}</b>\n", "Доступные провайдеры:"]
        for p in llm.providers.values():
            mark = "▶️" if p.name == llm.active_name else ("✅" if p.ready else "🔒")
            lines.append(f"{mark} <code>{p.name}</code> — {p.title} ({p.default_model})")
        lines.append("\nПереключить: <code>/llm &lt;provider&gt; [model]</code>")
        lines.append("🔒 — нет ключа в .env, будет демо-режим.")
        await message.answer("\n".join(lines))
        return
    name = args[0].lower()
    model = args[1] if len(args) > 1 else None
    if name not in llm.providers:
        await message.answer(f"Не знаю провайдера <code>{name}</code>. Список: /llm")
        return
    llm.switch(name, model)
    await db.set_setting("llm_provider", name)
    await db.set_setting("llm_model", model or "")
    note = "" if llm.providers[name].ready else "\n⚠️ Ключа нет — работает демо-заглушка."
    await message.answer(f"Переключила на <b>{llm.describe()}</b>{note}")


@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database) -> None:
    s = await db.stats()
    await message.answer(
        f"Пользователей: {s['users']}\n"
        f"Прошли онбординг: {s['onboarded']}\n"
        f"Генераций всего: {s['generations']}\n"
        f"Премиум: {s['premium']}"
    )
