from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.db import Database, User
from bot.keyboards import BTN_TARIFF, main_menu, paywall_kb

router = Router()

TARIFFS = (
    "<b>Тарифы</b>\n\n"
    "💎 <b>Базовый</b> — 990 ₽/мес\n"
    "До 50 генераций в месяц: посты, контент-планы, Reels, ответы в Директ.\n\n"
    "👑 <b>Безлимит</b> — 2490 ₽/мес\n"
    "Без ограничений + скоро: картинки для сторис и анализ конкурентов.\n"
)

PAYWALL = (
    "Бесплатные генерации закончились 🙈\n\n"
    "Ты уже увидела, как это работает. Дальше — подписка: "
    "это дешевле одной клиентки, а экономит часы каждую неделю.\n\n" + TARIFFS
)


def remaining_text(user: User) -> str:
    if user.is_premium:
        assert user.premium_until is not None
        return f"👑 Подписка активна до {user.premium_until:%d.%m.%Y}"
    left = max(settings.free_generations - user.generations_used, 0)
    return f"Осталось бесплатных генераций: {left} из {settings.free_generations}"


@router.message(Command("tariff"))
@router.message(F.text == BTN_TARIFF)
async def cmd_tariff(message: Message, db: Database) -> None:
    assert message.from_user is not None
    user = await db.get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"{remaining_text(user)}\n\n{TARIFFS}",
        reply_markup=paywall_kb() if not user.is_premium else main_menu(),
    )


@router.callback_query(F.data.startswith("buy:"))
async def buy(cb: CallbackQuery) -> None:
    assert cb.data is not None and isinstance(cb.message, Message)
    plan = "Базовый (990 ₽/мес)" if cb.data.endswith("basic") else "Безлимит (2490 ₽/мес)"
    await cb.message.answer(
        f"Ты выбрала тариф <b>{plan}</b> 💎\n\n"
        f"Онлайн-оплата подключается. Пока напиши {settings.payment_contact} — "
        f"пришлём реквизиты и включим доступ вручную в течение часа.\n\n"
        f"Твой ID для активации: <code>{cb.from_user.id}</code>"
    )
    await cb.answer()
