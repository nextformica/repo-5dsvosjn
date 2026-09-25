"""ЮKassa (https://yookassa.ru/developers/api): платёж с redirect-подтверждением, СБП/карта."""

import json
import logging
import uuid
from typing import Any

import httpx

from bot.db import Payment
from bot.payments.base import CreatedPayment, PaymentError, Plan, WebhookResult, rubles

log = logging.getLogger(__name__)
API = "https://api.yookassa.ru/v3"


class YooKassaProvider:
    name = "yookassa"
    title = "ЮKassa (СБП, карты)"
    supports_check = True

    def __init__(self, shop_id: str, secret_key: str, sbp_only: bool = False) -> None:
        self._auth = (shop_id, secret_key)
        self._sbp_only = sbp_only
        self.ready = bool(shop_id and secret_key)
        if sbp_only:
            self.title = "ЮKassa (только СБП)"

    async def create(self, payment: Payment, plan: Plan, return_url: str) -> CreatedPayment:
        body: dict[str, Any] = {
            "amount": {"value": f"{plan.amount:.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "description": f"{plan.title} — Нейро-SMM, заказ #{payment.id}",
            "metadata": {"payment_id": str(payment.id), "user_id": str(payment.user_id)},
        }
        if self._sbp_only:
            body["payment_method_data"] = {"type": "sbp"}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{API}/payments",
                json=body,
                auth=self._auth,
                headers={"Idempotence-Key": str(uuid.uuid4())},
            )
        if resp.status_code >= 400:
            raise PaymentError(f"YooKassa {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return CreatedPayment(url=data["confirmation"]["confirmation_url"], external_id=data["id"])

    async def _fetch(self, external_id: str) -> tuple[str, int | None]:
        """(status, сумма в рублях) платежа по API ЮKassa."""
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{API}/payments/{external_id}", auth=self._auth)
        if resp.status_code >= 400:
            raise PaymentError(f"YooKassa {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if not isinstance(data, dict):
            raise PaymentError(f"YooKassa: unexpected response {resp.text[:200]}")
        amount = data.get("amount")
        return str(data.get("status", "")), rubles(amount.get("value")) if isinstance(amount, dict) else None

    async def is_paid(self, payment: Payment) -> bool:
        if not payment.external_id:
            return False
        status, amount = await self._fetch(payment.external_id)
        return status == "succeeded" and amount == payment.amount

    async def parse_webhook(
        self, headers: dict[str, str], body: bytes, query: dict[str, str]
    ) -> WebhookResult | None:
        # Уведомления ЮKassa не подписаны — доверяем только статусу, перепрошенному по API.
        if not self.ready:
            return None
        try:
            data = json.loads(body)
            external_id = str(data["object"]["id"])
        except (ValueError, KeyError, TypeError):
            return None
        try:
            status, amount = await self._fetch(external_id)
        except (PaymentError, httpx.HTTPError, ValueError):
            log.exception("YooKassa webhook: cannot verify %s", external_id)
            return None
        return WebhookResult(paid=status == "succeeded", external_id=external_id, amount=amount)

    def webhook_ok_response(self, result: WebhookResult) -> str:
        return "OK"
