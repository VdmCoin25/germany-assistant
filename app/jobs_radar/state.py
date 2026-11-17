"""In-memory set of joined chats: the only chats the monitor listens to."""
import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database.repositories.jobs_radar import JobsRadarRepository

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatRef:
    id: int  # job_chats.id
    username: str | None


class JoinedState:
    def __init__(self) -> None:
        self._chats: dict[int, ChatRef] = {}  # marked tg chat id (-100... for supergroups) -> ref
        self._lock = asyncio.Lock()  # a reconcile snapshot must not overwrite a fresh add()

    def get(self, tg_chat_id: int) -> ChatRef | None:
        return self._chats.get(tg_chat_id)

    def __contains__(self, tg_chat_id: int) -> bool:
        return tg_chat_id in self._chats

    def __len__(self) -> int:
        return len(self._chats)

    def ids(self) -> list[int]:
        return list(self._chats)

    async def add(self, tg_chat_id: int, ref: ChatRef) -> None:
        async with self._lock:
            self._chats[tg_chat_id] = ref

    async def remove(self, tg_chat_id: int) -> None:
        async with self._lock:
            self._chats.pop(tg_chat_id, None)

    async def reconcile(self, sm: async_sessionmaker) -> None:
        async with self._lock:
            async with sm() as session:
                chats = await JobsRadarRepository(session).list_joined()
            self._chats = {c.tg_chat_id: ChatRef(c.id, c.username) for c in chats}
        log.info("joined chats reconciled: %d", len(self._chats))
