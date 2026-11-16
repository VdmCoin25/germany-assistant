"""Message handling without Telethon types: monitor.py and catchup.py convert messages to IncomingMessage.

The text is used in memory only (links, classifier); it is never stored. There is no author field on purpose.
"""
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database.repositories.jobs_radar import JobsRadarRepository
from app.jobs_radar.classifier import JobClassifier
from app.jobs_radar.discovery import extract_links
from app.jobs_radar.signals import Terms, process_message
from app.jobs_radar.state import JoinedState
from app.jobs_radar.tglinks import message_link

log = logging.getLogger(__name__)


@dataclass
class IncomingMessage:
    chat_id: int  # marked tg chat id
    message_id: int
    text: str
    date: datetime
    chat_username: str | None = None


@dataclass
class Pipeline:
    state: JoinedState
    sm: async_sessionmaker
    classifier: JobClassifier
    get_terms: Callable[[], Terms]


async def handle_message(msg: IncomingMessage, pipeline: Pipeline) -> None:
    """Never raises: one bad message must not stop the monitor."""
    try:
        ref = pipeline.state.get(msg.chat_id)
        if ref is None:
            return
        date = msg.date if msg.date.tzinfo else msg.date.replace(tzinfo=UTC)
        async with pipeline.sm() as session:
            repo = JobsRadarRepository(session)
            chat = await repo.get(ref.id)
            if chat is None or (chat.last_message_id is not None and msg.message_id <= chat.last_message_id):
                return  # already seen (live message vs catch-up)
            await repo.bump_daily(ref.id, date.astimezone(UTC).date())
            await repo.set_last_message_id(ref.id, msg.message_id)
            text = (msg.text or "").strip()
            if text:
                await repo.add_candidates(extract_links(text), via_chat_id=ref.id)
                link = message_link(msg.chat_id, msg.message_id, msg.chat_username or ref.username)
                if link:
                    await process_message(
                        session, pipeline.classifier, pipeline.get_terms(),
                        chat_id=ref.id, message_link=link, text=text,
                    )
            await session.commit()
    except Exception:
        log.exception("message handling failed: chat=%s msg=%s", msg.chat_id, msg.message_id)
