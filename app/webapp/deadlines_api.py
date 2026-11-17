"""Personal deadlines for the Mini App ("My dates"). Same Telegram initData auth as the other APIs."""
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.middlewares.throttling import RateLimiter
from app.config import Settings
from app.database.repositories.deadlines import DeadlineError, DeadlineRepository, today_berlin


class DeadlineIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    due: date

    @field_validator("title")
    @classmethod
    def _t(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("too short")
        return v

    @field_validator("due")
    @classmethod
    def _d(cls, v: date) -> date:
        today = today_berlin()
        if v < today or v > today + timedelta(days=3 * 366):
            raise ValueError("date out of range")
        return v


def out(d) -> dict:
    return {"id": d.id, "title": d.title, "due": d.due.isoformat()}


def build_deadlines_router(settings: Settings, sm: async_sessionmaker, verify) -> APIRouter:
    r = APIRouter(prefix="/api/deadlines")
    limiter = RateLimiter(limit=20, window=60)

    def auth(x_telegram_init_data: Annotated[str, Header()]) -> int:
        return verify(x_telegram_init_data, settings.bot_token, settings.webapp_init_data_ttl).user.id

    def write_auth(uid: Annotated[int, Depends(auth)]) -> int:
        if not limiter.allow(uid):
            raise HTTPException(429, "rate_limited")
        return uid

    Uid = Annotated[int, Depends(auth)]
    WUid = Annotated[int, Depends(write_auth)]

    @r.get("")
    async def list_(uid: Uid):
        async with sm() as s:
            return [out(d) for d in await DeadlineRepository(s).for_user(uid, since=today_berlin())]

    @r.post("")
    async def add(body: DeadlineIn, uid: WUid):
        async with sm() as s:
            try:
                d = await DeadlineRepository(s).add(uid, body.title, body.due)
            except DeadlineError as e:
                raise HTTPException(e.status, e.code) from e
            await s.commit()
            return out(d)

    @r.delete("/{deadline_id}")
    async def remove(deadline_id: int, uid: WUid):
        async with sm() as s:
            try:
                await DeadlineRepository(s).remove(uid, deadline_id)
            except DeadlineError as e:
                raise HTTPException(e.status, e.code) from e
            await s.commit()
            return {"ok": True}

    return r
