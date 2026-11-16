"""Catalog of Telegram chats watched by the Jobs Source Radar."""
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.jobs_radar_keywords import KEYWORDS
from app.database.models import JobChat, JobChatDaily, JobKeyword, JobRadarAction, JobSignal, utcnow
from app.jobs_radar.discovery import FoundLink
from app.jobs_radar.scoring import score_chat
from app.jobs_radar.tglinks import ChatLink, parse_chat_link

STATUSES = ("candidate", "approved", "joined", "rejected")
ADS_VALUES = ("unknown", "yes", "no")
_MAX_LEN = {"title": 255, "city": 80, "land": 8, "language": 8}


METADATA_FIELDS = ("title", "members", "entity_type", "ads_allowed", "admin_contact", "last_checked_at")
METADATA_RECHECK = timedelta(days=7)
_BLOCK_PREFIXES = ("flood@", "stopped@")


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _parse_iso(text: str) -> datetime | None:
    try:
        return _aware(datetime.fromisoformat(text))
    except ValueError:
        return None


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

    # --- monitor (J1.2) ---

    async def list_joined(self) -> list[JobChat]:
        res = await self.s.scalars(
            select(JobChat).where(JobChat.status == "joined", JobChat.tg_chat_id.is_not(None)).order_by(JobChat.id)
        )
        return list(res)

    async def list_to_join(self, now: datetime) -> list[JobChat]:
        """Approved chats whose retry time passed. join_error keeps "<reason>@<iso>": no retry before that moment."""
        res = await self.s.scalars(
            select(JobChat).where(JobChat.status == "approved").order_by(JobChat.score.desc(), JobChat.id)
        )
        due = []
        for chat in res:
            _, _, until = (chat.join_error or "").partition("@")
            retry_at = _parse_iso(until) if until else None
            if retry_at is None or retry_at <= now:
                due.append(chat)
        return due

    async def mark_joined(self, chat_id: int, tg_chat_id: int, entity_type: str | None = None) -> JobChat | None:
        """Set status=joined. If another row already owns this tg_chat_id (same chat found twice), keep that one."""
        chat = await self.get(chat_id)
        if chat is None:
            return None
        other = await self.s.scalar(select(JobChat).where(JobChat.tg_chat_id == tg_chat_id, JobChat.id != chat_id))
        if other is not None:
            await self.delete_chat(chat_id)
            chat = other
        chat.tg_chat_id = tg_chat_id
        chat.status = "joined"
        chat.join_error = None
        if entity_type:
            chat.entity_type = entity_type
        await self.s.flush()
        return chat

    async def set_join_error(self, chat_id: int, error: str, retry_after: datetime | None = None) -> None:
        """join_error = "<reason>" or "<reason>@<iso retry time>"; list_to_join skips the chat until that time."""
        chat = await self.get(chat_id)
        if chat is None:
            return
        value = error[:80] + (f"@{retry_after.isoformat()}" if retry_after else "")
        chat.join_error = value[:120]
        await self.s.flush()

    async def mark_lost(self, chat_id: int) -> None:
        chat = await self.get(chat_id)
        if chat is not None:
            chat.status = "rejected"
            chat.join_error = "lost_access"
            await self.s.flush()

    async def record_action(
        self, kind: str, chat_id: int | None, result: str, at: datetime | None = None
    ) -> JobRadarAction:
        action = JobRadarAction(kind=kind, chat_id=chat_id, result=result[:64], at=at or utcnow())
        self.s.add(action)
        await self.s.flush()
        return action

    async def count_actions_since(self, kind: str, since: datetime) -> int:
        return await self.s.scalar(
            select(func.count(JobRadarAction.id)).where(JobRadarAction.kind == kind, JobRadarAction.at >= since)
        ) or 0

    async def last_action_at(self, kind: str) -> datetime | None:
        return _aware(await self.s.scalar(select(func.max(JobRadarAction.at)).where(JobRadarAction.kind == kind)))

    async def blocked_until(self, kind: str, now: datetime) -> datetime | None:
        """Latest FloodWait / stop deadline in the journal (results "flood@<iso>", "stopped@<iso>") if still ahead."""
        rows = await self.s.scalars(
            select(JobRadarAction.result)
            .where(JobRadarAction.kind == kind, or_(*[JobRadarAction.result.like(f"{p}%") for p in _BLOCK_PREFIXES]))
            .order_by(JobRadarAction.at.desc(), JobRadarAction.id.desc())
            .limit(5)
        )
        deadlines = [d for r in rows if (d := _parse_iso(r.partition("@")[2])) is not None and d > now]
        return max(deadlines, default=None)

    async def chats_for_metadata(self, now: datetime, limit: int) -> list[JobChat]:
        """Never checked with unknown type first, then those last checked over 7 days ago. Rejected are skipped."""
        res = await self.s.scalars(
            select(JobChat)
            .where(
                JobChat.status != "rejected",
                or_(
                    (JobChat.entity_type == "unknown") & JobChat.last_checked_at.is_(None),
                    JobChat.last_checked_at < now - METADATA_RECHECK,
                ),
            )
            .order_by(JobChat.last_checked_at.is_not(None), JobChat.last_checked_at, JobChat.id)
            .limit(limit)
        )
        return list(res)

    async def apply_metadata(self, chat_id: int, **fields) -> None:
        unknown = set(fields) - set(METADATA_FIELDS)
        if unknown:
            raise ValueError(f"unexpected metadata fields: {sorted(unknown)}")
        chat = await self.get(chat_id)
        if chat is None:
            return
        for key, value in fields.items():
            if key == "title" and value:
                value = value[:255]
            if key == "admin_contact" and value:
                value = value[:120]
            setattr(chat, key, value)
        await self.s.flush()

    async def delete_chat(self, chat_id: int) -> None:
        await self.s.execute(delete(JobChatDaily).where(JobChatDaily.chat_id == chat_id))
        await self.s.execute(delete(JobSignal).where(JobSignal.chat_id == chat_id))
        await self.s.execute(update(JobRadarAction).where(JobRadarAction.chat_id == chat_id).values(chat_id=None))
        await self.s.execute(delete(JobChat).where(JobChat.id == chat_id))

    async def bump_daily(self, chat_id: int, day: date) -> None:
        row = await self.s.get(JobChatDaily, (chat_id, day))
        if row is None:
            self.s.add(JobChatDaily(chat_id=chat_id, day=day, posts=1))
        else:
            row.posts += 1
        await self.s.flush()

    async def set_last_message_id(self, chat_id: int, msg_id: int) -> None:
        chat = await self.get(chat_id)
        if chat is not None and (chat.last_message_id is None or msg_id > chat.last_message_id):
            chat.last_message_id = msg_id
            await self.s.flush()

    async def recompute_stats(self, now: datetime) -> int:
        """posts_per_day_7d = posts of the last 7 days / 7; signal_share = signals 7d / max(posts 7d, 1); then score."""
        first_day = (now - timedelta(days=6)).date()
        posts = dict((await self.s.execute(
            select(JobChatDaily.chat_id, func.sum(JobChatDaily.posts))
            .where(JobChatDaily.day >= first_day).group_by(JobChatDaily.chat_id)
        )).all())
        signals = dict((await self.s.execute(
            select(JobSignal.chat_id, func.count(JobSignal.id))
            .where(JobSignal.created_at >= now - timedelta(days=7)).group_by(JobSignal.chat_id)
        )).all())
        chats = list(await self.s.scalars(select(JobChat)))
        for chat in chats:
            posts_7d = int(posts.get(chat.id, 0))
            share = int(signals.get(chat.id, 0)) / max(posts_7d, 1)
            chat.posts_per_day_7d = round(posts_7d / 7, 3)
            chat.score = score_chat(
                chat.posts_per_day_7d, chat.members, share, chat.language,
                bool(chat.city or chat.land), chat.ads_allowed or "unknown",
            )
        await self.s.flush()
        return len(chats)

    async def purge_daily(self, older_than_days: int = 30) -> int:
        cutoff = (utcnow() - timedelta(days=older_than_days)).date()
        result = await self.s.execute(delete(JobChatDaily).where(JobChatDaily.day < cutoff))
        return result.rowcount or 0

    @staticmethod
    def _new(link: ChatLink, status: str, discovered_from: str) -> JobChat:
        return JobChat(
            username=link.value.lower() if link.kind == "username" else None,
            invite_hash=link.value if link.kind == "invite" else None,
            status=status, discovered_from=discovered_from, entity_type="unknown",
            ads_allowed="unknown", posts_per_day_7d=0, score=0,
        )
