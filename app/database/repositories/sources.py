from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources_seed import SEED
from app.database.models import InfoSource


class SourceRepository:
    def __init__(self, session: AsyncSession):
        self.s = session

    async def seed_if_empty(self) -> int:
        """Add catalog links the DB does not have yet (by topic + url). Rows admins edited or disabled
        are left alone, so a redeploy never overwrites their changes."""
        have = {(t, u) for t, u in (await self.s.execute(select(InfoSource.topic, InfoSource.url))).all()}
        base = await self.s.scalar(select(func.count(InfoSource.id))) or 0
        added = 0
        for i, item in enumerate(SEED):
            if (item["topic"], item["url"]) in have:
                continue
            self.s.add(InfoSource(sort_order=base + i, **item))
            added += 1
        await self.s.flush()
        return added

    async def by_topic(self, topic: str) -> list[InfoSource]:
        res = await self.s.scalars(
            select(InfoSource)
            .where(InfoSource.topic == topic, InfoSource.is_active.is_(True))
            .order_by(InfoSource.sort_order)
        )
        return list(res)

    async def all_active(self) -> list[InfoSource]:
        res = await self.s.scalars(
            select(InfoSource).where(InfoSource.is_active.is_(True)).order_by(InfoSource.sort_order)
        )
        return list(res)
