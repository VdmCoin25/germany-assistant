import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.i18n import t


class RateLimiter:
    """Sliding-window limiter, in memory (one bot process). Swap for Redis when scaling out."""

    def __init__(self, limit: int, window: float = 60.0):
        self.limit = limit
        self.window = window
        self.hits: dict[int, deque] = defaultdict(deque)
        self.warned: dict[int, float] = {}

    def allow(self, key: int, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True

    def should_warn(self, key: int, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if now - self.warned.get(key, -1e9) > self.window:
            self.warned[key] = now
            return True
        return False


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, limiter: RateLimiter, exempt: set[int] | None = None):
        self.limiter = limiter
        self.exempt = exempt or set()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user and tg_user.id not in self.exempt and not self.limiter.allow(tg_user.id):
            if self.limiter.should_warn(tg_user.id):
                text = t(data.get("lang"), "rate_limited")
                if isinstance(event, Message):
                    await event.answer(text)
                elif isinstance(event, CallbackQuery):
                    await event.answer(text, show_alert=True)
            return None
        return await handler(event, data)
