from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.prompts import NICHES

BTN_PLAN = "📅 Контент-план"
BTN_POST = "✍️ Написать пост"
BTN_REELS = "🎬 Идеи для Reels"
BTN_DM = "💬 Ответ в Директ"
BTN_PROFILE = "👤 Мой профиль"
BTN_TARIFF = "💎 Тариф"
MENU_BUTTONS = {BTN_PLAN, BTN_POST, BTN_REELS, BTN_DM, BTN_PROFILE, BTN_TARIFF}


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_PLAN), KeyboardButton(text=BTN_POST)],
            [KeyboardButton(text=BTN_REELS), KeyboardButton(text=BTN_DM)],
            [KeyboardButton(text=BTN_PROFILE), KeyboardButton(text=BTN_TARIFF)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие или напишите черновик",
    )


def niches_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i, n in enumerate(NICHES):
        b.button(text=n, callback_data=f"niche:{i}")
    b.button(text="✏️ Другое (напишу сама)", callback_data="niche:other")
    b.adjust(2, 2, 2, 1)
    return b.as_markup()


def tones_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🫶 Подружка", callback_data="tone:friend")
    b.button(text="🎓 Строгий эксперт", callback_data="tone:expert")
    b.button(text="✨ Премиум", callback_data="tone:premium")
    b.adjust(1)
    return b.as_markup()


def plan_days_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="7 дней", callback_data="plan:7")
    b.button(text="14 дней", callback_data="plan:14")
    return b.as_markup()


def reels_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎲 Удиви меня", callback_data="reels:random")
    return b.as_markup()


def paywall_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Базовый — 990 ₽/мес", callback_data="buy:basic")
    b.button(text="Безлимит — 2490 ₽/мес", callback_data="buy:unlimited")
    b.adjust(1)
    return b.as_markup()


def after_result_kb(kind: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Ещё вариант", callback_data=f"again:{kind}")
    return b.as_markup()
