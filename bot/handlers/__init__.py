from aiogram import Router

from bot.handlers import admin, generate, onboarding, subscription


def build_router() -> Router:
    root = Router()
    root.include_router(admin.router)
    root.include_router(onboarding.router)
    root.include_router(subscription.router)
    root.include_router(generate.router)
    return root
