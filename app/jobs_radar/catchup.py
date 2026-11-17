"""Catch-up after downtime. Telethon's catch_up does not work with StringSession (pts are not persisted),
so we read messages newer than the last processed one ourselves. Read-only: only get_messages,
which does not mark anything as read."""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from telethon.errors import ChannelInvalidError, ChannelPrivateError, FloodWaitError, UserBannedInChannelError

from app.database.repositories.jobs_radar import JobsRadarRepository
from app.jobs_radar.handler import IncomingMessage, Pipeline, handle_message

log = logging.getLogger(__name__)

CATCHUP_LIMIT = 200
CHAT_PAUSE_S = 1.0
_LOST_ERRORS = (ChannelPrivateError, ChannelInvalidError, UserBannedInChannelError)

Alert = Callable[[str], Awaitable[None]]


def _is_lost_access(exc: Exception) -> bool:
    if isinstance(exc, _LOST_ERRORS):
        return True
    return isinstance(exc, ValueError) and "Could not find the input entity" in str(exc)


async def catch_up_chat(client: Any, pipeline: Pipeline, tg_chat_id: int) -> int:
    """Re-read messages newer than last_message_id, oldest first. A chat without last_message_id is skipped."""
    ref = pipeline.state.get(tg_chat_id)
    if ref is None:
        return 0
    async with pipeline.sm() as session:
        chat = await JobsRadarRepository(session).get(ref.id)
    last_id = chat.last_message_id if chat else None
    if last_id is None:
        return 0
    messages = await client.get_messages(tg_chat_id, min_id=last_id, limit=CATCHUP_LIMIT)
    if len(messages) >= CATCHUP_LIMIT:
        log.warning("catch-up hit the limit (%d): chat=%s, gap may be larger", CATCHUP_LIMIT, tg_chat_id)
    for m in sorted(messages, key=lambda m: m.id):
        await handle_message(
            IncomingMessage(
                chat_id=tg_chat_id,
                message_id=m.id,
                text=getattr(m, "message", None) or "",
                date=m.date,
                chat_username=ref.username,
            ),
            pipeline,
        )
    return len(messages)


async def set_baseline(client: Any, pipeline: Pipeline, tg_chat_id: int) -> None:
    """After joining: remember the newest message id (not processed), so catch-up starts from the join moment."""
    ref = pipeline.state.get(tg_chat_id)
    if ref is None:
        return
    messages = await client.get_messages(tg_chat_id, limit=1)
    if not messages:
        return
    async with pipeline.sm() as session:
        await JobsRadarRepository(session).set_last_message_id(ref.id, max(m.id for m in messages))
        await session.commit()


async def catch_up_all(
    client: Any,
    pipeline: Pipeline,
    *,
    only_chat: int | None = None,
    alert: Alert | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    chats = [only_chat] if only_chat is not None else pipeline.state.ids()
    for tg_chat_id in chats:
        ref = pipeline.state.get(tg_chat_id)
        try:
            n = await catch_up_chat(client, pipeline, tg_chat_id)
            if n:
                log.info("catch-up: chat=%s messages=%d", tg_chat_id, n)
        except FloodWaitError as exc:
            log.warning("catch-up stopped: flood wait %s s", exc.seconds)
            break
        except Exception as exc:
            if ref is not None and _is_lost_access(exc):
                await _mark_lost(ref.id, tg_chat_id, pipeline, alert)
            else:
                log.exception("catch-up failed: chat=%s", tg_chat_id)
        await sleep(CHAT_PAUSE_S)


async def _mark_lost(chat_id: int, tg_chat_id: int, pipeline: Pipeline, alert: Alert | None) -> None:
    async with pipeline.sm() as session:
        repo = JobsRadarRepository(session)
        chat = await repo.get(chat_id)
        name = (chat.title or (f"@{chat.username}" if chat.username else str(chat_id))) if chat else str(chat_id)
        await repo.mark_lost(chat_id)
        await session.commit()
    await pipeline.state.remove(tg_chat_id)
    log.warning("chat access lost: chat=%s", tg_chat_id)
    if alert:
        try:
            await alert(f"Потерян доступ к чату: {name}. Аккаунт удалён или забанен, чат переведён в rejected.")
        except Exception:
            log.warning("alert failed")
