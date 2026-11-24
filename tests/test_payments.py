import asyncio
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest
from aiogram import Dispatcher
from aiogram.methods import SendMessage
from aiohttp.test_utils import TestClient, TestServer

from bot.db import Database, Payment
from bot.keyboards import BTN_POST
from bot.payments import PLANS, PaymentRouter
from bot.payments.base import CreatedPayment, Plan, WebhookResult
from bot.payments.platega import PlategaProvider
from bot.payments.robokassa import RobokassaProvider
from bot.webhook import build_app
from tests.conftest import Harness
from tests.test_flow import onboard


class FakeAcquirer:
    """Платёжка-заглушка: выдаёт ссылку, «оплату» включаем руками."""

    name = "fake"
    title = "Fake Pay"
    ready = True
    supports_check = True

    def __init__(self) -> None:
        self.paid: set[str] = set()
        self.created: list[Payment] = []

    async def create(self, payment: Payment, plan: Plan, return_url: str) -> CreatedPayment:
        self.created.append(payment)
        return CreatedPayment(url=f"https://pay.example/{payment.id}", external_id=f"ext-{payment.id}")

    async def is_paid(self, payment: Payment) -> bool:
        return payment.external_id in self.paid

    async def parse_webhook(
        self, headers: dict[str, str], body: bytes, query: dict[str, str]
    ) -> WebhookResult | None:
        if headers.get("X-Token") != "secret":
            return None
        return WebhookResult(paid=True, external_id=body.decode())

    def webhook_ok_response(self, result: WebhookResult) -> str:
        return "OK"


def db_of(h: Harness) -> Database:
    db = h.dp["db"]
    assert isinstance(db, Database)
    return db


def payments_of(h: Harness) -> PaymentRouter:
    p = h.dp["payments"]
    assert isinstance(p, PaymentRouter)
    return p


def last_markup(h: Harness) -> list[list[str]]:
    for m in reversed(h.bot.calls):
        if isinstance(m, SendMessage) and m.reply_markup is not None:
            kb = getattr(m.reply_markup, "inline_keyboard", None)
            if kb:
                return [[b.url or b.callback_data or "" for b in row] for row in kb]
    return []


async def test_manual_provider_shows_contact(harness: Harness) -> None:
    await onboard(harness)
    harness.bot.calls.clear()
    await harness.click("buy:unlimited")
    text = harness.bot.all_texts()
    assert "Безлимит (2490 ₽/мес)" in text and "@test_admin" in text and "<code>1</code>" in text


async def test_online_payment_flow_with_check_button(harness: Harness) -> None:
    await onboard(harness)
    fake = FakeAcquirer()
    payments = payments_of(harness)
    payments.providers["fake"] = fake
    payments.switch("fake")

    harness.bot.calls.clear()
    await harness.click("buy:basic")
    text = harness.bot.all_texts()
    assert "Счёт №1 на 990 ₽ через Fake Pay" in text
    assert last_markup(harness) == [["https://pay.example/1"], ["check:1"]]
    payment = await db_of(harness).get_payment(1)
    assert payment is not None and payment.external_id == "ext-1" and not payment.is_paid

    harness.bot.calls.clear()
    await harness.click("check:1")
    assert "Оплата получена" not in harness.bot.all_texts()
    user = await db_of(harness).get_user(1)
    assert user is not None and not user.is_premium

    fake.paid.add("ext-1")
    await harness.click("check:1")
    assert "Оплата получена" in harness.bot.all_texts()
    user = await db_of(harness).get_user(1)
    assert user is not None and user.is_premium
    payment = await db_of(harness).get_payment(1)
    assert payment is not None and payment.is_paid

    # Повторный клик не продлевает подписку второй раз.
    harness.bot.calls.clear()
    await harness.click("check:1")
    assert "Подписка активна до" in harness.bot.all_texts()

    # Чужой счёт недоступен.
    other = Harness(harness.bot, harness.dp, user_id=2)
    harness.bot.calls.clear()
    await other.click("check:1")
    assert "Оплата получена" not in harness.bot.all_texts()


