"""Job exchange API for the Mini App. Same Telegram initData auth as the profile API."""
import re
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.middlewares.throttling import RateLimiter
from app.config import Settings
from app.data.regions import GERMAN_LEVELS, LANDS
from app.database.models import ContactRequest, Employer, EmployerLead, SeekerProfile, Vacancy
from app.database.repositories.jobs import JobsError, JobsRepository, aware
from app.services.jobs.notify import Notifier

Level = Literal[tuple(GERMAN_LEVELS)]  # type: ignore[valid-type]
Employment = Literal["full", "part", "mini", "any"]


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = " ".join(v.split()) if "\n" not in v else "\n".join(" ".join(x.split()) for x in v.strip().splitlines())
    return v or None


def _land(v):
    if v is not None and v not in LANDS:
        raise ValueError("unknown land")
    return v


class SeekerIn(BaseModel):
    position: str = Field(min_length=2, max_length=120)
    land: str | None = None
    city: str | None = Field(default=None, max_length=80)
    german_level: Level | None = None
    employment: Employment = "any"
    shifts_ok: bool = False
    experience: str = Field(min_length=2, max_length=800)
    about: str | None = Field(default=None, max_length=500)

    _c = field_validator("position", "city", "experience", "about")(lambda cls, v: _clean(v))
    _l = field_validator("land")(lambda cls, v: _land(v))


class EmployerIn(BaseModel):
    company: str = Field(min_length=2, max_length=160)
    address: str = Field(min_length=5, max_length=240)
    register_no: str = Field(min_length=3, max_length=80)
    contact_person: str = Field(min_length=2, max_length=120)
    contact: str = Field(min_length=5, max_length=160)
    website: str | None = Field(default=None, max_length=200)

    _c = field_validator("company", "address", "register_no", "contact_person", "contact", "website")(
        lambda cls, v: _clean(v))


_PHONE = re.compile(r"^\+?[\d\s()\-/.]{6,24}$")
_USER = re.compile(r"^@?([A-Za-z][A-Za-z0-9_]{4,31})$")
_MAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _contact(v: str) -> str:
    """A way to reach the employer: phone, Telegram @username or e-mail. Usernames get a leading @."""
    v = " ".join(v.split())
    if _PHONE.match(v) and sum(ch.isdigit() for ch in v) >= 7:
        return v
    if m := _USER.match(v):
        return "@" + m.group(1)
    if _MAIL.match(v):
        return v
    raise ValueError("contact must be a phone number, @username or e-mail")


class LeadIn(BaseModel):
    contact: str = Field(min_length=5, max_length=160)
    contact_person: str | None = Field(default=None, max_length=120)
    company: str | None = Field(default=None, max_length=160)
    positions: str = Field(min_length=2, max_length=200)
    headcount: int | None = Field(default=None, ge=1, le=999)
    land: str | None = None
    city: str | None = Field(default=None, max_length=80)
    details: str | None = Field(default=None, max_length=1000)

    _c = field_validator("contact_person", "company", "positions", "city", "details")(lambda cls, v: _clean(v))
    _k = field_validator("contact")(lambda cls, v: _contact(v))
    _l = field_validator("land")(lambda cls, v: _land(v))


def lead_out(x: EmployerLead) -> dict:
    return {"id": x.id, "positions": x.positions, "headcount": x.headcount, "city": x.city, "land": x.land,
            "contact": x.contact, "status": x.status, "created": _d(x.created_at)}


class VacancyIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    land: str | None = None
    city: str = Field(min_length=2, max_length=80)
    german_level: Level | None = None
    employment: Employment = "full"
    salary: str | None = Field(default=None, max_length=80)
    description: str = Field(min_length=20, max_length=1500)

    _c = field_validator("title", "city", "salary", "description")(lambda cls, v: _clean(v))
    _l = field_validator("land")(lambda cls, v: _land(v))


class MessageIn(BaseModel):
    message: str = Field(min_length=5, max_length=600)
    _c = field_validator("message")(lambda cls, v: _clean(v))


class OfferIn(MessageIn):
    seeker_id: int
    vacancy_id: int | None = None


class ApplyIn(MessageIn):
    vacancy_id: int


class ActiveIn(BaseModel):
    active: bool


