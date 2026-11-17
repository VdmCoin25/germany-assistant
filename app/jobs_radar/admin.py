"""Admin-only catalog commands of the Jobs Source Radar (registered only when JOBS_RADAR_ENABLED)."""
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.handlers import IsAdmin
from app.database.models import JobAgency, JobChat
from app.database.repositories.jobs_radar import JobsRadarRepository
from app.jobs_radar.export import agencies_csv, sources_csv
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


_CHUNK = 3500


def _csv_kb(kind: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="CSV", callback_data=f"jr:csv:{kind}")]])


def _chunks(lines: list[str]) -> list[str]:
    out, cur = [], ""
    for line in lines:
        if cur and len(cur) + len(line) + 1 > _CHUNK:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


def _source_line(n: int, c: JobChat) -> str:
    name = escape(c.title) if c.title else (f"@{c.username}" if c.username else "приватная ссылка")
    members = c.members if c.members is not None else "?"
    parts = [c.status, f"{members} уч.", f"{c.posts_per_day_7d:g}/день", f"реклама: {c.ads_allowed}"]
    if c.city:
        parts.append(escape(c.city))
    parts.append(f"оценка {c.score:g}")
    return f"{n}. {name} — " + ", ".join(parts)


def _agency_line(n: int, a: JobAgency) -> str:
    contacts = [escape(v) for v in (a.website, a.email, a.phone_norm) if v]
    seen = a.last_seen_at.date().isoformat() if a.last_seen_at else "—"
    tail = f" [{', '.join(contacts)}]" if contacts else ""
    return f"{n}. {escape(a.name)}{tail} — сигналов: {a.signals_count}, последний: {seen}"


async def _send_list(message: Message, lines: list[str], kind: str) -> None:
    pages = _chunks(lines)
    for i, page in enumerate(pages):
        last = i == len(pages) - 1
        await message.answer(page, reply_markup=_csv_kb(kind) if last else None)


@router.message(Command("job_sources"))
async def cmd_job_sources(message: Message, session: AsyncSession) -> None:
    chats = await JobsRadarRepository(session).top_sources(limit=50)
    if not chats:
        await message.answer("Пусто.")
        return
    await _send_list(message, [_source_line(i, c) for i, c in enumerate(chats, 1)], "sources")


@router.message(Command("job_agencies"))
async def cmd_job_agencies(message: Message, session: AsyncSession) -> None:
    agencies = await JobsRadarRepository(session).top_agencies(limit=30)
    if not agencies:
        await message.answer("Пусто.")
        return
    await _send_list(message, [_agency_line(i, a) for i, a in enumerate(agencies, 1)], "agencies")


@router.callback_query(F.data.regexp(r"^jr:csv:(sources|agencies)$"))
async def on_csv(cb: CallbackQuery, session: AsyncSession) -> None:
    kind = cb.data.rsplit(":", 1)[1]
    repo = JobsRadarRepository(session)
    rows = await (repo.top_sources(limit=50) if kind == "sources" else repo.top_agencies(limit=30))
    if not rows:
        await cb.answer("Пусто.", show_alert=True)
        return
    data = sources_csv(rows) if kind == "sources" else agencies_csv(rows)
    if isinstance(cb.message, Message):
        await cb.message.answer_document(BufferedInputFile(data, filename=f"job_{kind}.csv"))
    await cb.answer()


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
