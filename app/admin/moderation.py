"""Admin moderation of the job exchange, right in the bot chat."""
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.handlers import IsAdmin
from app.config import Settings
from app.database.repositories.jobs import JobsError, JobsRepository, aware
from app.services.jobs.notify import Notifier, mod_kb, render_for_admin

router = Router(name="moderation")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


async def show_next(message: Message, session: AsyncSession) -> None:
    items = await JobsRepository(session).pending()
    if not items:
        await message.answer("Очередь модерации пуста.")
        return
    kind, obj = items[0]
    await message.answer(f"В очереди: {len(items)}\n\n" + await render_for_admin(session, kind, obj),
                         reply_markup=mod_kb(kind, obj.id))


@router.message(Command("moderate"))
async def cmd_moderate(message: Message, session: AsyncSession) -> None:
    await show_next(message, session)


@router.callback_query(F.data.startswith("mod:"))
async def on_mod(cb: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    try:
        _, kind, obj_id, ok = cb.data.split(":")
        approved = ok == "1"
        jobs = JobsRepository(session)
        obj = await jobs.moderate(kind, int(obj_id), approved, pilot_days=settings.employer_pilot_days,
                                  vacancy_days=settings.vacancy_days)
    except (JobsError, ValueError):
        await cb.answer("Уже обработано или не найдено.", show_alert=True)
        return
    await session.commit()
    await Notifier(cb.bot, settings).moderated(session, kind, obj, approved)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer("✅ Одобрено." if approved else "❌ Отклонено.")
    await cb.answer()
    await show_next(cb.message, session)


@router.message(Command("grant_employer"))
async def cmd_grant(message: Message, command: CommandObject, session: AsyncSession) -> None:
    parts = (command.args or "").split()
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        await message.answer("Формат: /grant_employer <telegram_id> <дней>")
        return
    try:
        e = await JobsRepository(session).grant(int(parts[0]), int(parts[1]))
    except JobsError:
        await message.answer("Работодатель не найден.")
        return
    await message.answer(f"Доступ «{e.company}» продлён до {aware(e.access_until):%d.%m.%Y}.")
