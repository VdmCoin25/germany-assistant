"""Entry point: runs the Telegram bot (long polling) and the Mini App backend together."""
import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.admin.handlers import router as admin_router
from app.admin.moderation import router as moderation_router
from app.bot.handlers import common, jobs as jobs_h, menu, settings as settings_h, start
from app.bot.middlewares.db import DbMiddleware
from app.bot.middlewares.throttling import RateLimiter, ThrottlingMiddleware
from app.config import Settings, get_settings
from app.database.repositories.sources import SourceRepository
from app.database.session import make_engine, make_sessionmaker
from app.i18n import t

log = logging.getLogger("app")

COMMANDS = {
    "uk": [("start", "Почати"), ("menu", "Головне меню"), ("help", "Допомога"),
           ("settings", "Налаштування"), ("privacy", "Конфіденційність"), ("delete_my_data", "Видалити мої дані")],
    "ru": [("start", "Начать"), ("menu", "Главное меню"), ("help", "Помощь"),
           ("settings", "Настройки"), ("privacy", "Конфиденциальность"), ("delete_my_data", "Удалить мои данные")],
}


def make_storage(settings: Settings) -> BaseStorage:
    if settings.redis_url:
        from aiogram.fsm.storage.redis import RedisStorage

        return RedisStorage.from_url(settings.redis_url)
    return MemoryStorage()


def build_dispatcher(settings: Settings, sessionmaker: async_sessionmaker, storage: BaseStorage | None = None) -> Dispatcher:
    dp = Dispatcher(storage=storage or MemoryStorage(), settings=settings)
    dp.update.outer_middleware(DbMiddleware(sessionmaker, settings))
    throttle = ThrottlingMiddleware(RateLimiter(settings.rate_limit_per_minute), exempt=set(settings.admin_ids))
    dp.message.middleware(throttle)
    dp.callback_query.middleware(throttle)
    # Order matters: admin and specific routers first, fallback last.
    dp.include_routers(admin_router, moderation_router)
    if settings.jobs_radar_enabled:
        from app.jobs_radar.admin import router as jobs_radar_router

        dp.include_router(jobs_radar_router)
    dp.include_routers(start.router, jobs_h.router, common.router, menu.router, settings_h.router, common.fallback_router)
    dp.errors.register(common.on_error)
    return dp


async def setup_bot_ui(bot: Bot, settings: Settings) -> None:
    for lang, cmds in COMMANDS.items():
        await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in cmds], language_code=lang)
    await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in COMMANDS["uk"]])
    if settings.webapp_url:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
            text=t("uk", "open_app").split(" ", 1)[-1], web_app=WebAppInfo(url=settings.webapp_url)))


async def with_retry(call, what: str, attempts: int = 5, delay: float = 3.0):
    """Telegram sometimes answers 502/timeouts for a minute. A deploy must not die on that."""
    for i in range(1, attempts + 1):
        try:
            return await call()
        except Exception as e:  # noqa: BLE001
            if i == attempts:
                raise
            log.warning("%s failed (%s), retry %s/%s", what, type(e).__name__, i, attempts - 1)
            await asyncio.sleep(delay * i)


async def keepalive(url: str, interval: int) -> None:
    """Ping our own public URL. Requests go through the host's router, which counts as traffic."""
    import aiohttp

    await asyncio.sleep(60)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as http:
        while True:
            try:
                async with http.get(f"{url}/health") as r:
                    if r.status != 200:
                        log.warning("keepalive: HTTP %s", r.status)
            except Exception as e:  # noqa: BLE001
                log.warning("keepalive failed: %s", type(e).__name__)
            await asyncio.sleep(interval)


async def run() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # aiogram logs update contents at DEBUG; keep it quiet to avoid leaking personal data.
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)

    engine = make_engine(settings.database_url)
    sm = make_sessionmaker(engine)
    async with sm() as s:
        added = await SourceRepository(s).seed_if_empty()
        await s.commit()
        if added:
            log.info("Seeded %s info sources", added)

    session = AiohttpSession(proxy=settings.telegram_proxy) if settings.telegram_proxy else None
    bot = Bot(settings.bot_token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher(settings, sm, make_storage(settings))
    me = await with_retry(bot.get_me, "get_me")
    log.info("Bot @%s started", me.username)
    try:   # commands and menu button are cosmetic: never block startup on them
        await with_retry(lambda: setup_bot_ui(bot, settings), "setup_bot_ui", attempts=3)
    except Exception as e:  # noqa: BLE001
        log.warning("setup_bot_ui skipped: %s", type(e).__name__)

    from app.webapp.api import create_app

    allowed = dp.resolve_used_update_types()
    tasks = []
    if settings.webhook_mode:
        if not (settings.webapp_url and settings.webhook_secret):
            raise RuntimeError("WEBHOOK_MODE needs WEBAPP_URL (or RENDER_EXTERNAL_URL) and WEBHOOK_SECRET")
        await with_retry(lambda: bot.set_webhook(f"{settings.webapp_url}/tg/webhook", secret_token=settings.webhook_token,
                                                 allowed_updates=allowed, drop_pending_updates=False), "set_webhook")
        log.info("Webhook mode")
        app = create_app(settings, sm, bot=bot, dp=dp, webhook=True)
    else:
        await bot.delete_webhook(drop_pending_updates=False)
        tasks.append(dp.start_polling(bot, allowed_updates=allowed))
        app = create_app(settings, sm, bot=bot)
    if settings.run_webapp or settings.webhook_mode:
        server = uvicorn.Server(uvicorn.Config(app, host=settings.webapp_host, port=settings.webapp_port,
                                               log_level="warning", access_log=False))
        tasks.append(server.serve())
    from app.services.reminders import reminders_loop

    tasks.append(reminders_loop(bot, sm, settings.default_language))
    if settings.webapp_url and settings.keepalive_interval_sec > 0:
        tasks.append(keepalive(settings.webapp_url, settings.keepalive_interval_sec))
    try:
        await asyncio.gather(*tasks)
    finally:
        await bot.session.close()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
