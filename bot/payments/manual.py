from bot.db import Payment
from bot.payments.base import CreatedPayment, Plan, WebhookResult


class ManualProvider:
    """Без эквайринга: мастер пишет в личку, админ включает доступ /grant."""

    name = "manual"
    title = "Вручную (перевод + /grant)"
    ready = True
    supports_check = False

    def __init__(self, contact: str) -> None:
        self.contact = contact

    async def create(self, payment: Payment, plan: Plan, return_url: str) -> CreatedPayment:
        return CreatedPayment(url="", external_id=f"manual-{payment.id}")

    async def is_paid(self, payment: Payment) -> bool:
        return False

    async def parse_webhook(
        self, headers: dict[str, str], body: bytes, query: dict[str, str]
    ) -> WebhookResult | None:
        return None

    def webhook_ok_response(self, result: WebhookResult) -> str:
        return "OK"
