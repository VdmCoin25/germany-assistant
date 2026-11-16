"""Rate-limited chat joiner: only approved chats, one join at a time, random pauses, daily cap, FloodWait guard.

Limits and the journal live in job_radar_actions (kind="join"). Block deadlines are journaled as
"flood@<iso>" / "stopped@<iso>" and survive restarts.
"""
import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker
from telethon import errors

from app.database.models import JobChat
from app.database.repositories.jobs_radar import JobsRadarRepository
from app.jobs_radar.state import ChatRef, JoinedState
from app.jobs_radar.tglinks import ChatLink

log = logging.getLogger(__name__)

PAUSE_MIN_S = 3600
PAUSE_MAX_S = 7200
REQUEST_RETRY = timedelta(hours=24)
ERROR_RETRY = timedelta(hours=24)
STOP_BLOCK = timedelta(hours=24)

JoinFn = Callable[[ChatLink], Awaitable[int]]
CheckFn = Callable[[ChatLink], Awaitable[int | None]]
Alert = Callable[[str], Awaitable[None]]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def human_duration(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m = rem // 60
    return f"{h} ч {m} мин" if h else f"{max(m, 1)} мин"


def _is_stop(exc: errors.RPCError) -> bool:
    if isinstance(exc, errors.ChannelsTooMuchError):
        return True
    return "FROZEN_METHOD_INVALID" in f"{getattr(exc, 'message', '')} {exc}"


def _chat_link(chat: JobChat) -> ChatLink | None:
    if chat.username:
        return ChatLink("username", chat.username)
    if chat.invite_hash:
        return ChatLink("invite", chat.invite_hash)
    return None


def _name(chat: JobChat) -> str:
    return chat.title or (f"@{chat.username}" if chat.username else "приватная ссылка")


class Joiner:
    def __init__(
        self,
        *,
        sm: async_sessionmaker,
        state: JoinedState,
        join_fn: JoinFn,
        check_fn: CheckFn,
        daily_cap: int,
        alert: Alert | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rand: Callable[[float, float], float] = random.uniform,
        clock: Callable[[], datetime] = _utcnow,
        on_joined: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> None:
        self.sm, self.state = sm, state
        self.join_fn, self.check_fn = join_fn, check_fn
        self.daily_cap = daily_cap
        self.alert, self.sleep, self.rand, self.clock = alert, sleep, rand, clock
        self.on_joined = on_joined
        self.next_at: datetime | None = None  # earliest time of the next attempt
        self.stopped = False  # CHANNELS_TOO_MUCH / frozen account: no more joins until restart

    async def run(self, poll_seconds: float = 30.0) -> None:
        while True:
            try:
                await self.step()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("joiner step failed")
            await self.sleep(poll_seconds)

    async def step(self) -> None:
        """One tick: at most one join attempt."""
        if self.stopped:
            return
        now = self.clock()
        async with self.sm() as session:
            repo = JobsRadarRepository(session)
            if await repo.blocked_until("join", now):
                return
            if self.next_at is None:
                last = await repo.last_action_at("join")
                self.next_at = last + timedelta(seconds=self.rand(PAUSE_MIN_S, PAUSE_MAX_S)) if last else now
            if now < self.next_at:
                return
            if await repo.count_actions_since("join", now - timedelta(hours=24)) >= self.daily_cap:
                return
            due = await repo.list_to_join(now)
            if not due:
                return
            chat = due[0]
            link = _chat_link(chat)
            if link is None:
                await repo.set_join_error(chat.id, "no_link", now + ERROR_RETRY)
                await session.commit()
                return
            action = await repo.record_action("join", chat.id, "attempt", at=now)
            await session.commit()  # counted before the network call: a crash must not allow extra joins
            try:
                action.result = await self._attempt(repo, chat, link)
            except Exception as e:
                log.exception("join failed: chat=%s", chat.id)
                action.result = await self._fail(repo, chat, f"error:{type(e).__name__}")
            finally:
                self.next_at = self.clock() + timedelta(seconds=self.rand(PAUSE_MIN_S, PAUSE_MAX_S))
            await session.commit()

    async def _attempt(self, repo: JobsRadarRepository, chat: JobChat, link: ChatLink) -> str:
        now = self.clock()
        name = _name(chat)
        try:
            try:
                tg_chat_id = await self.join_fn(link)
                result = "joined"
            except errors.UserAlreadyParticipantError:
                tg_chat_id = await self.check_fn(link)
                if tg_chat_id is None:
                    raise
                result = "already_participant"
            await self._joined(repo, chat, tg_chat_id, name)
            return result
        except errors.InviteRequestSentError:
            await repo.set_join_error(chat.id, "request_sent", now + REQUEST_RETRY)
            await self._alert(f"Заявка на вступление отправлена, жду одобрения: {name}")
            return "request_sent"
        except errors.FloodWaitError as e:
            until = now + timedelta(seconds=e.seconds)
            await repo.set_join_error(chat.id, "flood", until)
            log.warning("flood wait on join: %s s", e.seconds)
            await self._alert(
                f"FloodWait при вступлении: Telegram просит подождать {human_duration(e.seconds)}. "
                f"Вступления остановлены до {until:%Y-%m-%d %H:%M} UTC."
            )
            return f"flood@{until.isoformat()}"
        except errors.RPCError as e:
            if _is_stop(e):
                self.stopped = True
                until = now + STOP_BLOCK
                log.error("joining stopped: %s", type(e).__name__)
                await self._alert(
                    f"Вступления остановлены: {type(e).__name__}. "
                    "Проверь аккаунт-монитор (лимит чатов или заморозка, @SpamBot)."
                )
                return f"stopped@{until.isoformat()}"
            return await self._fail(repo, chat, f"error:{type(e).__name__}")

    async def _joined(self, repo: JobsRadarRepository, chat: JobChat, tg_chat_id: int, name: str) -> None:
        survivor = await repo.mark_joined(chat.id, tg_chat_id)
        keep = survivor or chat
        await self.state.add(tg_chat_id, ChatRef(keep.id, keep.username))
        log.info("joined chat: id=%s tg_chat_id=%s", keep.id, tg_chat_id)
        if self.on_joined:
            try:
                await self.on_joined(keep.id, tg_chat_id)
            except Exception:
                log.warning("on_joined hook failed: chat=%s", keep.id)
        await self._alert(f"Вступил: {name}")

    async def _fail(self, repo: JobsRadarRepository, chat: JobChat, error: str) -> str:
        """Stays approved; retried after ERROR_RETRY."""
        await repo.set_join_error(chat.id, error, self.clock() + ERROR_RETRY)
        await self._alert(f"Не удалось вступить в {_name(chat)}: {error}")
        return error

    async def _alert(self, text: str) -> None:
        if self.alert is None:
            return
        try:
            await self.alert(text)
        except Exception:
            log.warning("alert failed: %s", text[:80])
