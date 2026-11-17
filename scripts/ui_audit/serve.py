"""Serve the Mini App backend for UI screenshots with TEST settings only.

Never reads .env and never uses the real bot token. Usage:
    python scripts/ui_audit/serve.py <sqlite_path> <port> [--seed filled|empty]
"""
import asyncio
import sys

import uvicorn

from app.config import Settings
from app.database.models import Base
from app.database.repositories.jobs import JobsRepository
from app.database.repositories.sources import SourceRepository
from app.database.repositories.users import UserRepository
from app.database.session import make_engine, make_sessionmaker
from app.webapp.api import create_app

TEST_TOKEN = "42:TEST-TOKEN"


async def seed(sm, kind: str) -> None:
    async with sm() as s:
        await SourceRepository(s).seed_if_empty()
        if kind == "filled":
            users = UserRepository(s)
            for tg in (2001, 3001):
                u = await users.get_or_create(tg)
                u.language, u.land, u.city, u.german_level, u.is_registered = "uk", "BE", "Berlin", "A2", True
            j = JobsRepository(s)
            kw = dict(pilot_days=30, vacancy_days=30)
            p = await j.upsert_seeker(2001, position="Кухар / помічник кухаря", land="BE", city="Berlin",
                                      german_level="A2", employment="full", shifts_ok=True,
                                      experience="5 років кухарем у ресторані в Києві.\nГарячий цех.",
                                      about="Пунктуальний, швидко вчуся.")
            await j.moderate("seeker", p.id, True, **kw)
            e = await j.upsert_employer(3001, company="Muster Gastro GmbH", address="Hauptstr. 1, 10115 Berlin",
                                        register_no="HRB 12345 B", contact_person="Anna Muster",
                                        contact="jobs@muster.example")
            await j.moderate("employer", e.id, True, **kw)
            v1 = await j.create_vacancy(3001, title="Koch (m/w/d)", land="BE", city="Berlin", german_level="A2",
                                        employment="full", salary="15 €/год",
                                        description="Шукаємо кухаря в ресторан у Mitte. Повна зайнятість, 5 днів на тиждень.\nНавчання на місці.")
            await j.moderate("vacancy", v1.id, True, **kw)
            v2 = await j.create_vacancy(3001, title="Küchenhilfe, Minijob", land="BE", city="Berlin",
                                        employment="mini",
                                        description="Допомога на кухні у вихідні, 2 зміни на тиждень по 6 годин.")
            await j.moderate("vacancy", v2.id, True, **kw)
            c = await j.offer(3001, p.id, "Добрий день! Запрошуємо на пробний день у четвер о 10:00.", v1.id)
            await j.moderate("contact", c.id, True, **kw)
            # one user per step of the job route, for the new Mini App (users 2002-2005)
            def seeker(tg, pos):
                return j.upsert_seeker(tg, position=pos, land="BE", city="Berlin", german_level="A1", employment="any",
                                       shifts_ok=False, experience="2 роки на складі.", about=None)
            for tg in (2002, 2003, 2004, 2005, 2006):
                u = await users.get_or_create(tg)
                u.language, u.land, u.city, u.is_registered = "uk", "BE", "Berlin", True
            await seeker(2002, "Комплектувальник на склад")                          # in review
            p3 = await seeker(2003, "Прибиральниця")                                  # rejected
            await j.moderate("seeker", p3.id, False, **kw)
            p4 = await seeker(2004, "Водій категорії B")                               # published, no offers
            await j.moderate("seeker", p4.id, True, **kw)
            p6 = await seeker(2006, "Офіціантка")                                      # published, hidden by the owner
            await j.moderate("seeker", p6.id, True, **kw)
            await j.set_seeker_active(2006, False)
            p5 = await seeker(2005, "Помічник кухаря")                                 # contact passed
            await j.moderate("seeker", p5.id, True, **kw)
            c5 = await j.offer(3001, p5.id, "Запрошуємо на співбесіду.", v2.id)
            await j.moderate("contact", c5.id, True, **kw)
            await j.answer(2005, c5.id, True)
        await s.commit()


def main() -> None:
    path, port = sys.argv[1], int(sys.argv[2])
    kind = sys.argv[4] if len(sys.argv) > 4 else "empty"
    settings = Settings(_env_file=None, bot_token=TEST_TOKEN, database_url=f"sqlite+aiosqlite:///{path}",
                        bot_name="Ukraine Helper DE", analytics_salt="ui-audit", keepalive_interval_sec=0)
    engine = make_engine(settings.database_url)
    sm = make_sessionmaker(engine)

    async def init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await seed(sm, kind)

    asyncio.run(init())
    uvicorn.run(create_app(settings, sm), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
