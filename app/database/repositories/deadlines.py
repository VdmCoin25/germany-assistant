"""User deadlines and the reminder schedule (3 days before, the day before)."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Deadline

BERLIN = ZoneInfo("Europe/Berlin")
MAX_PER_USER = 30


def today_berlin(now: datetime | None = None) -> date:
    return (now or datetime.now(BERLIN)).astimezone(BERLIN).date()


class DeadlineError(Exception):
    def __init__(self, code: str, status: int = 400):
        self.code, self.status = code, status


class DeadlineRepository:
    def __init__(self, session: AsyncSession):
        self.s = session

    async def for_user(self, tg: int, since: date | None = None) -> list[Deadline]:
        q = select(Deadline).where(Deadline.owner_tg == tg)
        if since:
            q = q.where(Deadline.due >= since)
        return list(await self.s.scalars(q.order_by(Deadline.due, Deadline.id)))

    async def add(self, tg: int, title: str, due: date) -> Deadline:
        n = await self.s.scalar(select(func.count(Deadline.id)).where(Deadline.owner_tg == tg))
        if n >= MAX_PER_USER:
            raise DeadlineError("too_many", 409)
        d = Deadline(owner_tg=tg, title=title, due=due)
        self.s.add(d)
        await self.s.flush()
        return d

    async def remove(self, tg: int, deadline_id: int) -> None:
        d = await self.s.get(Deadline, deadline_id)
        if d is None or d.owner_tg != tg:
            raise DeadlineError("not_found", 404)
        await self.s.delete(d)
        await self.s.flush()

    async def due_reminders(self, today: date) -> list[tuple[Deadline, int]]:
        """(deadline, days_left) for every reminder that should go out now and has not gone out yet.
        Catches up after the server slept: a missed 3-day reminder still goes out on day 2."""
        rows = await self.s.scalars(select(Deadline).where(
            Deadline.due >= today, Deadline.due <= today + timedelta(days=3),
            (Deadline.sent_3.is_(False)) | (Deadline.sent_1.is_(False))).order_by(Deadline.due))
        out = []
        for d in rows:
            left = (d.due - today).days
            if left <= 1 and not d.sent_1:
                out.append((d, left))
            elif left >= 2 and not d.sent_3:
                out.append((d, left))
        return out

    async def mark_sent(self, d: Deadline, left: int) -> None:
        if left <= 1:
            d.sent_1 = d.sent_3 = True     # no "in 3 days" after "tomorrow"
        else:
            d.sent_3 = True
        await self.s.flush()

    async def delete_user(self, tg: int) -> None:
        await self.s.execute(delete(Deadline).where(Deadline.owner_tg == tg))

    async def purge_past(self, today: date, keep_days: int = 30) -> None:
        """Dates long gone are not needed: keep a month, then drop (data minimisation)."""
        await self.s.execute(delete(Deadline).where(Deadline.due < today - timedelta(days=keep_days)))
