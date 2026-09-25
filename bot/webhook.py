"""HTTP-сервер для вебхуков платёжек: POST /webhook/<provider>."""

import logging

from aiogram import Bot
from aiohttp import web

from bot.db import Database
from bot.payments import PaymentRouter
from bot.payments.service import handle_webhook

log = logging.getLogger(__name__)


def build_app(db: Database, payments: PaymentRouter, bot: Bot | None) -> web.Application:
    app = web.Application()

    async def webhook(request: web.Request) -> web.Response:
        provider = payments.providers.get(request.match_info["provider"])
        if provider is None or not provider.ready or provider.name == "manual":
            raise web.HTTPNotFound()
        body = await request.read()
        result = await provider.parse_webhook(dict(request.headers), body, dict(request.query))
        if result is None:
            raise web.HTTPForbidden(text="bad signature")
        await handle_webhook(provider, result, db, bot)
        return web.Response(text=provider.webhook_ok_response(result))

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_post("/webhook/{provider}", webhook)
    app.router.add_get("/health", health)
    return app


async def start_server(app: web.Application, host: str, port: int) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    log.info("Webhook server on http://%s:%s/webhook/<provider>", host, port)
    return runner