class AnswerIn(BaseModel):
    accept: bool


def _d(x: datetime | None) -> str | None:
    return aware(x).date().isoformat() if x else None


def seeker_public(p: SeekerProfile) -> dict:
    """What employers see: no name, no Telegram id, no contacts."""
    return {"id": p.id, "position": p.position, "land": p.land, "city": p.city, "german_level": p.german_level,
            "employment": p.employment, "shifts_ok": p.shifts_ok, "experience": p.experience, "about": p.about,
            "updated": _d(p.updated_at)}


def _ts(x: datetime | None) -> str | None:
    """Full timestamp (UTC, ISO 8601) for screens that show a time, not only a date."""
    return aware(x).isoformat() if x else None


def seeker_own(p: SeekerProfile) -> dict:
    return {**seeker_public(p), "status": p.status, "is_active": p.is_active, "updated_at": _ts(p.updated_at)}


def vacancy_out(v: Vacancy, e: Employer | None = None) -> dict:
    out = {"id": v.id, "title": v.title, "land": v.land, "city": v.city, "german_level": v.german_level,
           "employment": v.employment, "salary": v.salary, "description": v.description,
           "status": v.status, "published": _d(v.created_at), "expires": _d(v.expires_at)}
    if e is not None:
        out["company"] = e.company
    return out