async def test_webhook_server_activates_subscription(harness: Harness) -> None:
    await onboard(harness)
    fake = FakeAcquirer()
    payments = payments_of(harness)
    payments.providers["fake"] = fake
    payments.switch("fake")
    await harness.click("buy:unlimited")

    app = build_app(db_of(harness), payments, None)
    async with TestClient(TestServer(app)) as client:
        bad = await client.post("/webhook/fake", data="ext-1")
        assert bad.status == 403
        missing = await client.post("/webhook/nope", data="x")
        assert missing.status == 404
        ok = await client.post("/webhook/fake", data="ext-1", headers={"X-Token": "secret"})
        assert ok.status == 200 and await ok.text() == "OK"
        unknown = await client.post("/webhook/fake", data="ext-999", headers={"X-Token": "secret"})
        assert unknown.status == 200

    user = await db_of(harness).get_user(1)
    assert user is not None and user.is_premium
    stats = await db_of(harness).stats()
    assert stats["paid"] == 1 and stats["revenue"] == 2490


async def test_admin_switches_payment_provider(harness: Harness) -> None:
    admin = Harness(harness.bot, harness.dp, user_id=999)
    await admin.send("/pay")
    text = harness.bot.all_texts()
    assert "▶️ <code>manual</code>" in text
    assert "✅ <code>robokassa</code>" in text and "✅ <code>platega</code>" in text
    assert "🔒 <code>yookassa</code>" in text

    harness.bot.calls.clear()
    await admin.send("/pay yookassa")
    assert "не заполнены ключи" in harness.bot.all_texts()
    assert payments_of(harness).active_name == "manual"

    await admin.send("/pay nope")
    assert "Не знаю способа" in harness.bot.all_texts()

    harness.bot.calls.clear()
    await admin.send("/pay platega")
    assert "Оплата теперь через <b>Platega (СБП)</b>" in harness.bot.all_texts()
    assert payments_of(harness).active_name == "platega"
    assert await db_of(harness).get_setting("payment_provider") == "platega"

    harness.bot.calls.clear()
    await harness.send("/pay robokassa")
    assert harness.bot.all_texts() == ""
    assert payments_of(harness).active_name == "platega"


async def test_robokassa_link_and_result_url() -> None:
    rk = RobokassaProvider("demo", "pass1", "pass2", test=True)
    payment = Payment(
        id=7, user_id=1, plan="basic", amount=990, provider="robokassa", external_id=None, status="pending"
    )
    created = await rk.create(payment, PLANS["basic"], "https://t.me/x")
    q = {k: v[0] for k, v in parse_qs(urlparse(created.url).query).items()}
    assert (
        q["MerchantLogin"] == "demo" and q["OutSum"] == "990.00" and q["InvId"] == "7" and q["IsTest"] == "1"
    )
    assert q["SignatureValue"] == hashlib.md5(b"demo:990.00:7:pass1").hexdigest()

    good_sig = hashlib.md5(b"990.00:7:pass2").hexdigest().upper()
    result = await rk.parse_webhook({}, f"OutSum=990.00&InvId=7&SignatureValue={good_sig}".encode(), {})
    assert result == WebhookResult(paid=True, payment_id=7, amount=990)
    assert rk.webhook_ok_response(result) == "OK7"
    assert await rk.parse_webhook({}, b"OutSum=990.00&InvId=7&SignatureValue=deadbeef", {}) is None
    assert await rk.parse_webhook({}, b"OutSum=1.00&InvId=7&SignatureValue=" + good_sig.encode(), {}) is None
    assert await rk.parse_webhook({}, f"OutSum=990.00&InvId=x&SignatureValue={good_sig}".encode(), {}) is None

    unconfigured = RobokassaProvider("", "", "")
    empty_sig = hashlib.md5(b"990.00:7:").hexdigest()
    assert not unconfigured.ready
    body = f"OutSum=990.00&InvId=7&SignatureValue={empty_sig}".encode()
    assert await unconfigured.parse_webhook({}, body, {}) is None


