import html
import io
import logging

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import prompts
from bot.config import settings
from bot.db import Database
from bot.handlers.onboarding import start_onboarding
from bot.handlers.subscription import PAYWALL, remaining_text
from bot.keyboards import (
    BTN_DM,
    BTN_PLAN,
    BTN_POST,
    BTN_REELS,
    after_result_kb,
    main_menu,
    paywall_kb,
    plan_days_kb,
    reels_kb,
)
from bot.llm import LLM, TranscriptionUnavailable

log = logging.getLogger(__name__)
router = Router()

MAX_MESSAGE_LEN = 4000


class Gen(StatesGroup):
    post_input = State()
    reels_input = State()
    dm_input = State()


def build_prompt(kind: str, user_input: str) -> str:
    if kind == "post":
        return prompts.POST.format(user_input=user_input)
    if kind == "plan":
        return prompts.CONTENT_PLAN.format(days=user_input)
    if kind == "reels":
        return prompts.REELS.format(user_input=user_input or "на усмотрение SMM-менеджера")
    if kind == "dm":
        return prompts.DM_REPLY.format(user_input=user_input)
    raise ValueError(kind)


async def run_generation(
    message: Message, state: FSMContext, db: Database, llm: LLM, kind: str, user_input: str
) -> None:
    """Общий пайплайн: проверка лимита → LLM → лог → ответ."""
    assert message.from_user is not None
    user = await db.get_or_create_user(message.from_user.id, message.from_user.username)
    if not user.onboarded:
        await start_onboarding(message, state)
        return
    if not await db.reserve_generation(user.user_id, settings.free_generations):
        await message.answer(PAYWALL, reply_markup=paywall_kb())
        return

    status = await message.answer("⏳ Пишу…")
    assert message.bot is not None
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        result = await llm.generate(prompts.system_prompt(user), build_prompt(kind, user_input))
    except Exception:
        log.exception("LLM generation failed")
        await db.refund_generation(user.user_id)
        await status.edit_text("Что-то пошло не так, попробуй ещё раз через минуту 🙏")
        return

    await db.log_generation(user.user_id, kind, user_input, result)
    user = await db.get_or_create_user(user.user_id, user.username)
    await state.update_data(last_kind=kind, last_input=user_input)

    chunks = [result[i : i + MAX_MESSAGE_LEN] for i in range(0, len(result), MAX_MESSAGE_LEN)] or ["(пусто)"]
    await status.edit_text(chunks[0], parse_mode=None)
    for chunk in chunks[1:]:
        await message.answer(chunk, parse_mode=None)
    await message.answer(remaining_text(user), reply_markup=after_result_kb(kind))


# --- Кнопки меню (регистрируются первыми, чтобы работать из любого состояния) ---


@router.message(F.text == BTN_PLAN)
async def plan_start(message: Message, state: FSMContext) -> None:
    await state.set_state(None)
    await message.answer("На сколько дней собрать план?", reply_markup=plan_days_kb())


@router.message(F.text == BTN_POST)
async def post_start(message: Message, state: FSMContext) -> None:
    await state.set_state(Gen.post_input)
    await message.answer(
        "Расскажи, о чём пост — текстом или голосовым. Можно коротко и криво, я разберусь:\n\n"
        "<i>«сделала сегодня френч, клиентка грызла ногти, мы нарастили, вышло супер»</i>"
    )


@router.message(F.text == BTN_REELS)
async def reels_start(message: Message, state: FSMContext) -> None:
    await state.set_state(Gen.reels_input)
    await message.answer(
        "Про что хочешь снять Reels? Напиши тему или услугу — или нажми «Удиви меня».",
        reply_markup=reels_kb(),
    )


@router.message(F.text == BTN_DM)
async def dm_start(message: Message, state: FSMContext) -> None:
    await state.set_state(Gen.dm_input)
    await message.answer(
        "Перешли или скопируй сообщение клиента, на которое нужно ответить:\n\n"
        "<i>«А почему так дорого? У другого мастера дешевле»</i>"
    )


