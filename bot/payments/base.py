from dataclasses import dataclass
from typing import Protocol

from bot.db import Payment


@dataclass(frozen=True)
class Plan:
    code: str
    title: str
    amount: int  # рубли
    days: int


@dataclass(frozen=True)
class CreatedPayment:
    url: str
    external_id: str


@dataclass(frozen=True)
class WebhookResult:
    """Что платёжка сообщила вебхуком: наш payment_id или её external_id и факт оплаты."""

    paid: bool
    payment_id: int | None = None
    external_id: str | None = None


class PaymentError(Exception):
    pass


class PaymentProvider(Protocol):
    name: str
    title: str
    ready: bool
    supports_check: bool  # можно ли спросить статус у платёжки (кнопка «Я оплатила»)

    async def create(self, payment: Payment, plan: Plan, return_url: str) -> CreatedPayment: ...

    async def is_paid(self, payment: Payment) -> bool: ...

    async def parse_webhook(
        self, headers: dict[str, str], body: bytes, query: dict[str, str]
    ) -> WebhookResult | None:
        """None — подпись/секрет не сошлись, запрос игнорируем."""
        ...

    def webhook_ok_response(self, result: WebhookResult) -> str: ...
