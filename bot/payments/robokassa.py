"""Robokassa (https://docs.robokassa.ru): подписанная ссылка на оплату, ResultURL-вебхук, OpStateExt."""

import hashlib
import logging
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlencode

import httpx

from bot.db import Payment
from bot.payments.base import CreatedPayment, PaymentError, Plan, WebhookResult

log = logging.getLogger(__name__)
PAY_URL = "https://auth.robokassa.ru/Merchant/Index.aspx"
OPSTATE_URL = "https://auth.robokassa.ru/Merchant/WebService/Service.asmx/OpStateExt"
NS = "{http://merchant.roboxchange.com/WebService/}"


class RobokassaProvider:
    name = "robokassa"
    title = "Robokassa (СБП, карты)"
    supports_check = True

    def __init__(
        self,
        login: str,
        password1: str,
        password2: str,
        test: bool = False,
        hash_algo: str = "md5",
        inc_curr_label: str = "",
    ) -> None:
        self._login = login
        self._p1 = password1
        self._p2 = password2
        self._test = test
        self._algo = hash_algo.lower()
        self._inc_curr_label = inc_curr_label
        self.ready = bool(login and password1 and password2)
        if test:
            self.title += " · тест"

    def _sign(self, *parts: object) -> str:
        return hashlib.new(self._algo, ":".join(str(p) for p in parts).encode()).hexdigest()

    async def create(self, payment: Payment, plan: Plan, return_url: str) -> CreatedPayment:
        out_sum = f"{plan.amount:.2f}"
        params = {
            "MerchantLogin": self._login,
            "OutSum": out_sum,
            "InvId": payment.id,
            "Description": f"{plan.title} - Нейро-SMM",
            "SignatureValue": self._sign(self._login, out_sum, payment.id, self._p1),
            "Culture": "ru",
        }
        if self._inc_curr_label:
            params["IncCurrLabel"] = self._inc_curr_label
        if self._test:
            params["IsTest"] = 1
        return CreatedPayment(url=f"{PAY_URL}?{urlencode(params)}", external_id=str(payment.id))

    async def is_paid(self, payment: Payment) -> bool:
        params: dict[str, str | int] = {
            "MerchantLogin": self._login,
            "InvoiceID": payment.id,
            "Signature": self._sign(self._login, payment.id, self._p2),
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(OPSTATE_URL, params=params)
        if resp.status_code >= 400:
            raise PaymentError(f"Robokassa {resp.status_code}: {resp.text[:300]}")
        root = ET.fromstring(resp.text)
        state = root.find(f"{NS}State/{NS}Code")
        return state is not None and state.text == "100"

    async def parse_webhook(
        self, headers: dict[str, str], body: bytes, query: dict[str, str]
    ) -> WebhookResult | None:
        form = {k: v[0] for k, v in parse_qs(body.decode(errors="ignore")).items()}
        params = {**query, **form}
        out_sum, inv_id, signature = (
            params.get("OutSum"),
            params.get("InvId"),
            params.get("SignatureValue", ""),
        )
        if not (out_sum and inv_id and signature):
            return None
        expected = self._sign(out_sum, inv_id, self._p2)
        if expected.lower() != signature.lower():
            log.warning("Robokassa webhook: bad signature for InvId=%s", inv_id)
            return None
        try:
            return WebhookResult(paid=True, payment_id=int(inv_id))
        except ValueError:
            return None

    def webhook_ok_response(self, result: WebhookResult) -> str:
        return f"OK{result.payment_id}"
