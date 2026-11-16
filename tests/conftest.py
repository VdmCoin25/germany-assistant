import itertools
from datetime import datetime

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import CallbackQuery, Chat, Message, Update, User as TgUser
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database.models import Base
from app.database.repositories.sources import SourceRepository
from app.admin.handlers import router as admin_router
from app.admin.moderation import router as moderation_router
from app.bot.handlers import common, jobs as jobs_h, menu, settings as settings_h, start
from app.main import build_dispatcher

ADMIN_ID = 999
TOKEN = "42:TEST-TOKEN"


class FakeSession(BaseSession):
    """Records Bot API calls instead of sending them to Telegram."""

    def __init__(self):
        super().__init__()
        self.calls = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        ret = getattr(method, "__returning__", None)
        if ret is Message:
            return Message(message_id=1, date=datetime.now(), chat=Chat(id=1, type="private"),
                           text=getattr(method, "text", None))
        return True

    async def stream_content(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError

    async def close(self):
        pass

    def texts(self) -> list[str]:
        return [c.text for c in self.calls if getattr(c, "text", None)]

    def clear(self):
        self.calls.clear()


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, bot_token=TOKEN, database_url="sqlite+aiosqlite://",
                    admin_ids=[ADMIN_ID], analytics_salt="test-salt", rate_limit_per_minute=1000)


@pytest.fixture
async def sm():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool,
                                 connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await SourceRepository(s).seed_if_empty()
        await s.commit()
    yield maker
    await engine.dispose()


class Harness:
    _ids = itertools.count(1)

    def __init__(self, settings, sm):
        self.session = FakeSession()
        self.bot = Bot(TOKEN, session=self.session)
        # Routers are module-level singletons; detach them so each test gets a fresh Dispatcher.
        for r in (admin_router, moderation_router, jobs_h.router, start.router, common.router, menu.router, settings_h.router, common.fallback_router):
            r._parent_router = None
        self.dp = build_dispatcher(settings, sm)

    def _user(self, uid):
        return TgUser(id=uid, is_bot=False, first_name="Test", language_code="uk")

    def _msg(self, uid, text):
        return Message(message_id=next(self._ids), date=datetime.now(), chat=Chat(id=uid, type="private"),
                       from_user=self._user(uid), text=text)

    async def send(self, uid: int, text: str):
        await self.dp.feed_update(self.bot, Update(update_id=next(self._ids), message=self._msg(uid, text)))

    async def press(self, uid: int, data: str):
        cb = CallbackQuery(id=str(next(self._ids)), from_user=self._user(uid), chat_instance="ci",
                           data=data, message=self._msg(uid, "x"))
        await self.dp.feed_update(self.bot, Update(update_id=next(self._ids), callback_query=cb))


@pytest.fixture
def h(settings, sm) -> Harness:
    return Harness(settings, sm)
