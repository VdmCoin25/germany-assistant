"""Admin commands. Only Telegram IDs listed in ADMIN_IDS can use them.

Admins see aggregates only — never document contents or conversations.
"""
from aiogram import Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.repositories.analytics import AnalyticsRepository
from app.database.repositories.users import UserRepository


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, settings: Settings) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and user.id in settings.admin_ids)


router = Router(name="admin")
router.message.filter(IsAdmin())

ADMIN_HELP = (
    "<b>Admin</b>\n"
    "/stats — пользователи и активность за 7 дней\n"
    "/block &lt;telegram_id&gt; — заблокировать\n"
    "/unblock &lt;telegram_id&gt; — разблокировать\n"
    "/moderate — очередь модерации биржи работы\n"
    "/grant_employer &lt;telegram_id&gt; &lt;дней&gt; — продлить доступ работодателю"
)


RADAR_HELP = (
    "\n/add_job_chat &lt;ссылка&gt; — добавить чат в радар вакансий\n"
    "/job_candidates — кандидаты в чаты радара\n"
    "/job_sources — топ источников радара\n"
    "/job_agencies — топ агентств радара"
)


@router.message(Command("admin"))
async def admin_help(message: Message, settings: Settings) -> None:
    await message.answer(ADMIN_HELP + (RADAR_HELP if settings.jobs_radar_enabled else ""))


async def _radar_block(session: AsyncSession) -> str:
    from app.database.models import utcnow
    from app.database.repositories.jobs_radar import JobsRadarRepository

    r = await JobsRadarRepository(session).radar_stats(utcnow())
    chats = ", ".join(f"{k}: {v}" for k, v in sorted(r["chats_by_status"].items())) or "—"
    sigs = "\n".join(f"  {k}: {v}" for k, v in sorted(r["signals_7d"].items())) or "  —"
    return (
        f"\n\n<b>Радар вакансий</b>\nЧаты: {chats}\nАктивные чаты: {r['active_chats']}\n"
        f"Сигналы за 7 дней:\n{sigs}\nАгентства: {r['agencies_total']} (новых за 7 дней: {r['agencies_new_7d']})"
    )


@router.message(Command("stats"))
async def stats(
    message: Message, users: UserRepository, analytics: AnalyticsRepository,
    settings: Settings, session: AsyncSession,
) -> None:
    s = await users.stats()
    events = await analytics.summary(7)
    langs = ", ".join(f"{k}: {v}" for k, v in s["by_language"].items()) or "—"
    ev = "\n".join(f"  {k}: {v}" for k, v in sorted(events.items())) or "  —"
    text = (
        f"<b>Пользователи</b>\nВсего: {s['total']}\nЗарегистрированы: {s['registered']}\n"
        f"Активны за 7 дней: {s['active_7d']}\nЯзыки: {langs}\n\n<b>События за 7 дней</b>\n{ev}"
    )
    if settings.jobs_radar_enabled:
        text += await _radar_block(session)
    await message.answer(text)


async def _set_block(message: Message, command: CommandObject, users: UserRepository, blocked: bool) -> None:
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer("Укажите telegram_id числом.")
        return
    ok = await users.set_blocked(int(arg), blocked)
    await message.answer("Готово." if ok else "Пользователь не найден.")


@router.message(Command("block"))
async def block(message: Message, command: CommandObject, users: UserRepository) -> None:
    await _set_block(message, command, users, True)


@router.message(Command("unblock"))
async def unblock(message: Message, command: CommandObject, users: UserRepository) -> None:
    await _set_block(message, command, users, False)
