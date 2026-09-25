import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot.db import Database, Payment
from bot.payments import PLANS, WebhookResult
from bot.payments.base import PaymentProvider

log = logging.getLogger(__name__)


async def activate_payment(payment: Payment, db: Database, bot: Bot | None) -> bool:
    """Помечает платёж оплаченным и включает подписку. False — уже был активирован."""
    if not await db.mark_payment_paid(payment.id):
        return False
    plan = PLANS.get(payment.plan, PLANS["basic"])
    until = await db.grant_premium(payment.user_id, plan.days)
    log.info(
        "Payment %s paid via %s: user=%s plan=%s", payment.id, payment.provider, payment.user_id, plan.code
    )
    if bot is not None:
        try:
            await bot.send_message(
                payment.user_id,
                f"👑 Оплата получена! Тариф <b>{plan.title}</b> активен до {until:%d.%m.%Y}. Хорошей работы!",
            )
        except TelegramAPIError:
            log.warning("Could not notify user %s about payment", payment.user_id)
    return True


async def handle_webhook(
    provider: PaymentProvider,
    result: WebhookResult,
    db: Database,
    bot: Bot | None,
) -> None:
    if result.payment_id is not None:
        payment = await db.get_payment(result.payment_id)
    elif result.external_id is not None:
        payment = await db.get_payment_by_external_id(provider.name, result.external_id)
    else:
        payment = None
    if payment is None or payment.provider != provider.name:
        log.warning("%s webhook: unknown payment %s", provider.name, result)
        return
    if result.amount is not None and result.amount != payment.amount:
        log.warning(
            "%s webhook: amount %s != %s for payment %s",
            provider.name,
            result.amount,
            payment.amount,
            payment.id,
        )
        return
    if result.paid:
        await activate_payment(payment, db, bot)
