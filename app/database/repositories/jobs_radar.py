"""Catalog of Telegram chats watched by the Jobs Source Radar."""
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.jobs_radar_keywords import KEYWORDS
from app.database.models import JobChat, JobKeyword
from app.jobs_radar.discovery import FoundLink
from app.jobs_radar.tglinks import ChatLink, parse_chat_link

STATUSES = ("candidate", "approved", "joined", "rejected")
ADS_VALUES = ("unknown", "yes", "no")
_MAX_LEN = {"title": 255, "city": 80, "land": 8, "language": 8}


def _clean(value) -> str | None:
    value = (value or "").strip()
    return value or None


class JobsRadarRepository:
    def __init__(self, session: AsyncSession):
        self.s = session

    async def get(self, chat_id: int) -> JobChat | None:
        return await self.s.get(JobChat, chat_id)

    async def get_by_username(self, username: str) -> JobChat | None:
        return await self.s.scalar(select(JobChat).where(JobChat.username == username.lstrip("@").lower()))

    async def get_by_invite(self, invite_hash: str) -> JobChat | None:
        return await self.s.scalar(select(JobChat).where(JobChat.invite_hash == invite_hash))

    async def get_by_link(self, link: ChatLink) -> JobChat | None:
        if link.kind == "username":
            return await self.get_by_username(link.value)
        return await self.get_by_invite(link.value)

    async def add_manual(self, link: ChatLink) -> tuple[JobChat, bool]:
        existing = await self.get_by_link(link)
        if existing:
            return existing, False
        chat = self._new(link, status="approved", discovered_from="seed")
        self.s.add(chat)
        await self.s.flush()
        return chat, True

    async def add_candidates(self, links: Iterable[FoundLink], via_chat_id: int | None = None) -> int:
        created = 0
        for found in links:
            if await self.get_by_link(found.link):
                continue
            chat = self._new(found.link, status="candidate", discovered_from=found.source)
            chat.discovered_via_chat_id = via_chat_id
            self.s.add(chat)
            await self.s.flush()
            created += 1
        return created

    async def list_candidates(self, limit: int = 10) -> list[JobChat]:
        res = await self.s.scalars(
            select(JobChat)
            .where(JobChat.status == "candidate", JobChat.entity_type != "user")
            .order_by(JobChat.score.desc(), JobChat.created_at, JobChat.id)
            .limit(limit)
        )
        return list(res)

    async def set_status(self, chat_id: int, status: str) -> JobChat | None:
        if status not in STATUSES:
            raise ValueError(f"bad status: {status}")
        chat = await self.get(chat_id)
        if chat:
            chat.status = status
            await self.s.flush()
        return chat

    async def import_rows(self, rows: Iterable[dict]) -> tuple[int, int]:
        """Upsert seed chats by username. Returns (created, updated)."""
        created = updated = 0
        for row in rows:
            raw = (row.get("username") or "").strip()
            link = parse_chat_link(raw if "/" in raw or raw.startswith("@") else f"@{raw}")
            if link is None or link.kind != "username":
                raise ValueError(f"bad username: {row.get('username')!r}")
            if len(link.value) > 64:
                raise ValueError(f"username too long: {link.value!r}")
            fields = {k: _clean(row.get(k)) for k in ("title", "city", "land", "language")}
            for k, v in fields.items():
                if v is not None and len(v) > _MAX_LEN[k]:
                    raise ValueError(f"{k} too long for {link.value}")
            ads = _clean(row.get("ads_allowed"))
            if ads is not None and ads not in ADS_VALUES:
                raise ValueError(f"bad ads_allowed for {link.value}: {ads!r}")
            fields["ads_allowed"] = ads
            fields = {k: v for k, v in fields.items() if v is not None}
            chat = await self.get_by_username(link.value)
            if chat:
                for k, v in fields.items():
                    setattr(chat, k, v)
                if chat.status in ("candidate", "rejected"):
                    chat.status = "approved"
                chat.discovered_from = "seed"
                updated += 1
            else:
                chat = self._new(link, status="approved", discovered_from="seed")
                for k, v in fields.items():
                    setattr(chat, k, v)
                self.s.add(chat)
                created += 1
            await self.s.flush()
        return created, updated

    async def seed_keywords_if_empty(self) -> int:
        if await self.s.scalar(select(func.count(JobKeyword.id))):
            return 0
        for term, lang, kind in KEYWORDS:
            self.s.add(JobKeyword(term=term, lang=lang, kind=kind))
        await self.s.flush()
        return len(KEYWORDS)

    @staticmethod
    def _new(link: ChatLink, status: str, discovered_from: str) -> JobChat:
        return JobChat(
            username=link.value.lower() if link.kind == "username" else None,
            invite_hash=link.value if link.kind == "invite" else None,
            status=status, discovered_from=discovered_from, entity_type="unknown",
            ads_allowed="unknown", posts_per_day_7d=0, score=0,
        )
