"""/help, fallbacks and the central error handler."""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, ErrorEvent, Message

from app.bot.keyboards.common import main_menu
from app.config import Settings
from app.database.models import User
from app.i18n import t

log = logging.getLogger(__name__)

router = Router(name="common")
fallback_router = Router(name="fallback")


@router.message(Command("help"))
async def cmd_help(message: Message, lang: str, settings: Settings) -> None:
    await message.answer(t(lang, "help_text", bot_name=settings.bot_name))


@fallback_router.message()
async def fallback_message(message: Message, user: User | None, lang: str) -> None:
    if not user or not user.is_registered:
        await message.answer(t(lang, "need_start"))
        return
    await message.answer(t(lang, "unknown"), reply_markup=main_menu(lang))


@fallback_router.callback_query()
async def fallback_callback(cb: CallbackQuery) -> None:
    await cb.answer()


async def on_error(event: ErrorEvent) -> bool:
    # Log only the exception type and update id — never message text or user data.
    log.error("Unhandled %s in update %s", type(event.exception).__name__, event.update.update_id,
              exc_info=event.exception)
    target = event.update.message or (event.update.callback_query and event.update.callback_query.message)
    if target:
        try:
            await target.answer(t(None, "error_generic"))
        except Exception:  # noqa: BLE001 — best effort
            pass
    return True
