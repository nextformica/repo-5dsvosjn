import html

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.db import Database
from bot.keyboards import BTN_PROFILE, MENU_BUTTONS, main_menu, niches_kb, tones_kb
from bot.prompts import NICHES, TONES

router = Router()

PLAIN_TEXT = F.text & ~F.text.startswith("/") & ~F.text.in_(MENU_BUTTONS)


class Onboarding(StatesGroup):
    niche = State()
    niche_custom = State()
    tone = State()
    services = State()


WELCOME = (
    "Привет! Я твой карманный SMM-менеджер для бьюти-мастеров 💅\n\n"
    "Пишу посты, собираю контент-план, придумываю Reels и подсказываю, "
    "что ответить клиенту в Директе — в твоём стиле.\n\n"
    f"Первые {settings.free_generations} генерации — бесплатно.\n\n"
    "Давай настроим профиль за 30 секунд. <b>Какая у тебя ниша?</b>"
)


async def start_onboarding(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Onboarding.niche)
    await message.answer(WELCOME, reply_markup=niches_kb())


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user is not None
    user = await db.get_or_create_user(message.from_user.id, message.from_user.username)
    if user.onboarded:
        await state.clear()
        await message.answer("С возвращением! Что делаем?", reply_markup=main_menu())
        return
    await start_onboarding(message, state)


@router.message(Command("profile"))
@router.message(F.text == BTN_PROFILE)
async def cmd_profile(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user is not None
    user = await db.get_or_create_user(message.from_user.id, message.from_user.username)
    if not user.onboarded:
        await start_onboarding(message, state)
        return
    tone_title = TONES.get(user.tone or "", user.tone or "—").split(" — ")[0]
    await message.answer(
        f"<b>Твой профиль</b>\n\n"
        f"Ниша: {html.escape(user.niche or '—')}\n"
        f"Tone of voice: {tone_title}\n"
        f"Услуги: {html.escape(user.services or '—')}\n\n"
        "Хочешь изменить — нажми /setup",
        reply_markup=main_menu(),
    )


@router.message(Command("setup"))
async def cmd_setup(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Onboarding.niche)
    await message.answer("<b>Какая у тебя ниша?</b>", reply_markup=niches_kb())


@router.callback_query(Onboarding.niche, F.data.startswith("niche:"))
async def pick_niche(cb: CallbackQuery, state: FSMContext) -> None:
    assert cb.data is not None and isinstance(cb.message, Message)
    value = cb.data.split(":", 1)[1]
    if value == "other":
        await state.set_state(Onboarding.niche_custom)
        await cb.message.edit_text("Напиши свою нишу одной строкой, например: «Ламинирование ресниц».")
        await cb.answer()
        return
    niche = NICHES[int(value)]
    await state.update_data(niche=niche)
    await cb.message.edit_text(f"Ниша: <b>{niche}</b> ✅")
    await ask_tone(cb.message, state)
    await cb.answer()


@router.message(Onboarding.niche, PLAIN_TEXT)
@router.message(Onboarding.niche_custom, PLAIN_TEXT)
async def custom_niche(message: Message, state: FSMContext) -> None:
    assert message.text is not None
    await state.update_data(niche=message.text.strip()[:100])
    await ask_tone(message, state)


async def ask_tone(message: Message, state: FSMContext) -> None:
    await state.set_state(Onboarding.tone)
    await message.answer(
        "<b>Как ты общаешься с клиентками?</b>\n\n"
        "🫶 <b>Подружка</b> — тепло, на «ты», с юмором\n"
        "🎓 <b>Строгий эксперт</b> — на «вы», факты и польза\n"
        "✨ <b>Премиум</b> — сдержанно, эстетично, коротко",
        reply_markup=tones_kb(),
    )


@router.message(Onboarding.tone, PLAIN_TEXT)
async def tone_text(message: Message) -> None:
    await message.answer("Выбери стиль кнопкой ниже 👇", reply_markup=tones_kb())


@router.callback_query(Onboarding.tone, F.data.startswith("tone:"))
async def pick_tone(cb: CallbackQuery, state: FSMContext) -> None:
    assert cb.data is not None and isinstance(cb.message, Message)
    tone = cb.data.split(":", 1)[1]
    await state.update_data(tone=tone)
    await state.set_state(Onboarding.services)
    await cb.message.edit_text(f"Tone of voice: <b>{TONES[tone].split(' — ')[0]}</b> ✅")
    await cb.message.answer(
        "<b>Какие услуги продвигаем в первую очередь?</b>\n\n"
        "Перечисли через запятую, например: «наращивание, френч, укрепление гелем, педикюр»."
    )
    await cb.answer()


@router.message(Onboarding.services, PLAIN_TEXT)
async def set_services(message: Message, state: FSMContext, db: Database) -> None:
    assert message.text is not None and message.from_user is not None
    data = await state.get_data()
    await db.save_profile(
        user_id=message.from_user.id,
        niche=data["niche"],
        tone=data["tone"],
        services=message.text.strip()[:300],
    )
    await state.clear()
    await message.answer(
        "Готово! Профиль сохранён 🎉\n\n"
        "Теперь просто напиши мне пару слов о сегодняшней работе (или отправь голосовое) — "
        "и я превращу это в пост. Или выбери действие в меню 👇",
        reply_markup=main_menu(),
    )
