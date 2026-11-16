"""Read-only Telegram monitor of the Jobs Source Radar: `python -m app.jobs_radar.monitor`.

Does not run migrations (the web service does). Does nothing unless JOBS_RADAR_ENABLED=true.
The account only reads and joins approved chats: no sending, replying, marking as read or typing.
"""
import asyncio
import contextlib
import logging
import signal
import sys
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.config import Settings, get_settings
from app.database.models import utcnow
from app.database.repositories.jobs_radar import JobsRadarRepository
from app.database.session import make_engine, make_sessionmaker
from app.jobs_radar import telegram
from app.jobs_radar.catchup import catch_up_all, set_baseline
from app.jobs_radar.classifier import get_classifier
from app.jobs_radar.digest import send_agency_digest
from app.jobs_radar.handler import IncomingMessage, Pipeline, handle_message
from app.jobs_radar.joiner import Joiner
from app.jobs_radar.metadata import MetadataCollector
from app.jobs_radar.notify import AdminNotifier
from app.jobs_radar.signals import Terms, load_terms, purge_old_signals
from app.jobs_radar.state import JoinedState

log = logging.getLogger("jobs_radar.monitor")

RECONCILE_EVERY_S = 300
DAILY_PURGE_DAYS = 30


def missing_settings(settings: Settings) -> list[str]:
    names = {"TG_API_ID": settings.tg_api_id, "TG_API_HASH": settings.tg_api_hash, "TG_SESSION": settings.tg_session}
    return [name for name, value in names.items() if not value]


def seconds_until_hour(now: datetime, hour: int) -> float:
    target = now.astimezone(UTC).replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


class Monitor:
    def __init__(self, settings: Settings, client: Any, sm: async_sessionmaker, bot: Any) -> None:
        self.settings, self.client, self.sm, self.bot = settings, client, sm, bot
        self.state = JoinedState()
        self.notifier = AdminNotifier(bot, settings.admin_ids)
        self.terms: Terms = ([], [])
        self.pipeline = Pipeline(self.state, sm, get_classifier(settings), lambda: self.terms)
        self.joiner = Joiner(
            sm=sm,
            state=self.state,
            join_fn=partial(telegram.join_chat, client),
            check_fn=partial(telegram.check_membership, client),
            daily_cap=settings.jobs_join_daily_cap,
            alert=self.notifier.alert,
            on_joined=self._on_joined,
        )
        self.metadata = MetadataCollector(
            sm=sm, client=client, daily_cap=settings.jobs_metadata_daily_cap, alert=self.notifier.alert
        )

    async def refresh(self) -> None:
        await self.state.reconcile(self.sm)
        async with self.sm() as session:
            self.terms = await load_terms(session)

    async def on_new_message(self, event: Any) -> None:
        """Telethon NewMessage callback. Cheap check first: nothing is looked up for chats we do not watch."""
        try:
            if event.chat_id not in self.state or getattr(event, "out", False):
                return
            message = event.message
            msg = IncomingMessage(
                chat_id=event.chat_id,
                message_id=message.id,
                text=message.message or "",
                date=message.date,
                chat_username=getattr(event.chat, "username", None),
            )
        except Exception:
            log.exception("failed to read event")
            return
        await handle_message(msg, self.pipeline)

    async def _on_joined(self, chat_id: int, tg_chat_id: int) -> None:
        await self.refresh()
        await set_baseline(self.client, self.pipeline, tg_chat_id)

    async def catch_up(self, only_chat: int | None = None) -> None:
        await catch_up_all(self.client, self.pipeline, only_chat=only_chat, alert=self.notifier.alert)

    async def daily_job(self) -> None:
        """Stats and scores, retention purges, agency digest. Each step is isolated."""
        steps = (
            ("recompute_stats", self._recompute),
            ("purge", self._purge),
            ("digest", self._digest),
        )
        for name, step in steps:
            try:
                await step()
            except Exception:
                log.exception("daily step failed: %s", name)

    async def _recompute(self) -> None:
        async with self.sm() as session:
            await JobsRadarRepository(session).recompute_stats(utcnow())
            await session.commit()

    async def _purge(self) -> None:
        async with self.sm() as session:
            removed = await purge_old_signals(session, self.settings.jobs_signal_retention_days)
            await JobsRadarRepository(session).purge_daily(DAILY_PURGE_DAYS)
            await session.commit()
        log.info("purged %d old signals", removed)

    async def _digest(self) -> None:
        async with self.sm() as session:
            await send_agency_digest(self.bot, session, self.settings.admin_ids)
            await session.commit()

    async def _reconcile_loop(self) -> None:
        while True:
            await asyncio.sleep(RECONCILE_EVERY_S)
            try:
                await self.refresh()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("reconcile failed")

    async def _daily_loop(self) -> None:
        while True:
            await asyncio.sleep(seconds_until_hour(datetime.now(UTC), self.settings.jobs_digest_hour))
            await self.daily_job()

    async def _startup_catch_up(self) -> None:
        try:
            await self.catch_up()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("startup catch-up failed")

    async def run(self, stop: asyncio.Event) -> None:
        from telethon import events

        await self.refresh()
        self.client.add_event_handler(self.on_new_message, events.NewMessage())
        tasks = [
            asyncio.create_task(self._reconcile_loop()),
            asyncio.create_task(self._daily_loop()),
            asyncio.create_task(self.joiner.run()),
            asyncio.create_task(self.metadata.run()),
            asyncio.create_task(self._startup_catch_up()),
        ]
        log.info("monitor ready: joined chats=%d", len(self.state))
        try:
            await stop.wait()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


def build_monitor(settings: Settings, client: Any, sm: async_sessionmaker, bot: Any) -> Monitor:
    return Monitor(settings, client, sm, bot)


def _make_engine(url: str) -> AsyncEngine:
    if url.startswith("sqlite"):
        return make_engine(url)
    return create_async_engine(url, pool_size=3, max_overflow=2, pool_pre_ping=True)


async def _run(settings: Settings) -> None:
    from aiogram import Bot
    from aiogram.client.session.aiohttp import AiohttpSession
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    engine = _make_engine(settings.database_url)
    session = AiohttpSession(proxy=settings.telegram_proxy) if settings.telegram_proxy else None
    bot = Bot(settings.bot_token, session=session)
    client = TelegramClient(
        StringSession(settings.tg_session.get_secret_value()),
        settings.tg_api_id,
        settings.tg_api_hash,
        flood_sleep_threshold=60,
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError, ValueError):
            loop.add_signal_handler(sig, stop.set)
    try:
        monitor = build_monitor(settings, client, make_sessionmaker(engine), bot)
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError("TG_SESSION is not authorized: run scripts/telegram_login.py")
        await client.get_dialogs()  # fills the entity cache
        run = asyncio.create_task(monitor.run(stop))
        await asyncio.wait({run, client.disconnected}, return_when=asyncio.FIRST_COMPLETED)
        stop.set()
        await asyncio.gather(run, return_exceptions=True)
    finally:
        with contextlib.suppress(Exception):
            await client.disconnect()
        with contextlib.suppress(Exception):
            await bot.session.close()
        with contextlib.suppress(Exception):
            await engine.dispose()


def main(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not settings.jobs_radar_enabled:
        log.info("JOBS_RADAR_ENABLED is false: monitor not started")
        return 0
    missing = missing_settings(settings)
    if missing:
        log.error("monitor not started: missing settings: %s", ", ".join(missing))
        return 1
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run(settings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
