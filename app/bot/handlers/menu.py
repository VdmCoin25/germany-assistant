"""Main menu sections. Sections without a connected integration say so honestly."""
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.handlers.start import send_main_menu
from app.bot.keyboards.common import info_topics_kb, links_kb
from app.config import Settings
from app.data.sources_seed import TOPICS
from app.database.models import User
from app.database.repositories.analytics import AnalyticsRepository
from app.database.repositories.sources import SourceRepository
from app.i18n import all_variants, t

router = Router(name="menu")


def menu_button(key: str):
    return F.text.in_(all_variants(key))


@router.message(Command("menu"))
async def cmd_menu(message: Message, lang: str, settings: Settings) -> None:
    await send_main_menu(message, lang, settings)


@router.message(menu_button("menu_documents"))
async def documents(message: Message, user: User, lang: str, analytics: AnalyticsRepository) -> None:
    await analytics.log("feature_used", user.telegram_id, feature="documents")
    await message.answer(t(lang, "section_documents"))


@router.message(menu_button("menu_translator"))
async def translator(message: Message, user: User, lang: str, analytics: AnalyticsRepository) -> None:
    await analytics.log("feature_used", user.telegram_id, feature="translator")
    await message.answer(t(lang, "section_translator"))


@router.message(menu_button("menu_ai"))
async def ai_helper(message: Message, user: User, lang: str, analytics: AnalyticsRepository) -> None:
    await analytics.log("feature_used", user.telegram_id, feature="ai")
    await message.answer(t(lang, "section_ai"))


@router.message(menu_button("menu_jobs"))
async def jobs(message: Message, user: User, lang: str, analytics: AnalyticsRepository,
               sources: SourceRepository) -> None:
    await analytics.log("feature_used", user.telegram_id, feature="jobs")
    await message.answer(t(lang, "section_jobs"), reply_markup=links_kb(await sources.by_topic("jobs"), lang=lang))


@router.message(menu_button("menu_housing"))
async def housing(message: Message, user: User, lang: str, analytics: AnalyticsRepository,
                  sources: SourceRepository) -> None:
    await analytics.log("feature_used", user.telegram_id, feature="housing")
    await message.answer(t(lang, "section_housing"),
                         reply_markup=links_kb(await sources.by_topic("housing"), lang=lang))


@router.message(menu_button("menu_info"))
async def info(message: Message, user: User, lang: str, analytics: AnalyticsRepository) -> None:
    await analytics.log("feature_used", user.telegram_id, feature="info")
    await message.answer(t(lang, "info_title"), reply_markup=info_topics_kb(lang, TOPICS))


def _fmt_date(d: datetime | None, lang: str) -> str:
    return t(lang, "info_checked", date=d.strftime("%d.%m.%Y")) if d else t(lang, "info_not_checked")


@router.callback_query(F.data.startswith("info:"))
async def info_topic(cb: CallbackQuery, lang: str, sources: SourceRepository) -> None:
    key = cb.data.split(":", 1)[1]
    if key == "back":
        await cb.message.edit_text(t(lang, "info_title"), reply_markup=info_topics_kb(lang, TOPICS))
        await cb.answer()
        return
    if key not in TOPICS:
        await cb.answer()
        return
    items = await sources.by_topic(key)
    title = TOPICS[key][1 if lang == "ru" else 0]
    if not items:
        body = t(lang, "info_empty")
    else:
        lines = [f"• {s.title_ru if lang == 'ru' else s.title_uk} — <i>{_fmt_date(s.checked_at, lang)}</i>" for s in items]
        body = "\n".join(lines) + "\n\n" + t(lang, "info_disclaimer")
    await cb.message.edit_text(f"<b>{title}</b>\n\n{body}", reply_markup=links_kb(items, back="info:back", lang=lang))
    await cb.answer()
