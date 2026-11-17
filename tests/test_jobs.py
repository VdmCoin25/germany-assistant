"""Job exchange: moderation, anonymity, paid access, contact exchange, GDPR."""
import httpx
from aiogram.methods import SendMessage
from sqlalchemy import func, select

from app.database.models import ContactRequest, Employer, SeekerProfile, Vacancy
from app.database.repositories.jobs import JobsRepository
from app.webapp.api import create_app
from tests.conftest import ADMIN_ID, FakeSession, TOKEN
from tests.test_units import make_init_data

SEEKER, BOSS = 2001, 3001

SEEKER_BODY = {"position": "Koch", "land": "BE", "city": "Berlin", "german_level": "A2", "employment": "full",
               "shifts_ok": True, "experience": "5 років кухарем у Києві", "about": "Пунктуальний"}
EMPLOYER_BODY = {"company": "Muster Gastro GmbH", "address": "Hauptstr. 1, 10115 Berlin",
                 "register_no": "HRB 12345 B", "contact_person": "Anna Muster", "contact": "jobs@muster.example"}
VACANCY_BODY = {"title": "Koch (m/w/d)", "land": "BE", "city": "Berlin", "german_level": "A2", "employment": "full",
                "salary": "15 €/h", "description": "Wir suchen einen Koch für unser Restaurant in Mitte. Vollzeit."}


def hdr(uid):
    return {"X-Telegram-Init-Data": make_init_data(uid)}


async def approve_all(sm, settings, kind):
    async with sm() as s:
        jobs = JobsRepository(s)
        for k, obj in await jobs.pending():
            if k == kind:
                await jobs.moderate(k, obj.id, True, pilot_days=settings.employer_pilot_days,
                                    vacancy_days=settings.vacancy_days)
        await s.commit()


async def test_full_exchange_flow(settings, sm):
    from aiogram import Bot

    fake = FakeSession()
    app = create_app(settings, sm, bot=Bot(TOKEN, session=fake))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        # seeker submits -> pending, admin notified, invisible
        r = await c.put("/api/jobs/seeker", headers=hdr(SEEKER), json=SEEKER_BODY)
        assert r.status_code == 200 and r.json()["status"] == "pending"
        assert any(isinstance(m, SendMessage) and m.chat_id == ADMIN_ID for m in fake.calls)

        # employer without approval has no access
        await c.put("/api/jobs/employer", headers=hdr(BOSS), json=EMPLOYER_BODY)
        assert (await c.get("/api/jobs/seekers", headers=hdr(BOSS))).status_code == 403
        assert (await c.post("/api/jobs/vacancies", headers=hdr(BOSS), json=VACANCY_BODY)).status_code == 403

        await approve_all(sm, settings, "seeker")
        await approve_all(sm, settings, "employer")

        # employer now sees the seeker, anonymised
        seekers = (await c.get("/api/jobs/seekers", headers=hdr(BOSS))).json()
        assert len(seekers) == 1
        assert "owner_tg" not in seekers[0] and str(SEEKER) not in str(seekers[0])

        # vacancy is invisible until approved
        await c.post("/api/jobs/vacancies", headers=hdr(BOSS), json=VACANCY_BODY)
        assert (await c.get("/api/jobs/vacancies", headers=hdr(SEEKER))).json() == []
        await approve_all(sm, settings, "vacancy")
        vacs = (await c.get("/api/jobs/vacancies", headers=hdr(SEEKER))).json()
        assert vacs[0]["company"] == "Muster Gastro GmbH"

        # offer -> admin -> seeker; duplicate refused
        r = await c.post("/api/jobs/offers", headers=hdr(BOSS),
                         json={"seeker_id": seekers[0]["id"], "vacancy_id": vacs[0]["id"], "message": "Kommen Sie zum Probetag?"})
        assert r.status_code == 200
        dup = await c.post("/api/jobs/offers", headers=hdr(BOSS),
                           json={"seeker_id": seekers[0]["id"], "vacancy_id": vacs[0]["id"], "message": "Noch einmal bitte"})
        assert dup.status_code == 409
        assert (await c.get("/api/jobs/me", headers=hdr(SEEKER))).json()["inbox"] == []  # not yet approved
        await approve_all(sm, settings, "contact")
        inbox = (await c.get("/api/jobs/me", headers=hdr(SEEKER))).json()["inbox"]
        assert inbox[0]["status"] == "sent"
        # the new Mini App shows the vacancy details and an exact time on the offer card
        info = inbox[0]["vacancy_info"]
        assert info["city"] == VACANCY_BODY["city"] and info["employment"] == VACANCY_BODY["employment"]
        assert "T" in inbox[0]["created_at"] and inbox[0]["answered_at"] is None
        assert "T" in (await c.get("/api/jobs/me", headers=hdr(SEEKER))).json()["seeker"]["updated_at"]

        # employer cannot answer the seeker's offer; seeker accepts -> both get contacts
        assert (await c.post(f"/api/jobs/requests/{inbox[0]['id']}/answer", headers=hdr(BOSS),
                             json={"accept": True})).status_code == 404
        fake.clear()
        r = await c.post(f"/api/jobs/requests/{inbox[0]['id']}/answer", headers=hdr(SEEKER), json={"accept": True})
        assert r.json()["status"] == "accepted"
        to_seeker = [m.text for m in fake.calls if isinstance(m, SendMessage) and m.chat_id == SEEKER]
        to_boss = [m.text for m in fake.calls if isinstance(m, SendMessage) and m.chat_id == BOSS]
        assert "jobs@muster.example" in to_seeker[0]
        assert f"tg://user?id={SEEKER}" in to_boss[0]


