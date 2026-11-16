from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.database.repositories.analytics import AnalyticsRepository
from app.database.repositories.sources import SourceRepository
from app.database.repositories.users import UserRepository


class DbMiddleware(BaseMiddleware):
    """Opens one DB session per update, loads the user and their language."""

    def __init__(self, sessionmaker: async_sessionmaker, settings: Settings):
        self.sm = sessionmaker
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.sm() as session:
            users = UserRepository(session)
            data.update(
                session=session,
                users=users,
                analytics=AnalyticsRepository(session, self.settings.analytics_salt),
                sources=SourceRepository(session),
            )
            tg_user = data.get("event_from_user")
            user = None
            if tg_user and not tg_user.is_bot:
                user = await users.get_or_create(tg_user.id)
                await users.touch(user)
                if user.is_blocked and tg_user.id not in self.settings.admin_ids:
                    await session.commit()
                    return None
            data["user"] = user
            data["lang"] = (user.language if user and user.language else self.settings.default_language)
            result = await handler(event, data)
            await session.commit()
            return result
