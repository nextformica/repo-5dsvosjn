"""Platega (https://docs.platega.io): СБП QR (paymentMethod=2), карты (11), SberPay (14).

Вебхук приходит на Callback URL из личного кабинета.
"""

import json
import logging

import httpx

from bot.db import Payment
from bot.payments.base import CreatedPayment, PaymentError, Plan, WebhookResult, rubles

log = logging.getLogger(__name__)
API = "https://app.platega.io"
METHOD_TITLES = {2: "СБП", 11: "карты", 12: "зарубежные карты", 13: "крипта", 14: "SberPay"}


class PlategaProvider:
    name = "platega"
    supports_check = True

    def __init__(self, merchant_id: str, secret: str, payment_method: int = 2) -> None:
        self._merchant_id = merchant_id
        self._secret = secret
        self._method = payment_method
        self.ready = bool(merchant_id and secret)
        self.title = f"Platega ({METHOD_TITLES.get(payment_method, f'метод {payment_method}')})"

    def _headers(self) -> dict[str, str]:
        return {"X-MerchantId": self._merchant_id, "X-Secret": self._secret}

    async def create(self, payment: Payment, plan: Plan, return_url: str) -> CreatedPayment:
        body = {
            "paymentMethod": self._method,
            "paymentDetails": {"amount": plan.amount, "currency": "RUB"},
            "description": f"{plan.title} — Нейро-SMM, заказ #{payment.id}",
            "return": return_url,
            "failedUrl": return_url,
            "payload": str(payment.id),
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{API}/transaction/process", json=body, headers=self._headers())
        if resp.status_code >= 400:
            raise PaymentError(f"Platega {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if not isinstance(data, dict) or "redirect" not in data or "transactionId" not in data:
            raise PaymentError(f"Platega: unexpected response {resp.text[:200]}")
        return CreatedPayment(url=str(data["redirect"]), external_id=str(data["transactionId"]))

    async def is_paid(self, payment: Payment) -> bool:
        if not payment.external_id:
            return False
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{API}/transaction/{payment.external_id}", headers=self._headers())
        if resp.status_code >= 400:
            raise PaymentError(f"Platega {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if not isinstance(data, dict):
            raise PaymentError(f"Platega: unexpected response {resp.text[:200]}")
        details = data.get("paymentDetails")
        amount = rubles(details.get("amount")) if isinstance(details, dict) else None
        if amount is None:
            amount = rubles(data.get("amount", payment.amount))
        return data.get("status") == "CONFIRMED" and amount == payment.amount

    async def parse_webhook(
        self, headers: dict[str, str], body: bytes, query: dict[str, str]
    ) -> WebhookResult | None:
        # Platega подписывает вебхук теми же заголовками, что и наши запросы к ней.
        h = {k.lower(): v for k, v in headers.items()}
        if not self.ready or h.get("x-merchantid") != self._merchant_id or h.get("x-secret") != self._secret:
            log.warning("Platega webhook: bad credentials")
            return None
        try:
            data = json.loads(body)
        except ValueError:
            return None
        if not isinstance(data, dict) or "id" not in data:
            return None
        return WebhookResult(
            paid=data.get("status") == "CONFIRMED",
            external_id=str(data["id"]),
            amount=rubles(data.get("amount")) if "amount" in data else None,
        )

    def webhook_ok_response(self, result: WebhookResult) -> str:
        return "OK"