async def test_seeker_edit_goes_back_to_moderation(settings, sm):
    async with sm() as s:
        jobs = JobsRepository(s)
        p = await jobs.upsert_seeker(SEEKER, position="Koch", employment="any", experience="x" * 5)
        await jobs.moderate("seeker", p.id, True, pilot_days=30, vacancy_days=30)
        await jobs.upsert_seeker(SEEKER, position="Koch und Fahrer", employment="any", experience="x" * 5)
        assert p.status == "pending"
        assert await jobs.list_seekers() == []


async def test_access_expires(settings, sm):
    from datetime import timedelta

    from app.database.repositories.jobs import now

    async with sm() as s:
        jobs = JobsRepository(s)
        e = await jobs.upsert_employer(BOSS, **EMPLOYER_BODY)
        await jobs.moderate("employer", e.id, True, pilot_days=30, vacancy_days=30)
        assert jobs.has_access(e)
        e.access_until = now() - timedelta(days=1)
        assert not jobs.has_access(e)
        await jobs.grant(BOSS, 30)
        assert jobs.has_access(e)


async def test_apply_requires_approved_seeker(settings, sm):
    app = create_app(settings, sm)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/jobs/applications", headers=hdr(SEEKER), json={"vacancy_id": 1, "message": "Hallo, ich"})
        assert r.status_code == 403


async def test_validation_rejects_bad_input(settings, sm):
    app = create_app(settings, sm)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        bad = {**SEEKER_BODY, "land": "XX"}
        assert (await c.put("/api/jobs/seeker", headers=hdr(SEEKER), json=bad)).status_code == 422
        long = {**SEEKER_BODY, "experience": "x" * 900}
        assert (await c.put("/api/jobs/seeker", headers=hdr(SEEKER), json=long)).status_code == 422
        assert (await c.get("/api/jobs/me", headers={"X-Telegram-Init-Data": "x"})).status_code == 401


async def test_admin_moderates_in_chat_and_others_cannot(h, sm):
    async with sm() as s:
        p = await JobsRepository(s).upsert_seeker(SEEKER, position="Koch", employment="any", experience="xxxxx")
        await s.commit()
    await h.press(SEEKER, f"mod:seeker:{p.id}:1")  # regular user: ignored
    async with sm() as s:
        assert (await s.get(SeekerProfile, p.id)).status == "pending"
    await h.send(ADMIN_ID, "/moderate")
    assert any("Анкета соискателя" in x for x in h.session.texts())
    await h.press(ADMIN_ID, f"mod:seeker:{p.id}:1")
    async with sm() as s:
        assert (await s.get(SeekerProfile, p.id)).status == "approved"


async def test_delete_my_data_removes_job_records(h, sm):
    from tests.test_bot_flows import register

    await register(h, uid=BOSS)
    async with sm() as s:
        jobs = JobsRepository(s)
        e = await jobs.upsert_employer(BOSS, **EMPLOYER_BODY)
        await jobs.moderate("employer", e.id, True, pilot_days=30, vacancy_days=30)
        await jobs.create_vacancy(BOSS, title="Koch", city="Berlin", employment="full", description="x" * 30)
        await s.commit()
    await h.send(BOSS, "/delete_my_data")
    await h.press(BOSS, "del:yes")
    async with sm() as s:
        for m in (Employer, Vacancy, ContactRequest):
            assert await s.scalar(select(func.count(m.id))) == 0


