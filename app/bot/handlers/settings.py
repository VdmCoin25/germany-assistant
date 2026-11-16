"""Settings, profile, privacy, data export and deletion (DSGVO Art. 15/17/20)."""
import json

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message, ReplyKeyboardRemove

from app.bot.handlers.menu import menu_button
from app.bot.handlers.start import ask_land, send_main_menu
from app.bot.keyboards.common import delete_confirm_kb, language_kb, profile_kb, settings_kb
from app.config import Settings
from app.data.regions import LANDS
from app.database.models import User
from app.database.repositories.analytics import AnalyticsRepository, user_hash
from app.database.repositories.users import UserRepository
from app.i18n import t

router = Router(name="settings")


def profile_text(user: User, lang: str) -> str:
    dash = t(lang, "not_set")
    level = user.german_level
    if level == "C1":
        level = t(lang, "level_C1")
    return t(
        lang, "profile_view",
        language=t(user.language, "language_name") if user.language else dash,
        land=LANDS.get(user.land or "", dash),
        city=user.city or dash,
        level=level or dash,
        goal=t(lang, f"goal_{user.goal}") if user.goal else dash,
        status=t(lang, f"status_{user.residence_status}") if user.residence_status else dash,
        broadcast=t(lang, "yes" if user.broadcast_consent else "no"),
    )


@router.message(Command("settings"))
@router.message(menu_button("menu_settings"))
async def show_settings(message: Message, user: User, lang: str) -> None:
    await message.answer(t(lang, "settings_title"), reply_markup=settings_kb(lang, user.broadcast_consent))


@router.message(menu_button("menu_profile"))
async def show_profile(message: Message, user: User, lang: str) -> None:
    await message.answer(profile_text(user, lang), reply_markup=profile_kb(lang))


@router.callback_query(F.data == "set:lang")
async def choose_lang(cb: CallbackQuery, settings: Settings) -> None:
    await cb.message.edit_reply_markup(reply_markup=language_kb(settings.languages, prefix="setlang"))
    await cb.answer()


@router.callback_query(F.data.startswith("setlang:"))
async def set_lang(cb: CallbackQuery, user: User, users: UserRepository, settings: Settings,
                   analytics: AnalyticsRepository) -> None:
    code = cb.data.split(":", 1)[1]
    if code not in settings.languages:
        await cb.answer()
        return
    await users.update_profile(user, language=code)
    await analytics.log("language_selected", user.telegram_id, feature=code)
    await cb.message.edit_text(t(code, "language_changed"))
    await send_main_menu(cb.message, code, settings)
    await cb.answer()


@router.callback_query(F.data == "set:edit")
async def edit_profile(cb: CallbackQuery, state: FSMContext, lang: str) -> None:
    await cb.answer()
    await ask_land(cb.message, state, lang)


@router.callback_query(F.data == "set:broadcast")
async def toggle_broadcast(cb: CallbackQuery, user: User, users: UserRepository, lang: str) -> None:
    await users.update_profile(user, broadcast_consent=not user.broadcast_consent)
    await cb.message.edit_reply_markup(reply_markup=settings_kb(lang, user.broadcast_consent))
    await cb.answer(t(lang, "broadcast_changed"))


@router.message(Command("privacy"))
async def cmd_privacy(message: Message, lang: str, settings: Settings) -> None:
    await message.answer(t(lang, "privacy_text", bot_name=settings.bot_name))


@router.callback_query(F.data == "set:privacy")
async def cb_privacy(cb: CallbackQuery, lang: str, settings: Settings) -> None:
    await cb.message.answer(t(lang, "privacy_text", bot_name=settings.bot_name))
    await cb.answer()


async def _send_export(message: Message, user: User, users: UserRepository, lang: str) -> None:
    payload = json.dumps(await users.export(user), ensure_ascii=False, indent=2).encode()
    await message.answer_document(BufferedInputFile(payload, filename="my_data.json"), caption=t(lang, "export_caption"))


@router.message(Command("export_my_data"))
async def cmd_export(message: Message, user: User, users: UserRepository, lang: str) -> None:
    await _send_export(message, user, users, lang)


@router.callback_query(F.data == "set:export")
async def cb_export(cb: CallbackQuery, user: User, users: UserRepository, lang: str) -> None:
    await _send_export(cb.message, user, users, lang)
    await cb.answer()


@router.message(Command("delete_my_data"))
async def cmd_delete(message: Message, lang: str) -> None:
    await message.answer(t(lang, "delete_confirm"), reply_markup=delete_confirm_kb(lang))


@router.callback_query(F.data == "set:delete")
async def cb_delete(cb: CallbackQuery, lang: str) -> None:
    await cb.message.answer(t(lang, "delete_confirm"), reply_markup=delete_confirm_kb(lang))
    await cb.answer()


@router.callback_query(F.data == "del:yes")
async def delete_yes(cb: CallbackQuery, state: FSMContext, user: User, users: UserRepository,
                     lang: str, settings: Settings) -> None:
    await state.clear()
    await users.delete_all(user, user_hash(user.telegram_id, settings.analytics_salt))
    await cb.message.edit_text(t(lang, "deleted"))
    await cb.message.answer("🗑", reply_markup=ReplyKeyboardRemove())
    await cb.answer()


@router.callback_query(F.data == "del:no")
async def delete_no(cb: CallbackQuery, lang: str) -> None:
    await cb.message.edit_text(t(lang, "cancelled"))
    await cb.answer()
