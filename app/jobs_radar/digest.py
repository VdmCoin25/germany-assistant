"""Daily admin digest of newly seen agencies. Seekers are never reported."""
import html
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import JobAgency, utcnow

log = logging.getLogger(__name__)
MAX_AGENCIES = 30


def _line(a: JobAgency) -> str:
    parts = [f"<b>{html.escape(a.name)}</b>"]
    for value in (a.website, a.email, a.phone_norm):
        if value:
            parts.append(html.escape(value))
    return "• " + " | ".join(parts) + f" (упоминаний: {a.signals_count})"


async def build_agency_digest(session: AsyncSession) -> tuple[str | None, list[int]]:
    rows = (await session.scalars(
        select(JobAgency).where(JobAgency.digest_sent_at.is_(None)).order_by(JobAgency.first_seen_at, JobAgency.id)
    )).all()
    if not rows:
        return None, []
    shown = rows[:MAX_AGENCIES]
    text = f"Новые агентства из Telegram-чатов ({len(rows)}):\n\n" + "\n".join(_line(a) for a in shown)
    if len(rows) > len(shown):
        text += f"\n\nИ ещё {len(rows) - len(shown)}: придут в следующем дайджесте."
    return text, [a.id for a in shown]


async def send_agency_digest(bot, session: AsyncSession, admin_ids) -> int:
    text, ids = await build_agency_digest(session)
    if not text or not admin_ids:
        return 0
    delivered = 0
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
            delivered += 1
        except Exception:
            log.exception("Agency digest was not delivered to admin %s", admin_id)
    if not delivered:
        return 0
    now = utcnow()
    for agency in (await session.scalars(select(JobAgency).where(JobAgency.id.in_(ids)))).all():
        agency.digest_sent_at = now
    await session.flush()
    return len(ids)
