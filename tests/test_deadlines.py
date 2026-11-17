"""My dates: API, reminder schedule (3 days / day before, catch-up, quiet hours), GDPR."""
from datetime import datetime, timedelta

import httpx
from aiogram import Bot
from aiogram.methods import SendMessage
from sqlalchemy import func, select

from app.database.models import Deadline, User
from app.database.repositories.deadlines import BERLIN, DeadlineRepository, today_berlin
from app.database.repositories.users import UserRepository
from app.services.reminders import send_due
from app.webapp.api import create_app
from tests.conftest import TOKEN, FakeSession
from tests.test_units import make_init_data

ME, OTHER = 4001, 4002


def hdr(uid):
    return {"X-Telegram-Init-Data": make_init_data(uid)}


async def test_api_add_list_delete(settings, sm):
    app = create_app(settings, sm)
    day = (today_berlin() + timedelta(days=5)).isoformat()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/deadlines", headers=hdr(ME), json={"title": "  Термін у  Jobcenter ", "due": day})
        assert r.status_code == 200 and r.json()["title"] == "Термін у Jobcenter"
        did = r.json()["id"]
        assert [d["id"] for d in (await c.get("/api/deadlines", headers=hdr(ME))).json()] == [did]
        assert (await c.get("/api/deadlines", headers=hdr(OTHER))).json() == []
        past = (today_berlin() - timedelta(days=1)).isoformat()
        assert (await c.post("/api/deadlines", headers=hdr(ME), json={"title": "Старе", "due": past})).status_code == 422
        assert (await c.delete(f"/api/deadlines/{did}", headers=hdr(OTHER))).status_code == 404
        assert (await c.delete(f"/api/deadlines/{did}", headers=hdr(ME))).status_code == 200


def at(day, hour=10):
    return datetime(day.year, day.month, day.day, hour, tzinfo=BERLIN)


async def test_reminders_three_days_then_day_before_with_catch_up(settings, sm):
    fake = FakeSession()
    bot = Bot(TOKEN, session=fake)
    today = today_berlin()
    async with sm() as s:
        repo = DeadlineRepository(s)
        await repo.add(ME, "Лист з Jobcenter", today + timedelta(days=3))
        await s.commit()

    assert await send_due(bot, sm, "uk", now=at(today, 23)) == 0          # quiet at night
    assert await send_due(bot, sm, "uk", now=at(today)) == 1               # 3 days before
    assert "через 3 дн." in [m for m in fake.calls if isinstance(m, SendMessage)][-1].text
    assert await send_due(bot, sm, "uk", now=at(today)) == 0               # not twice
    # the server slept through day 2 and wakes on the day before: one "tomorrow" message
    assert await send_due(bot, sm, "uk", now=at(today + timedelta(days=2))) == 1
    assert "завтра" in [m for m in fake.calls if isinstance(m, SendMessage)][-1].text
    assert await send_due(bot, sm, "uk", now=at(today + timedelta(days=3))) == 0


async def test_deadlines_go_with_gdpr_delete(settings, sm):
    async with sm() as s:
        await DeadlineRepository(s).add(ME, "Kita", today_berlin() + timedelta(days=10))
        s.add(User(telegram_id=ME, language="uk"))
        await s.commit()
        users = UserRepository(s)
        u = await users.get(ME)
        assert (await users.export(u))["deadlines"][0]["title"] == "Kita"
        await users.delete_all(u, "hash")
        await s.commit()
        assert await s.scalar(select(func.count(Deadline.id))) == 0