def build_jobs_router(settings: Settings, sm: async_sessionmaker, bot, verify) -> APIRouter:
    r = APIRouter(prefix="/api/jobs")
    limiter = RateLimiter(limit=15, window=60)

    def auth(x_telegram_init_data: Annotated[str, Header()]) -> int:
        data = verify(x_telegram_init_data, settings.bot_token, settings.webapp_init_data_ttl)
        return data.user.id

    def write_auth(uid: Annotated[int, Depends(auth)]) -> int:
        if not limiter.allow(uid):
            raise HTTPException(429, "rate_limited")
        return uid

    Uid = Annotated[int, Depends(auth)]
    WUid = Annotated[int, Depends(write_auth)]
    notifier = Notifier(bot, settings)

    def fail(e: JobsError):
        raise HTTPException(e.status, e.code)

    async def blocked(s, uid: int) -> None:
        from app.database.repositories.users import UserRepository

        u = await UserRepository(s).get(uid)
        if u and u.is_blocked:
            raise HTTPException(403, "blocked")

    @r.get("/me")
    async def me(uid: Uid):
        async with sm() as s:
            jobs = JobsRepository(s)
            p, e = await jobs.seeker(uid), await jobs.employer(uid)
            emp = None
            if e:
                emp = {"company": e.company, "address": e.address, "register_no": e.register_no,
                       "contact_person": e.contact_person, "contact": e.contact, "website": e.website,
                       "status": e.status, "access_until": _d(e.access_until), "has_access": jobs.has_access(e),
                       "vacancies": [vacancy_out(v) for v in await jobs.employer_vacancies(e.id)]}

            async def describe(c: ContactRequest) -> dict:
                emp_ = await s.get(Employer, c.employer_id)
                sk = await s.get(SeekerProfile, c.seeker_id)
                vac = await s.get(Vacancy, c.vacancy_id) if c.vacancy_id else None
                return {"id": c.id, "kind": c.kind, "status": c.status, "message": c.message,
                        "created": _d(c.created_at), "created_at": _ts(c.created_at),
                        "answered_at": _ts(c.answered_at), "company": emp_.company if emp_ else None,
                        "vacancy": vac.title if vac else None, "vacancy_id": c.vacancy_id,
                        # details for the offer card in the new Mini App (v1 ignores them)
                        "vacancy_info": {"city": vac.city, "land": vac.land, "employment": vac.employment,
                                         "salary": vac.salary, "german_level": vac.german_level} if vac else None,
                        "seeker": seeker_public(sk) if sk else None}

            return {"seeker": seeker_own(p) if p else None, "employer": emp,
                    "leads": [lead_out(x) for x in await jobs.leads(uid)],
                    "inbox": [await describe(c) for c in await jobs.inbox(uid)],
                    "outbox": [await describe(c) for c in await jobs.outbox(uid)]}

    @r.get("/vacancies")
    async def vacancies(uid: Uid, land: str | None = None):
        async with sm() as s:
            return [vacancy_out(v, e) for v, e in await JobsRepository(s).list_vacancies(land)]

    @r.put("/seeker")
    async def put_seeker(body: SeekerIn, uid: WUid):
        async with sm() as s:
            await blocked(s, uid)
            jobs = JobsRepository(s)
            try:
                await jobs.check_submission_limit(uid, settings.submission_limit_per_hour)
            except JobsError as e:
                fail(e)
            await jobs.log_submission(uid, "seeker")
            p = await jobs.upsert_seeker(uid, **body.model_dump())
            await s.commit()
            await notifier.to_admins(s, "seeker", p)
            return seeker_own(p)

    @r.post("/seeker/active")
    async def seeker_active(body: ActiveIn, uid: WUid):
        async with sm() as s:
            try:
                p = await JobsRepository(s).set_seeker_active(uid, body.active)
            except JobsError as e:
                fail(e)
            await s.commit()
            return seeker_own(p)

    @r.put("/employer")
    async def put_employer(body: EmployerIn, uid: WUid):
        async with sm() as s:
            await blocked(s, uid)
            jobs = JobsRepository(s)
            try:
                await jobs.check_submission_limit(uid, settings.submission_limit_per_hour)
            except JobsError as ex:
                fail(ex)
            await jobs.log_submission(uid, "employer")
            e = await jobs.upsert_employer(uid, **body.model_dump())
            await s.commit()
            await notifier.to_admins(s, "employer", e)
            return {"status": e.status}

    @r.post("/leads")
    async def post_lead(body: LeadIn, uid: WUid):
        async with sm() as s:
            await blocked(s, uid)
            jobs = JobsRepository(s)
            try:
                await jobs.check_submission_limit(uid, settings.submission_limit_per_hour)
            except JobsError as ex:
                fail(ex)
            await jobs.log_submission(uid, "lead")
            lead = await jobs.create_lead(uid, **body.model_dump())
            await s.commit()
            await notifier.to_admins(s, "lead", lead)
            return lead_out(lead)

    @r.get("/seekers")
    async def seekers(uid: Uid, land: str | None = None):
        async with sm() as s:
            jobs = JobsRepository(s)
            try:
                await jobs.require_employer(uid)
            except JobsError as e:
                fail(e)
            return [seeker_public(p) for p in await jobs.list_seekers(land)]

    @r.post("/vacancies")
    async def post_vacancy(body: VacancyIn, uid: WUid):
        async with sm() as s:
            await blocked(s, uid)
            try:
                v = await JobsRepository(s).create_vacancy(uid, **body.model_dump())
            except JobsError as e:
                fail(e)
            await s.commit()
            await notifier.to_admins(s, "vacancy", v)
            return vacancy_out(v)

    @r.post("/vacancies/{vacancy_id}/close")
    async def close_vacancy(vacancy_id: int, uid: WUid):
        async with sm() as s:
            try:
                await JobsRepository(s).close_vacancy(uid, vacancy_id)
            except JobsError as e:
                fail(e)
            await s.commit()
            return {"ok": True}

    @r.post("/offers")
    async def offer(body: OfferIn, uid: WUid):
        async with sm() as s:
            await blocked(s, uid)
            try:
                c = await JobsRepository(s).offer(uid, body.seeker_id, body.message, body.vacancy_id)
            except JobsError as e:
                fail(e)
            await s.commit()
            await notifier.to_admins(s, "contact", c)
            return {"id": c.id, "status": c.status}

    @r.post("/applications")
    async def application(body: ApplyIn, uid: WUid):
        async with sm() as s:
            await blocked(s, uid)
            try:
                c = await JobsRepository(s).apply(uid, body.vacancy_id, body.message)
            except JobsError as e:
                fail(e)
            await s.commit()
            await notifier.to_admins(s, "contact", c)
            return {"id": c.id, "status": c.status}

    @r.post("/requests/{request_id}/answer")
    async def answer(request_id: int, body: AnswerIn, uid: WUid):
        async with sm() as s:
            try:
                c = await JobsRepository(s).answer(uid, request_id, body.accept)
            except JobsError as e:
                fail(e)
            await s.commit()
            await notifier.answered(s, c)
            return {"status": c.status}

    return r
