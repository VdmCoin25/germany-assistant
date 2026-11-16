import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AnalyticsEvent

ALLOWED_EVENTS = {
    "bot_started",
    "language_selected",
    "registration_completed",
    "feature_used",
    "document_analysis_completed",
    "job_search_completed",
    "translation_completed",
    "subscription_started",
    "subscription_cancelled",
    "data_deleted",
}


def user_hash(telegram_id: int, salt: str) -> str:
    return hmac.new(salt.encode(), str(telegram_id).encode(), hashlib.sha256).hexdigest()


class AnalyticsRepository:
    def __init__(self, session: AsyncSession, salt: str):
        self.s = session
        self.salt = salt

    async def log(self, name: str, telegram_id: int, feature: str | None = None) -> None:
        if name not in ALLOWED_EVENTS:
            raise ValueError(f"Unknown event: {name}")
        self.s.add(AnalyticsEvent(name=name, feature=feature, user_hash=user_hash(telegram_id, self.salt)))

    async def summary(self, days: int = 7) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        rows = await self.s.execute(
            select(AnalyticsEvent.name, AnalyticsEvent.feature, func.count(AnalyticsEvent.id))
            .where(AnalyticsEvent.created_at >= since)
            .group_by(AnalyticsEvent.name, AnalyticsEvent.feature)
        )
        out: dict[str, int] = {}
        for name, feature, n in rows.all():
            out[f"{name}:{feature}" if feature else name] = n
        return out
