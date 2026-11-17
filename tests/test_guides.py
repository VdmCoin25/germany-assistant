"""Reference answers: every rule has an official source and a check date, both languages match."""
import httpx
from sqlalchemy import func, select

from app.data.guides import CHANGES, GUIDES
from app.data.sources_seed import SEED, TOPICS
from app.database.models import InfoSource
from app.database.repositories.sources import SourceRepository
from app.webapp.api import create_app


def test_guides_are_sourced_and_bilingual():
    for key, g in GUIDES.items():
        assert key in TOPICS, key
        assert len(g["uk"]) == len(g["ru"]) and 1 <= len(g["uk"]) <= 5
        title, url = g["source"]
        assert title and url.startswith("https://")
    dates = [c["date"] for c in CHANGES]
    assert dates == sorted(dates, reverse=True)
    assert all(c["topic"] in GUIDES for c in CHANGES)
    assert not any("Bürgergeld" in v[0] or "Bürgergeld" in v[1] for v in TOPICS.values())


async def test_meta_serves_guides_and_changes(settings, sm):
    app = create_app(settings, sm)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        meta = (await c.get("/api/meta")).json()
    assert meta["guides"]["residence"]["checked"] == "2026-11-17"
    assert meta["guides"]["jobcenter"]["source"]["url"].startswith("https://")
    assert meta["changes"][0]["date"] >= meta["changes"][-1]["date"]


async def test_seed_adds_new_links_without_touching_old(sm):
    async with sm() as s:
        repo = SourceRepository(s)
        await repo.seed_if_empty()
        row = await s.scalar(select(InfoSource).limit(1))
        row.is_active = False                       # an admin disabled it
        await s.execute(InfoSource.__table__.delete().where(InfoSource.topic == "safety"))
        await s.commit()
        added = await repo.seed_if_empty()
        await s.commit()
        assert added == sum(1 for x in SEED if x["topic"] == "safety")
        assert (await s.get(InfoSource, row.id)).is_active is False
        assert await s.scalar(select(func.count(InfoSource.id))) == len(SEED)
