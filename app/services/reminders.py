"""Sends deadline reminders. Runs inside the bot process every few minutes; only between 8:00 and 21:00
Berlin time so nobody is woken up. Missed reminders (server asleep) go out on the next run."""
import asyncio
import logging
from datetime import datetime

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database.repositories.deadlines import BERLIN, DeadlineRepository, today_berlin
from app.database.repositories.users import UserRepository
from app.i18n import t

log = logging.getLogger(__name__)


def _when(lang: str, left: int) -> str:
    if left <= 0:
        return t(lang, "deadline_today")
    if left == 1:
        return t(lang, "deadline_tomorrow")
    return t(lang, "deadline_in_days", n=left)


async def send_due(bot: Bot, sm: async_sessionmaker, default_lang: str, now: datetime | None = None) -> int:
    now = (now or datetime.now(BERLIN)).astimezone(BERLIN)
    if not 8 <= now.hour < 21:
        return 0
    today = today_berlin(now)
    sent = 0
    async with sm() as s:
        repo, users = DeadlineRepository(s), UserRepository(s)
        for d, left in await repo.due_reminders(today):
            u = await users.get(d.owner_tg)
            lang = (u.language if u and u.language else default_lang)
            try:
                await bot.send_message(d.owner_tg, t(lang, "deadline_msg", title=d.title,
                                                     date=d.due.strftime("%d.%m.%Y"), when=_when(lang, left)),
                                       parse_mode=None)
                sent += 1
            except Exception as ex:  # noqa: BLE001 — a blocked bot must not stop the others
                log.warning("reminder failed: %s", type(ex).__name__)
            await repo.mark_sent(d, left)   # mark even on failure: no retry storm for blocked chats
        await repo.purge_past(today)
        await s.commit()
    return sent


async def reminders_loop(bot: Bot, sm: async_sessionmaker, default_lang: str, interval: int = 600) -> None:
    await asyncio.sleep(30)
    while True:
        try:
            n = await send_due(bot, sm, default_lang)
            if n:
                log.info("reminders sent: %s", n)
        except Exception as ex:  # noqa: BLE001
            log.warning("reminders loop: %s", type(ex).__name__)
        await asyncio.sleep(interval)
