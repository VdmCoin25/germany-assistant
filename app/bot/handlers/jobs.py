"""Accept / decline an offer or application from the chat."""
from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.repositories.jobs import JobsError, JobsRepository
from app.i18n import t
from app.services.jobs.notify import Notifier

router = Router(name="jobs")


@router.callback_query(F.data.startswith("jc:"))
async def on_answer(cb: CallbackQuery, session: AsyncSession, settings: Settings, lang: str) -> None:
    try:
        _, rid, ok = cb.data.split(":")
        c = await JobsRepository(session).answer(cb.from_user.id, int(rid), ok == "1")
    except (JobsError, ValueError):
        await cb.answer()
        await cb.message.edit_reply_markup(reply_markup=None)
        return
    await session.commit()
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer(t(lang, "job_answer_saved"))
    await Notifier(cb.bot, settings).answered(session, c)