# --- Контент-план -----------------------------------------------------------


@router.callback_query(F.data.startswith("plan:"))
async def plan_pick(cb: CallbackQuery, state: FSMContext, db: Database, llm: LLM) -> None:
    assert cb.data is not None and isinstance(cb.message, Message)
    days = cb.data.split(":", 1)[1]
    await cb.message.edit_text(f"Контент-план на {days} дней")
    await cb.answer()
    await run_generation(_as_user_message(cb), state, db, llm, "plan", days)


# --- Пост -------------------------------------------------------------------


@router.message(Gen.post_input, F.text)
async def post_text(message: Message, state: FSMContext, db: Database, llm: LLM) -> None:
    assert message.text is not None
    await state.set_state(None)
    await run_generation(message, state, db, llm, "post", message.text)


@router.message(F.voice)
async def post_voice(message: Message, state: FSMContext, db: Database, llm: LLM) -> None:
    assert message.voice is not None and message.bot is not None
    await state.set_state(None)
    status = await message.answer("🎧 Слушаю голосовое…")
    buf = io.BytesIO()
    await message.bot.download(message.voice, destination=buf)
    try:
        text = await llm.transcribe(buf.getvalue(), "voice.ogg")
    except TranscriptionUnavailable:
        await status.edit_text("Распознавание голоса в этой конфигурации недоступно, напиши текстом 🙏")
        return
    except Exception:
        log.exception("Transcription failed")
        await status.edit_text("Не смогла разобрать голосовое, напиши текстом 🙏")
        return
    await status.edit_text(f"Услышала: <i>{html.escape(text)}</i>")
    await run_generation(message, state, db, llm, "post", text)


# --- Reels ------------------------------------------------------------------


@router.message(Gen.reels_input, F.text)
async def reels_text(message: Message, state: FSMContext, db: Database, llm: LLM) -> None:
    assert message.text is not None
    await state.set_state(None)
    await run_generation(message, state, db, llm, "reels", message.text)


@router.callback_query(F.data == "reels:random")
async def reels_random(cb: CallbackQuery, state: FSMContext, db: Database, llm: LLM) -> None:
    assert isinstance(cb.message, Message)
    await state.set_state(None)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer()
    await run_generation(_as_user_message(cb), state, db, llm, "reels", "")


# --- Директ -----------------------------------------------------------------


@router.message(Gen.dm_input, F.text)
async def dm_text(message: Message, state: FSMContext, db: Database, llm: LLM) -> None:
    assert message.text is not None
    await state.set_state(None)
    await run_generation(message, state, db, llm, "dm", message.text)


# --- Ещё вариант / fallback ---------------------------------------------------


@router.callback_query(F.data.startswith("again:"))
async def again(cb: CallbackQuery, state: FSMContext, db: Database, llm: LLM) -> None:
    assert isinstance(cb.message, Message)
    data = await state.get_data()
    kind, user_input = data.get("last_kind"), data.get("last_input")
    await cb.answer()
    if kind is None or user_input is None:
        await cb.message.answer("Не помню прошлый запрос — выбери действие в меню", reply_markup=main_menu())
        return
    await run_generation(_as_user_message(cb), state, db, llm, kind, user_input)


@router.message(F.text, ~F.text.startswith("/"))
async def free_text(message: Message, state: FSMContext, db: Database, llm: LLM) -> None:
    """Любой текст вне сценария считаем черновиком поста."""
    assert message.text is not None
    await run_generation(message, state, db, llm, "post", message.text)


def _as_user_message(cb: CallbackQuery) -> Message:
    """Сообщение из callback принадлежит боту; подменяем from_user на нажавшего."""
    assert isinstance(cb.message, Message)
    return cb.message.model_copy(update={"from_user": cb.from_user})
