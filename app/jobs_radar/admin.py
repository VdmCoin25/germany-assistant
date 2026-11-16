"""Admin-only catalog commands of the Jobs Source Radar (registered only when JOBS_RADAR_ENABLED)."""
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.handlers import IsAdmin
from app.database.models import JobChat
from app.database.repositories.jobs_radar import JobsRadarRepository
from app.jobs_radar.tglinks import parse_chat_link

router = Router(name="jobs_radar")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

_ACTIONS = {"ok": "approved", "no": "rejected"}


def _candidate_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Одобрить", callback_data=f"jr:ok:{chat_id}"),
        InlineKeyboardButton(text="Отклонить", callback_data=f"jr:no:{chat_id}"),
    ]])


def _render(chat: JobChat) -> str:
    name = f"@{chat.username}" if chat.username else "приватная ссылка"
    title = escape(chat.title) if chat.title else "без названия"
    return f"{title}\n{name}\nНайден: {chat.discovered_from}, оценка: {chat.score}"


@router.message(Command("add_job_chat"))
async def cmd_add_job_chat(message: Message, command: CommandObject, session: AsyncSession) -> None:
    link = parse_chat_link(command.args or "")
    if link is None:
        await message.answer("Формат: /add_job_chat <ссылка t.me или @username>")
        return
    chat, created = await JobsRadarRepository(session).add_manual(link)
    await session.commit()
    if created:
        await message.answer("Чат добавлен, статус: approved.")
    else:
        await message.answer(f"Уже есть, статус: {chat.status}.")


@router.message(Command("job_candidates"))
async def cmd_job_candidates(message: Message, session: AsyncSession) -> None:
    chats = await JobsRadarRepository(session).list_candidates(limit=10)
    if not chats:
        await message.answer("Кандидатов нет.")
        return
    for chat in chats:
        await message.answer(_render(chat), reply_markup=_candidate_kb(chat.id))


@router.callback_query(F.data.regexp(r"^jr:(ok|no):\d{1,9}$"))
async def on_candidate(cb: CallbackQuery, session: AsyncSession) -> None:
    _, action, raw_id = cb.data.split(":")
    repo = JobsRadarRepository(session)
    chat = await repo.get(int(raw_id))
    if chat is None:
        await cb.answer("Чат не найден.", show_alert=True)
        return
    if chat.status != "candidate":
        await cb.answer("Уже обработано.", show_alert=True)
        return
    await repo.set_status(chat.id, _ACTIONS[action])
    await session.commit()
    if isinstance(cb.message, Message):
        await cb.message.edit_reply_markup(reply_markup=None)
        await cb.message.answer("Одобрено." if action == "ok" else "Отклонено.")
    await cb.answer()
