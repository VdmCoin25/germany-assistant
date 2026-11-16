from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AnalyticsEvent, User, utcnow

PROFILE_FIELDS = ("language", "land", "city", "german_level", "goal", "residence_status", "broadcast_consent")


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.s = session

    async def get(self, telegram_id: int) -> User | None:
        return await self.s.scalar(select(User).where(User.telegram_id == telegram_id))

    async def get_or_create(self, telegram_id: int) -> User:
        user = await self.get(telegram_id)
        if user is None:
            user = User(telegram_id=telegram_id)
            self.s.add(user)
            await self.s.flush()
        return user

    async def touch(self, user: User) -> None:
        user.last_seen_at = utcnow()

    async def update_profile(self, user: User, **fields) -> User:
        for k, v in fields.items():
            if k not in PROFILE_FIELDS:
                raise ValueError(f"Field not allowed: {k}")
            setattr(user, k, v)
        await self.s.flush()
        return user

    async def set_blocked(self, telegram_id: int, blocked: bool) -> bool:
        user = await self.get(telegram_id)
        if not user:
            return False
        user.is_blocked = blocked
        await self.s.flush()
        return True

    async def export(self, user: User) -> dict:
        from app.database.repositories.jobs import JobsRepository

        jobs = await JobsRepository(self.s).export_user(user.telegram_id)
        return {**({"jobs": jobs} if jobs else {}),
            "telegram_id": user.telegram_id,
            **{f: getattr(user, f) for f in PROFILE_FIELDS},
            "is_registered": user.is_registered,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_seen_at": user.last_seen_at.isoformat() if user.last_seen_at else None,
            "note": "Documents and message contents are not stored by the bot.",
        }

    async def delete_all(self, user: User, user_hash: str) -> None:
        """GDPR erasure: profile and pseudonymous analytics linked to the user."""
        from app.database.repositories.jobs import JobsRepository

        await JobsRepository(self.s).delete_user(user.telegram_id)
        await self.s.execute(delete(AnalyticsEvent).where(AnalyticsEvent.user_hash == user_hash))
        await self.s.delete(user)
        await self.s.flush()

    # --- admin stats (aggregates only) ---
    async def stats(self) -> dict:
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        total = await self.s.scalar(select(func.count(User.id)))
        registered = await self.s.scalar(select(func.count(User.id)).where(User.is_registered.is_(True)))
        active7 = await self.s.scalar(select(func.count(User.id)).where(User.last_seen_at >= week_ago))
        rows = await self.s.execute(select(User.language, func.count(User.id)).group_by(User.language))
        return {
            "total": total or 0,
            "registered": registered or 0,
            "active_7d": active7 or 0,
            "by_language": {str(lang): n for lang, n in rows.all()},
        }
