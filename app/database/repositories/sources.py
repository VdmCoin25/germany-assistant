from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sources_seed import SEED
from app.database.models import InfoSource


class SourceRepository:
    def __init__(self, session: AsyncSession):
        self.s = session

    async def seed_if_empty(self) -> int:
        count = await self.s.scalar(select(func.count(InfoSource.id)))
        if count:
            return 0
        for i, item in enumerate(SEED):
            self.s.add(InfoSource(sort_order=i, **item))
        await self.s.flush()
        return len(SEED)

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