async def test_webhook_rejects_wrong_amount_provider_and_unconfigured(harness: Harness) -> None:
    await onboard(harness)
    fake = FakeAcquirer()
    payments = payments_of(harness)
    payments.providers["fake"] = fake
    payments.switch("fake")
    await harness.click("buy:unlimited")  # payment #1, provider=fake, 2490 ₽
    db = db_of(harness)

    app = build_app(db, payments, None)
    async with TestClient(TestServer(app)) as client:
        # Подписанный вебхук Robokassa не активирует счёт другого провайдера.
        sig = hashlib.md5(b"2490.00:1:pass2").hexdigest()
        r = await client.post("/webhook/robokassa", data=f"OutSum=2490.00&InvId=1&SignatureValue={sig}")
        assert r.status == 200
        p = await db.get_payment(1)
        assert p is not None and not p.is_paid

        # Недоплата по подписанному вебхуку не активирует счёт.
        rk = await db.create_payment(1, "unlimited", 2490, "robokassa")
        sig = hashlib.md5(f"1.00:{rk.id}:pass2".encode()).hexdigest()
        r = await client.post("/webhook/robokassa", data=f"OutSum=1.00&InvId={rk.id}&SignatureValue={sig}")
        assert r.status == 200
        p = await db.get_payment(rk.id)
        assert p is not None and not p.is_paid

        sig = hashlib.md5(f"2490.00:{rk.id}:pass2".encode()).hexdigest()
        r = await client.post("/webhook/robokassa", data=f"OutSum=2490.00&InvId={rk.id}&SignatureValue={sig}")
        assert r.status == 200 and await r.text() == f"OK{rk.id}"
        p = await db.get_payment(rk.id)
        assert p is not None and p.is_paid

        # Провайдер без ключей и manual не принимают вебхуки вообще; кривой JSON → 403, не 500.
        assert (await client.post("/webhook/yookassa", data="{}")).status == 404
        assert (await client.post("/webhook/manual", data="x")).status == 404
        pg_headers = {"X-MerchantId": "m-1", "X-Secret": "s-1"}
        assert (await client.post("/webhook/platega", data="[1,2]", headers=pg_headers)).status == 403
        assert (await client.post("/webhook/platega", data="null", headers=pg_headers)).status == 403

    user = await db.get_user(1)
    assert user is not None and user.is_premium


async def test_bad_callback_data_is_handled(harness: Harness) -> None:
    await onboard(harness)
    harness.bot.calls.clear()
    for data in ("check:abc", "check:", "check:1:2", "check:" + "9" * 50, "buy:vip"):
        await harness.click(data)
    assert await db_of(harness).get_payment(1) is None
    alerts = [
        m.text for m in harness.bot.calls if type(m).__name__ == "AnswerCallbackQuery" and m.text is not None
    ]
    assert alerts.count("Счёт не найден") == 4 and alerts.count("Такого тарифа нет") == 1


async def test_platega_webhook_requires_merchant_headers() -> None:
    pg = PlategaProvider("m-1", "s-1")
    body = b'{"id": "tx-1", "amount": 990, "currency": "RUB", "status": "CONFIRMED", "paymentMethod": 2}'
    assert await pg.parse_webhook({"X-MerchantId": "m-1", "X-Secret": "wrong"}, body, {}) is None
    ok = await pg.parse_webhook({"x-merchantid": "m-1", "x-secret": "s-1"}, body, {})
    assert ok == WebhookResult(paid=True, external_id="tx-1", amount=990)
    canceled = await pg.parse_webhook(
        {"X-MerchantId": "m-1", "X-Secret": "s-1"}, body.replace(b"CONFIRMED", b"CANCELED"), {}
    )
    assert canceled is not None and not canceled.paid


async def test_payment_router_falls_back_to_manual_when_unconfigured(harness: Harness) -> None:
    payments = payments_of(harness)
    payments.switch("yookassa")
    assert payments.active_name == "manual"
    with pytest.raises(KeyError):
        payments.switch("nope")


async def test_setup_first_for_new_user_persists_profile(harness: Harness) -> None:
    await harness.send("/setup")
    await harness.click("niche:1")
    await harness.click("tone:expert")
    await harness.send("окрашивание, стрижки")
    assert "Профиль сохранён" in harness.bot.all_texts()
    harness.bot.calls.clear()
    await harness.send("/profile")
    text = harness.bot.all_texts()
    assert "окрашивание, стрижки" in text and "Какая у тебя ниша" not in text


async def test_concurrent_generations_respect_quota(harness: Harness, dispatcher: Dispatcher) -> None:
    await onboard(harness)
    await harness.send(BTN_POST)
    await harness.send("первый")
    await harness.send("второй")
    assert "Осталось бесплатных генераций: 1 из 3" in harness.bot.all_texts()

    harness.bot.calls.clear()
    await asyncio.gather(harness.send("третий"), harness.send("четвёртый"))
    user = await db_of(harness).get_user(1)
    assert user is not None and user.generations_used == 3
    text = harness.bot.all_texts()
    assert "Бесплатные генерации закончились" in text
    assert "Осталось бесплатных генераций: 0 из 3" in text
