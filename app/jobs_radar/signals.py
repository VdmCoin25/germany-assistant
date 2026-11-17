"""Turns a monitored message into stored signals: labels only, never the text or the author."""
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import JobKeyword, JobSignal, utcnow
from app.jobs_radar.agencies import upsert_agency
from app.jobs_radar.classifier import Classification, JobClassifier
from app.jobs_radar.prefilter import check

Terms = tuple[list[str], list[str]]


async def load_terms(session: AsyncSession) -> Terms:
    rows = (await session.execute(select(JobKeyword.term, JobKeyword.kind).where(JobKeyword.active.is_(True)))).all()
    include = [t for t, k in rows if k == "include"]
    exclude = [t for t, k in rows if k == "exclude"]
    return include, exclude


async def process_message(
    session: AsyncSession, classifier: JobClassifier, terms: Terms, *, chat_id: int, message_link: str, text: str
) -> Classification | None:
    """None if the prefilter rejects the message; otherwise the classification (noise is returned but not stored)."""
    include, exclude = terms
    if not check(text, include, exclude).passed:
        return None
    c = await classifier.classify(text)
    if c.label == "noise":
        return c
    session.add(JobSignal(
        chat_id=chat_id, message_link=message_link[:255], kind=c.label, city=c.city, profession=c.profession,
        language=c.language, confidence=c.confidence,
    ))
    if c.label == "agency_vacancy":
        await upsert_agency(session, c)
    await session.flush()
    return c


async def purge_old_signals(session: AsyncSession, days: int) -> int:
    result = await session.execute(delete(JobSignal).where(JobSignal.created_at < utcnow() - timedelta(days=days)))
    return result.rowcount or 0
