import logging

import httpx
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.db import Database, User
from bot.keyboards import BTN_TARIFF, main_menu, pay_kb, paywall_kb
from bot.payments import PLANS, PaymentError, PaymentRouter
from bot.payments.service import activate_payment

log = logging.getLogger(__name__)
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
async def buy(cb: CallbackQuery, db: Database, payments: PaymentRouter) -> None:
    assert cb.data is not None and isinstance(cb.message, Message)
    plan = PLANS.get(cb.data.split(":", 1)[1], PLANS["basic"])
    plan_text = f"{plan.title} ({plan.amount} ₽/мес)"
    await db.get_or_create_user(cb.from_user.id, cb.from_user.username)

    provider = payments.active
    if provider.name == "manual":
        await cb.message.answer(
            f"Ты выбрала тариф <b>{plan_text}</b> 💎\n\n"
            f"Напиши {settings.payment_contact} — пришлём реквизиты и включим доступ в течение часа.\n\n"
            f"Твой ID для активации: <code>{cb.from_user.id}</code>"
        )
        await cb.answer()
        return

    payment = await db.create_payment(cb.from_user.id, plan.code, plan.amount, provider.name)
    try:
        created = await provider.create(payment, plan, payments.return_url)
    except (PaymentError, httpx.HTTPError, KeyError, ValueError):
        log.exception("Payment creation failed (%s)", provider.name)
        await cb.message.answer(
            "Не получилось создать счёт 😔 Попробуй ещё раз через минуту "
            f"или напиши {settings.payment_contact}."
        )
        await cb.answer()
        return
    await db.set_payment_external_id(payment.id, created.external_id)
    await cb.message.answer(
        f"Тариф <b>{plan_text}</b> 💎\n\n"
        f"Счёт №{payment.id} на {plan.amount} ₽ через {provider.title}.\n"
        "Нажми «Оплатить», а после оплаты — «Я оплатила», и подписка включится сразу.",
        reply_markup=pay_kb(created.url, payment.id, plan.amount),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("check:"))
async def check_payment(cb: CallbackQuery, db: Database, payments: PaymentRouter) -> None:
    assert cb.data is not None and isinstance(cb.message, Message)
    payment = await db.get_payment(int(cb.data.split(":", 1)[1]))
    if payment is None or payment.user_id != cb.from_user.id:
        await cb.answer("Счёт не найден", show_alert=True)
        return
    if payment.is_paid:
        user = await db.get_user(payment.user_id)
        await cb.message.answer(remaining_text(user) if user else "Оплачено ✅", reply_markup=main_menu())
        await cb.answer()
        return
    provider = payments.providers[payment.provider]
    try:
        paid = await provider.is_paid(payment)
    except (PaymentError, httpx.HTTPError, ValueError):
        log.exception("Payment check failed (%s)", provider.name)
        await cb.answer("Платёжка не отвечает, попробуй через минуту", show_alert=True)
        return
    if not paid:
        await cb.answer(
            "Оплата пока не пришла. Если платила только что — подожди минуту и нажми ещё раз.",
            show_alert=True,
        )
        return
    await activate_payment(payment, db, None)
    user = await db.get_user(payment.user_id)
    assert user is not None
    await cb.message.answer(f"👑 Оплата получена!\n{remaining_text(user)}", reply_markup=main_menu())
    await cb.answer()
