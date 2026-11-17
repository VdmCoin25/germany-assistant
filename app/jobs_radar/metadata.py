"""Chat metadata collector: type, member count, ads policy and admin contact from the chat's PUBLIC description.

Daily cap from job_radar_actions (kind="metadata"). Never reads member lists or user profiles, and never
stores the description text itself.
"""
import asyncio
import logging
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker
from telethon import errors
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import CheckChatInviteRequest
from telethon.tl.types import Channel, ChannelForbidden, Chat, ChatForbidden, ChatInvite, ChatInviteAlready, User

from app.database.models import JobChat
from app.database.repositories.jobs_radar import JobsRadarRepository

log = logging.getLogger(__name__)

BATCH = 10
PAUSE_RANGE_S = (2.0, 5.0)
_KEEP_ROW_ERRORS = (errors.ChannelPrivateError, errors.ChannelInvalidError, errors.ChannelPublicGroupNaError)
_DEAD_NAME_ERRORS = (errors.UsernameNotOccupiedError, errors.UsernameInvalidError)

_ADS_NO = re.compile(
    r"реклам\w*[\s:–—\-]*(?:заборон\w*|запрещ[её]н\w*|не\s+допускается|не\s+принимается)"
    r"|заборон\w*\s+реклам\w*|запрет\s+реклам\w*|без\s+реклам\w*"
    r"|keine\s+werbung|werbung\s+(?:verboten|nicht\s+erlaubt)",
    re.IGNORECASE,
)
_ADS_YES = re.compile(
    r"реклам\w*[\s:–—\-]*(?:за\s+домовленістю|по\s+договор[её]нности|платн\w*)|платн\w*\s+реклам\w*",
    re.IGNORECASE,
)
_CONTACT_RE = re.compile(
    r"(?<![\w@/.])@([A-Za-z][A-Za-z0-9_]{3,31})"
    r"|(?:https?://)?(?:t\.me|telegram\.me)/([A-Za-z][A-Za-z0-9_]{3,31})(?![\w/])",
    re.IGNORECASE,
)


@dataclass
class Info:
    entity_type: str
    title: str | None
    members: int | None
    about: str


def parse_ads_allowed(about: str) -> str:
    if _ADS_NO.search(about):
        return "no"
    if _ADS_YES.search(about):
        return "yes"
    return "unknown"


def parse_admin_contact(about: str) -> str | None:
    """First @username or t.me/<username> link in the description, as "@username"."""
    m = _CONTACT_RE.search(about)
    return f"@{m.group(1) or m.group(2)}" if m else None


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MetadataCollector:
    def __init__(
        self,
        *,
        sm: async_sessionmaker,
        client: Any,
        daily_cap: int,
        alert: Callable[[str], Awaitable[None]] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rand: Callable[[float, float], float] = random.uniform,
        clock: Callable[[], datetime] = _utcnow,
        batch: int = BATCH,
    ) -> None:
        self.sm, self.client, self.daily_cap = sm, client, daily_cap
        self.alert, self.sleep, self.rand, self.clock, self.batch = alert, sleep, rand, clock, batch

    async def run(self, poll_seconds: float = 600.0) -> None:
        while True:
            try:
                await self.step()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("metadata step failed")
            await self.sleep(poll_seconds)

    async def step(self) -> int:
        """Check up to a batch of due chats within the daily cap. Returns how many lookups were made."""
        now = self.clock()
        async with self.sm() as session:
            repo = JobsRadarRepository(session)
            if await repo.blocked_until("metadata", now):
                return 0
            left = self.daily_cap - await repo.count_actions_since("metadata", now - timedelta(hours=24))
            if left <= 0:
                return 0
            chats = await repo.chats_for_metadata(now, min(left, self.batch))
        done = 0
        for chat in chats:
            if done:
                await self.sleep(self.rand(*PAUSE_RANGE_S))
            if not await self._check(chat):
                return done + 1
            done += 1
        return done

    async def _check(self, chat: JobChat) -> bool:
        """False after a FloodWait: stop the batch."""
        now = self.clock()
        async with self.sm() as session:
            repo = JobsRadarRepository(session)
            try:
                info = await self._lookup(chat)
                if info is None:  # a user or a bot: never keep it
                    await repo.delete_chat(chat.id)
                    await repo.record_action("metadata", None, "user_deleted", at=now)
                    result = None
                else:
                    await repo.apply_metadata(chat.id, **self._fields(chat, info, now))
                    result = "ok"
            except errors.FloodWaitError as e:
                until = now + timedelta(seconds=e.seconds)
                await repo.record_action("metadata", chat.id, f"flood@{until.isoformat()}", at=now)
                await session.commit()
                log.warning("flood wait on metadata: %s s", e.seconds)
                await self._alert(f"FloodWait при проверке чатов: пауза до {until:%Y-%m-%d %H:%M} UTC.")
                return False
            except _DEAD_NAME_ERRORS as e:
                await repo.apply_metadata(chat.id, last_checked_at=now)
                await repo.set_status(chat.id, "rejected")
                result = type(e).__name__
            except _KEEP_ROW_ERRORS as e:
                await repo.apply_metadata(chat.id, last_checked_at=now)
                result = type(e).__name__
            except Exception as e:
                log.exception("metadata lookup failed: chat=%s", chat.id)
                await repo.apply_metadata(chat.id, last_checked_at=now)
                result = f"error:{type(e).__name__}"
            if result is not None:
                await repo.record_action("metadata", chat.id, result, at=now)
            await session.commit()
        return True

    @staticmethod
    def _fields(chat: JobChat, info: Info, now: datetime) -> dict:
        fields: dict = {"entity_type": info.entity_type, "last_checked_at": now}
        if info.title:
            fields["title"] = info.title
        if info.members is not None:
            fields["members"] = info.members
        ads = parse_ads_allowed(info.about)
        if ads != "unknown":
            fields["ads_allowed"] = ads
        contact = parse_admin_contact(info.about)
        if contact:
            fields["admin_contact"] = contact
        return fields

    async def _lookup(self, chat: JobChat) -> Info | None:
        """None for users and bots. Raises Telethon errors."""
        if chat.username:
            entity = await self.client.get_entity(chat.username)
        elif chat.invite_hash:
            invite = await self.client(CheckChatInviteRequest(chat.invite_hash))
            if isinstance(invite, ChatInviteAlready):
                entity = invite.chat
            elif isinstance(invite, ChatInvite):
                kind = "channel" if invite.broadcast else "group"
                return Info(kind, invite.title, invite.participants_count, invite.about or "")
            else:
                raise errors.InviteHashInvalidError(request=None)
        elif chat.tg_chat_id:
            entity = await self.client.get_entity(chat.tg_chat_id)
        else:
            raise errors.UsernameInvalidError(request=None)

        if isinstance(entity, User):
            return None
        if isinstance(entity, (ChannelForbidden, ChatForbidden)):
            raise errors.ChannelPrivateError(request=None)
        if isinstance(entity, Channel):
            full = await self.client(GetFullChannelRequest(entity))
            return Info(
                "channel" if entity.broadcast else "group",
                entity.title,
                getattr(full.full_chat, "participants_count", None),
                getattr(full.full_chat, "about", None) or "",
            )
        if isinstance(entity, Chat):
            return Info("group", entity.title, getattr(entity, "participants_count", None), "")
        raise errors.ChannelInvalidError(request=None)

    async def _alert(self, text: str) -> None:
        if self.alert is None:
            return
        try:
            await self.alert(text)
        except Exception:
            log.warning("alert failed: %s", text[:80])