async def test_profile_submission_limit_two_per_hour(settings, sm):
    from datetime import timedelta

    from app.database.models import SubmissionLog
    from app.database.repositories.jobs import now

    app = create_app(settings, sm)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        for _ in range(2):
            assert (await c.put("/api/jobs/seeker", headers=hdr(SEEKER), json=SEEKER_BODY)).status_code == 200
        r = await c.put("/api/jobs/seeker", headers=hdr(SEEKER), json=SEEKER_BODY)
        assert r.status_code == 429 and r.json()["detail"].startswith("submit_limit:")
        # employer form shares the same limit
        assert (await c.put("/api/jobs/employer", headers=hdr(SEEKER), json=EMPLOYER_BODY)).status_code == 429
        # another user is not affected
        assert (await c.put("/api/jobs/seeker", headers=hdr(SEEKER + 1), json=SEEKER_BODY)).status_code == 200
        # after an hour it works again
        async with sm() as s:
            for row in await s.scalars(select(SubmissionLog).where(SubmissionLog.owner_tg == SEEKER)):
                row.created_at = now() - timedelta(minutes=61)
            await s.commit()
        assert (await c.put("/api/jobs/seeker", headers=hdr(SEEKER), json=SEEKER_BODY)).status_code == 200


LEAD_BODY = {"contact": "+49 151 2345 6789", "contact_person": "Anna", "company": "Muster Bau GmbH",
             "positions": "Helfer auf der Baustelle", "headcount": 3, "land": "BY", "city": "München",
             "details": "Ab Dezember, Vollzeit"}


async def test_employer_lead_goes_to_admin_with_contact_first(settings, sm):
    from aiogram import Bot

    from app.database.models import EmployerLead

    fake = FakeSession()
    app = create_app(settings, sm, bot=Bot(TOKEN, session=fake))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/jobs/leads", headers=hdr(BOSS), json=LEAD_BODY)
        assert r.status_code == 200 and r.json()["status"] == "pending"
        to_admin = [m.text for m in fake.calls if isinstance(m, SendMessage) and m.chat_id == ADMIN_ID]
        assert to_admin and "+49 151 2345 6789" in to_admin[0].split("\n")[3]       # the line right after the title
        assert f"tg://user?id={BOSS}" in to_admin[0]
        me = (await c.get("/api/jobs/me", headers=hdr(BOSS))).json()
        assert me["leads"][0]["positions"] == LEAD_BODY["positions"]

        # a bare username gets its @, junk is refused
        r = await c.post("/api/jobs/leads", headers=hdr(BOSS), json={**LEAD_BODY, "contact": "muster_bau"})
        assert r.json()["contact"] == "@muster_bau"
        for bad in ("123", "hello world", "+49 12"):
            assert (await c.post("/api/jobs/leads", headers=hdr(BOSS), json={**LEAD_BODY, "contact": bad})).status_code == 422
        assert (await c.post("/api/jobs/leads", headers=hdr(BOSS), json={**LEAD_BODY, "land": "XX"})).status_code == 422

    # admin takes it into work -> the employer is told we will call them on their contact
    async with sm() as s:
        jobs = JobsRepository(s)
        kind, lead = next((k, o) for k, o in await jobs.pending() if k == "lead")
        await jobs.moderate(kind, lead.id, True, pilot_days=30, vacancy_days=30)
        await s.commit()
        from app.services.jobs.notify import Notifier
        fake.clear()
        await Notifier(Bot(TOKEN, session=fake), settings).moderated(s, kind, lead, True)
        sent = [m for m in fake.calls if isinstance(m, SendMessage)]
        assert sent[0].chat_id == BOSS and "+49 151 2345 6789" in sent[0].text

        # GDPR: leads are exported and deleted with the user
        assert "employer_leads" in await jobs.export_user(BOSS)
        await jobs.delete_user(BOSS)
        await s.commit()
        assert await s.scalar(select(func.count()).select_from(EmployerLead)) == 0


async def test_report_vacancy_reaches_admins_with_takedown(settings, sm):
    from aiogram import Bot

    fake = FakeSession()
    app = create_app(settings, sm, bot=Bot(TOKEN, session=fake))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        await c.put("/api/jobs/employer", headers=hdr(BOSS), json=EMPLOYER_BODY)
        await approve_all(sm, settings, "employer")
        vid = (await c.post("/api/jobs/vacancies", headers=hdr(BOSS), json=VACANCY_BODY)).json()["id"]
        # not published yet -> cannot be reported
        assert (await c.post(f"/api/jobs/vacancies/{vid}/report", headers=hdr(SEEKER),
                             json={"reason": "fee"})).status_code == 404
        await approve_all(sm, settings, "vacancy")
        fake.clear()
        r = await c.post(f"/api/jobs/vacancies/{vid}/report", headers=hdr(SEEKER),
                         json={"reason": "fee", "text": "Хотят 200 € за оформление"})
        assert r.status_code == 200
        sent = [m for m in fake.calls if isinstance(m, SendMessage) and m.chat_id == ADMIN_ID]
        assert "200 €" in sent[0].text and f"rep:close:{vid}" in str(sent[0].reply_markup)
        assert (await c.post(f"/api/jobs/vacancies/{vid}/report", headers=hdr(SEEKER),
                             json={"reason": "spam"})).status_code == 422
