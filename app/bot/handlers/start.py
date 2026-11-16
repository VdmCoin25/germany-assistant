"""/start, language choice and the short onboarding (also reused for 'edit profile')."""
from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.common import (
    city_skip_kb,
    goals_kb,
    lands_kb,
    language_kb,
    levels_kb,
    main_menu,
    status_kb,
    webapp_kb,
)
from app.config import Settings
from app.data.regions import GERMAN_LEVELS, GOALS, LANDS, STATUSES
from app.database.models import User
from app.database.repositories.analytics import AnalyticsRepository
from app.database.repositories.users import UserRepository
from app.i18n import t

router = Router(name="start")


class Reg(StatesGroup):
    language = State()
    land = State()
    city = State()
    level = State()
    goal = State()
    status = State()


async def send_main_menu(message: Message, lang: str, settings: Settings, key: str = "menu_hint") -> None:
    await message.answer(t(lang, key, bot_name=settings.bot_name), reply_markup=main_menu(lang))
    if settings.webapp_url:
        await message.answer(t(lang, "open_app_text"), reply_markup=webapp_kb(lang, settings.webapp_url))


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: User, lang: str,
                    analytics: AnalyticsRepository, settings: Settings) -> None:
    await state.clear()
    await analytics.log("bot_started", user.telegram_id)
    if user.is_registered:
        await send_main_menu(message, lang, settings, "welcome_back")
        return
    await state.set_state(Reg.language)
    await message.answer(t(None, "choose_language"), reply_markup=language_kb(settings.languages))


@router.callback_query(Reg.language, F.data.startswith("lang:"))
async def on_language(cb: CallbackQuery, state: FSMContext, user: User, users: UserRepository,
                      analytics: AnalyticsRepository, settings: Settings) -> None:
    code = cb.data.split(":", 1)[1]
    if code not in settings.languages:
        await cb.answer()
        return
    await users.update_profile(user, language=code)
    await analytics.log("language_selected", user.telegram_id, feature=code)
    await cb.message.edit_text(t(code, "welcome_new", bot_name=settings.bot_name))
    await ask_land(cb.message, state, code)
    await cb.answer()


async def ask_land(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(Reg.land)
    await message.answer(t(lang, "ask_land"), reply_markup=lands_kb(lang))


@router.callback_query(Reg.land, F.data.startswith("land:"))
async def on_land(cb: CallbackQuery, state: FSMContext, user: User, users: UserRepository, lang: str) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "skip" and code not in LANDS:
        await cb.answer()
        return
    await users.update_profile(user, land=None if code == "skip" else code)
    await state.set_state(Reg.city)
    await cb.message.edit_text(t(lang, "ask_city"), reply_markup=city_skip_kb(lang))
    await cb.answer()


def clean_city(text: str | None) -> str | None:
    if not text:
        return None
    value = " ".join(text.split())
    if not value or len(value) > 80 or value.startswith("/"):
        return None
    return value


@router.message(Reg.city, F.text)
async def on_city_text(message: Message, state: FSMContext, user: User, users: UserRepository, lang: str) -> None:
    city = clean_city(message.text)
    if city is None:
        await message.answer(t(lang, "city_invalid"), reply_markup=city_skip_kb(lang))
        return
    await users.update_profile(user, city=city)
    await state.set_state(Reg.level)
    await message.answer(t(lang, "ask_level"), reply_markup=levels_kb(lang))


@router.callback_query(Reg.city, F.data == "city:skip")
async def on_city_skip(cb: CallbackQuery, state: FSMContext, user: User, users: UserRepository, lang: str) -> None:
    await users.update_profile(user, city=None)
    await state.set_state(Reg.level)
    await cb.message.edit_text(t(lang, "ask_level"), reply_markup=levels_kb(lang))
    await cb.answer()


@router.callback_query(Reg.level, F.data.startswith("lvl:"))
async def on_level(cb: CallbackQuery, state: FSMContext, user: User, users: UserRepository, lang: str) -> None:
    level = cb.data.split(":", 1)[1]
    if level not in GERMAN_LEVELS:
        await cb.answer()
        return
    await users.update_profile(user, german_level=level)
    await state.set_state(Reg.goal)
    await cb.message.edit_text(t(lang, "ask_goal"), reply_markup=goals_kb(lang))
    await cb.answer()


@router.callback_query(Reg.goal, F.data.startswith("goal:"))
async def on_goal(cb: CallbackQuery, state: FSMContext, user: User, users: UserRepository, lang: str) -> None:
    goal = cb.data.split(":", 1)[1]
    if goal not in GOALS:
        await cb.answer()
        return
    await users.update_profile(user, goal=goal)
    await state.set_state(Reg.status)
    await cb.message.edit_text(t(lang, "ask_status"), reply_markup=status_kb(lang))
    await cb.answer()


@router.callback_query(Reg.status, F.data.startswith("st:"))
async def on_status(cb: CallbackQuery, state: FSMContext, user: User, users: UserRepository, lang: str,
                    analytics: AnalyticsRepository, settings: Settings) -> None:
    status = cb.data.split(":", 1)[1]
    if status != "skip" and status not in STATUSES:
        await cb.answer()
        return
    await users.update_profile(user, residence_status=None if status == "skip" else status)
    first_time = not user.is_registered
    user.is_registered = True
    if first_time:
        await analytics.log("registration_completed", user.telegram_id)
    await state.clear()
    await cb.message.edit_text(t(lang, "registration_done", bot_name=settings.bot_name))
    await send_main_menu(cb.message, lang, settings)
    await cb.answer()
