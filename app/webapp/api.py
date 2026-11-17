"""Backend for the Telegram Mini App.

Every request must carry Telegram's signed initData in the `X-Telegram-Init-Data`
header. We verify the HMAC signature with the bot token, so a user can only read
and change their own profile.
"""
import hmac
import time
from pathlib import Path
from typing import Annotated, Literal

from aiogram.utils.web_app import WebAppInitData, safe_parse_webapp_init_data
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.data.regions import GERMAN_LEVELS, GOALS, LANDS, STATUSES
from app.data.guides import changes_json, guides_json
from app.data.sources_seed import TOPICS
from app.database.repositories.analytics import user_hash
from app.database.repositories.sources import SourceRepository
from app.database.repositories.users import UserRepository

STATIC = Path(__file__).parent / "static"
# New Mini App (webapp/, Vite build). Served at /app-v2 only when it has been built; / keeps the old app.
V2_DIST = Path(__file__).resolve().parents[2] / "webapp" / "dist"


def verify_init_data(init_data: str, bot_token: str, ttl: int, now: float | None = None) -> WebAppInitData:
    try:
        data = safe_parse_webapp_init_data(token=bot_token, init_data=init_data)
    except ValueError as e:
        raise HTTPException(401, "invalid init data") from e
    if not data.user:
        raise HTTPException(401, "no user")
    now = time.time() if now is None else now
    if now - data.auth_date.timestamp() > ttl:
        raise HTTPException(401, "init data expired")
    return data


class ProfileUpdate(BaseModel):
    language: str | None = None
    land: str | None = None
    city: str | None = Field(default=None, max_length=80)
    german_level: Literal[tuple(GERMAN_LEVELS)] | None = None  # type: ignore[valid-type]
    goal: Literal[tuple(GOALS)] | None = None  # type: ignore[valid-type]
    residence_status: Literal[tuple(STATUSES)] | None = None  # type: ignore[valid-type]
    broadcast_consent: bool | None = None

    @field_validator("land")
    @classmethod
    def _land(cls, v):
        if v is not None and v not in LANDS:
            raise ValueError("unknown land")
        return v

    @field_validator("city")
    @classmethod
    def _city(cls, v):
        if v is None:
            return None
        return " ".join(v.split()) or None


def create_app(settings: Settings, sessionmaker: async_sessionmaker, bot=None, dp=None,
               webhook: bool = False) -> FastAPI:
    app = FastAPI(title=f"{settings.bot_name} Mini App", docs_url=None, redoc_url=None, openapi_url=None)

    from app.webapp.jobs_api import build_jobs_router

    app.include_router(build_jobs_router(settings, sessionmaker, bot, verify_init_data))

    if webhook and bot is not None and dp is not None:
        @app.post("/tg/webhook")
        async def telegram_webhook(request: Request):
            secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if not hmac.compare_digest(secret, settings.webhook_token or ""):
                raise HTTPException(403, "forbidden")
            await dp.feed_webhook_update(bot, await request.json())
            return {"ok": True}

    def auth(x_telegram_init_data: Annotated[str, Header()]) -> WebAppInitData:
        return verify_init_data(x_telegram_init_data, settings.bot_token, settings.webapp_init_data_ttl)

    Auth = Annotated[WebAppInitData, Depends(auth)]

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    if (V2_DIST / "index.html").exists():
        app.mount("/app-v2", StaticFiles(directory=V2_DIST, html=True), name="app-v2")

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/api/meta")
    async def meta():
        return {
            "bot_name": settings.bot_name,
            "languages": settings.languages,
            "lands": LANDS,
            "levels": GERMAN_LEVELS,
            "goals": GOALS,
            "statuses": STATUSES,
            "topics": {k: {"uk": v[0], "ru": v[1]} for k, v in TOPICS.items()},
            "guides": guides_json(),
            "changes": changes_json(),
            "employment": ["full", "part", "mini", "any"],
            "employer_price_eur": settings.employer_price_eur,
            "employer_pilot_days": settings.employer_pilot_days,
            "submission_limit_per_hour": settings.submission_limit_per_hour,
        }

    @app.get("/api/housing")
    async def housing():
        from app.data import housing as h

        return {"terms": h.TERMS, "checklist": h.CHECKLIST, "safety": h.SAFETY, "sources": h.SOURCES,
                "checked": h.CHECKED}

    @app.get("/api/me")
    async def get_me(data: Auth):
        async with sessionmaker() as s:
            repo = UserRepository(s)
            user = await repo.get_or_create(data.user.id)
            out = await repo.export(user)
            await s.commit()
            out.pop("telegram_id", None)
            return out

    @app.patch("/api/me")
    async def patch_me(body: ProfileUpdate, data: Auth):
        fields = body.model_dump(exclude_unset=True)
        if "language" in fields and fields["language"] not in settings.languages:
            raise HTTPException(422, "unsupported language")
        async with sessionmaker() as s:
            repo = UserRepository(s)
            user = await repo.get_or_create(data.user.id)
            if user.is_blocked:
                raise HTTPException(403, "blocked")
            await repo.update_profile(user, **fields)
            if user.language and user.german_level and user.goal:
                user.is_registered = True
            await s.commit()
        return {"ok": True}

    @app.delete("/api/me")
    async def delete_me(data: Auth):
        async with sessionmaker() as s:
            repo = UserRepository(s)
            user = await repo.get(data.user.id)
            if user:
                await repo.delete_all(user, user_hash(user.telegram_id, settings.analytics_salt))
                await s.commit()
        return {"ok": True}

    @app.get("/api/sources")
    async def get_sources():
        async with sessionmaker() as s:
            items = await SourceRepository(s).all_active()
        return [
            {"topic": i.topic, "title_uk": i.title_uk, "title_ru": i.title_ru, "url": i.url,
             "checked_at": i.checked_at.date().isoformat() if i.checked_at else None}
            for i in items
        ]

    return app
