"""In-memory stand-in for the Telethon client, used only by the offline demo (`app.jobs_radar.demo`).

It answers exactly the calls the real radar code makes: get_entity, get_permissions, get_messages and the
requests Join/Import/CheckChatInvite/GetFullChannel. There is no network, no session and no credentials.
It is read-only like the real monitor: nothing here can send, post, reply or mark anything as read.
"""
from collections.abc import Callable
from datetime import datetime, timedelta
from types import SimpleNamespace

from telethon import errors
from telethon.tl.functions.channels import GetFullChannelRequest, JoinChannelRequest
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.types import Channel, ChatInvite, ChatPhotoEmpty, User

from app.data.jobs_radar_demo import DemoChat, DemoMessage

FLOOD_SECONDS = 5400
FIRST_MESSAGE_ID = 1000
_ID_BASE = 1_000_000_000


class DemoClient:
    def __init__(
        self,
        chats: tuple[DemoChat, ...],
        messages: list[DemoMessage],
        clock: Callable[[], datetime],
        day_start: Callable[[int], datetime],
    ) -> None:
        self.clock = clock
        self._chats = list(chats)
        self._by_name = {c.username: c for c in self._chats if c.username}
        self._by_hash = {c.invite_hash: c for c in self._chats if c.invite_hash}
        self._raw_id = {id(c): _ID_BASE + i for i, c in enumerate(self._chats, 1)}
        self._flooded: set[int] = set()
        self.joined: set[int] = set()  # raw ids of chats we "are a member of"
        self.history: dict[int, list[SimpleNamespace]] = {}  # marked tg chat id -> messages, oldest first
        self.baselines: dict[int, int] = {}  # marked tg chat id -> newest message id seen right after joining
        self.served_by_catchup: dict[int, int] = {}
        self.calls: list[str] = []  # names of requests, for the report
        self._load(messages, day_start)

    # --- scenario ---

    def _load(self, messages: list[DemoMessage], day_start: Callable[[int], datetime]) -> None:
        slots: dict[tuple, int] = {}
        for m in sorted(messages, key=lambda m: (m.chat, m.day, m.hour)):  # stable: keeps the order in the data file
            chat = self._by_name[m.chat]
            raw = self._raw_id[id(chat)]
            rank = slots[(m.chat, m.day, m.hour)] = slots.get((m.chat, m.day, m.hour), -1) + 1
            date = day_start(m.day) + timedelta(hours=m.hour, minutes=5 + 10 * rank)
            items = self.history.setdefault(-(10**12) - raw, [])
            items.append(SimpleNamespace(
                id=FIRST_MESSAGE_ID + len(items), message=m.text, date=date, spec=m,
            ))

    def tg_id(self, chat: DemoChat) -> int:
        return -(10**12) - self._raw_id[id(chat)]

    def chat_of(self, tg_chat_id: int) -> DemoChat | None:
        for c in self._chats:
            if self.tg_id(c) == tg_chat_id:
                return c
        return None

    def due(self, since: datetime, until: datetime) -> list[tuple[DemoChat, SimpleNamespace]]:
        """Messages posted in (since, until], oldest first. The demo driver plays the role of Telethon's event loop."""
        out = []
        for tg_id, items in self.history.items():
            chat = self.chat_of(tg_id)
            out += [(chat, m) for m in items if since < m.date <= until]
        return sorted(out, key=lambda x: x[1].date)

    # --- what the real code calls ---

    def _entity(self, chat: DemoChat):
        raw = self._raw_id[id(chat)]
        if chat.kind == "user":
            return User(id=raw)
        return Channel(
            id=raw, photo=ChatPhotoEmpty(), date=self.clock(), title=chat.title,
            megagroup=chat.kind != "channel", broadcast=chat.kind == "channel",
        )

    async def get_entity(self, ident):
        if isinstance(ident, int):
            chat = self.chat_of(ident)
        else:
            chat = self._by_name.get(str(ident).lower())
        if chat is None or chat.kind in ("dead", "invite"):
            raise errors.UsernameNotOccupiedError(request=None)
        return self._entity(chat)

    async def get_permissions(self, entity, user="me"):
        if entity.id not in self.joined:
            raise errors.UserNotParticipantError(request=None)
        return SimpleNamespace(is_banned=False)

    async def get_dialogs(self, *args, **kwargs):
        return []

    async def get_messages(self, entity, *, min_id: int = 0, limit: int = 1):
        """Newest first, like Telethon. Only messages posted up to the simulated "now" exist."""
        now = self.clock()
        items = [m for m in self.history.get(entity, []) if m.date <= now and m.id > min_id]
        items.sort(key=lambda m: m.id, reverse=True)
        items = items[:limit]
        if min_id:
            self.served_by_catchup[entity] = self.served_by_catchup.get(entity, 0) + len(items)
        elif limit == 1 and items:
            self.baselines[entity] = items[0].id
        return items

    async def __call__(self, request):
        name = type(request).__name__
        self.calls.append(name)
        if isinstance(request, JoinChannelRequest):
            chat = self.chat_of(-(10**12) - request.channel.id)
            if chat.join == "flood_once" and id(chat) not in self._flooded:
                self._flooded.add(id(chat))
                raise errors.FloodWaitError(request=None, capture=FLOOD_SECONDS)
            self.joined.add(request.channel.id)
            return SimpleNamespace(chats=[request.channel])
        if isinstance(request, ImportChatInviteRequest):
            chat = self._by_hash.get(request.hash)
            if chat is None:
                raise errors.InviteHashInvalidError(request=None)
            if chat.join == "request_sent":
                raise errors.InviteRequestSentError(request=None)
            self.joined.add(self._raw_id[id(chat)])
            return SimpleNamespace(chats=[self._entity(chat)])
        if isinstance(request, CheckChatInviteRequest):
            chat = self._by_hash.get(request.hash)
            if chat is None or chat.kind == "dead":
                raise errors.ChannelPrivateError(request=None)  # an expired private link: the row is kept
            return ChatInvite(
                title=chat.title, photo=ChatPhotoEmpty(), participants_count=chat.members, participants=[],
                color=0, about=chat.about, broadcast=False, megagroup=True,
            )
        if isinstance(request, GetFullChannelRequest):
            chat = self.chat_of(-(10**12) - request.channel.id)
            return SimpleNamespace(full_chat=SimpleNamespace(participants_count=chat.members, about=chat.about))
        raise RuntimeError(f"DemoClient does not support {name}")
