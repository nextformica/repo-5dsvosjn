import logging

from bot.config import Settings, settings
from bot.payments.base import CreatedPayment, PaymentError, PaymentProvider, Plan, WebhookResult
from bot.payments.manual import ManualProvider
from bot.payments.platega import PlategaProvider
from bot.payments.robokassa import RobokassaProvider
from bot.payments.yookassa import YooKassaProvider

__all__ = [
    "PLANS",
    "CreatedPayment",
    "PaymentError",
    "PaymentProvider",
    "PaymentRouter",
    "Plan",
    "WebhookResult",
    "build_payment_providers",
]

log = logging.getLogger(__name__)


def plans(days: int) -> dict[str, Plan]:
    return {
        "basic": Plan("basic", "Базовый", 990, days),
        "unlimited": Plan("unlimited", "Безлимит", 2490, days),
    }


PLANS = plans(settings.subscription_days)


def build_payment_providers(s: Settings) -> dict[str, PaymentProvider]:
    return {
        "manual": ManualProvider(s.payment_contact),
        "yookassa": YooKassaProvider(s.yookassa_shop_id, s.yookassa_secret_key, s.yookassa_sbp_only),
        "robokassa": RobokassaProvider(
            s.robokassa_login,
            s.robokassa_password1,
            s.robokassa_password2,
            test=s.robokassa_test,
            hash_algo=s.robokassa_hash,
            inc_curr_label=s.robokassa_inc_curr_label,
        ),
        "platega": PlategaProvider(s.platega_merchant_id, s.platega_secret, s.platega_payment_method),
    }


class PaymentRouter:
    """Активный способ оплаты; переключается на лету командой /pay."""

    def __init__(self, providers: dict[str, PaymentProvider], default: str, return_url: str = "") -> None:
        self.providers = providers
        self.active_name = "manual"
        self.return_url = return_url  # куда вернуть мастера после оплаты — обычно https://t.me/<bot>
        self.switch(default)

    def switch(self, name: str) -> PaymentProvider:
        provider = self.providers.get(name)
        if provider is None:
            raise KeyError(name)
        if not provider.ready:
            log.warning("Payment provider %s is not configured — falling back to manual", name)
            name = "manual"
        self.active_name = name
        return self.providers[name]

    @property
    def active(self) -> PaymentProvider:
        return self.providers[self.active_name]
