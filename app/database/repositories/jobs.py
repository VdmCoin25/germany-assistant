"""Job exchange rules. Every public item (seeker profile, employer, vacancy, contact request)
starts as `pending` and becomes visible only after an admin approves it."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ContactRequest, Employer, EmployerLead, SeekerProfile, SubmissionLog, Vacancy

EMPLOYMENT = ("full", "part", "mini", "any")
KINDS = ("lead", "seeker", "employer", "vacancy", "contact")


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(d: datetime | None) -> datetime | None:
    # SQLite returns naive datetimes; treat them as UTC.
    if d is not None and d.tzinfo is None:
        return d.replace(tzinfo=timezone.utc)
    return d


class JobsError(Exception):
    """Business-rule violation; `code` is shown to the client."""

    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code = code
        self.status = status


class JobsRepository:
    def __init__(self, session: AsyncSession):
        self.s = session

    # ---------- submission limit ----------
    async def check_submission_limit(self, tg: int, limit: int) -> None:
        """Raise if the user already sent `limit` profile forms within the last hour; otherwise record this one."""
        since = now() - timedelta(hours=1)
        rows = list(await self.s.scalars(select(SubmissionLog.created_at).where(
            SubmissionLog.owner_tg == tg, SubmissionLog.created_at >= since).order_by(SubmissionLog.created_at)))
        if len(rows) >= limit:
            wait = int(((aware(rows[0]) + timedelta(hours=1)) - now()).total_seconds() // 60) + 1
            raise JobsError(f"submit_limit:{max(wait, 1)}", 429)

    async def log_submission(self, tg: int, kind: str) -> None:
        self.s.add(SubmissionLog(owner_tg=tg, kind=kind))
        await self.s.flush()

    # ---------- seekers ----------
    async def seeker(self, tg: int) -> SeekerProfile | None:
        return await self.s.scalar(select(SeekerProfile).where(SeekerProfile.owner_tg == tg))

    async def upsert_seeker(self, tg: int, **data) -> SeekerProfile:
        p = await self.seeker(tg)
        if p is None:
            p = SeekerProfile(owner_tg=tg, **data)
            self.s.add(p)
        else:
            for k, v in data.items():
                setattr(p, k, v)
        p.status = "pending"  # every change is reviewed again
        await self.s.flush()
        return p

    async def set_seeker_active(self, tg: int, active: bool) -> SeekerProfile:
        p = await self.seeker(tg)
        if not p:
            raise JobsError("no_seeker", 404)
        p.is_active = active
        await self.s.flush()
        return p

    async def list_seekers(self, land: str | None = None) -> list[SeekerProfile]:
        q = select(SeekerProfile).where(SeekerProfile.status == "approved", SeekerProfile.is_active.is_(True))
        if land:
            q = q.where(SeekerProfile.land == land)
        return list(await self.s.scalars(q.order_by(SeekerProfile.updated_at.desc()).limit(200)))

    # ---------- employers ----------
    async def employer(self, tg: int) -> Employer | None:
        return await self.s.scalar(select(Employer).where(Employer.owner_tg == tg))

    async def upsert_employer(self, tg: int, **data) -> Employer:
        e = await self.employer(tg)
        if e is None:
            e = Employer(owner_tg=tg, **data)
            self.s.add(e)
        else:
            for k, v in data.items():
                setattr(e, k, v)
        e.status = "pending"
        await self.s.flush()
        return e

    @staticmethod
    def has_access(e: Employer | None) -> bool:
        return bool(e and e.status == "approved" and e.access_until and aware(e.access_until) > now())

    async def grant(self, tg: int, days: int) -> Employer:
        e = await self.employer(tg)
        if not e:
            raise JobsError("no_employer", 404)
        base = max(aware(e.access_until) or now(), now())
        e.access_until = base + timedelta(days=days)
        await self.s.flush()
        return e

    async def require_employer(self, tg: int) -> Employer:
        e = await self.employer(tg)
        if not self.has_access(e):
            raise JobsError("employer_no_access", 403)
        return e

    # ---------- vacancies ----------
    async def create_vacancy(self, tg: int, **data) -> Vacancy:
        e = await self.require_employer(tg)
        v = Vacancy(employer_id=e.id, status="pending", **data)
        self.s.add(v)
        await self.s.flush()
        return v

    async def close_vacancy(self, tg: int, vacancy_id: int) -> None:
        e = await self.employer(tg)
        v = await self.s.get(Vacancy, vacancy_id)
        if not e or not v or v.employer_id != e.id:
            raise JobsError("not_found", 404)
        v.status = "closed"
        await self.s.flush()

    async def employer_vacancies(self, employer_id: int) -> list[Vacancy]:
        return list(await self.s.scalars(
            select(Vacancy).where(Vacancy.employer_id == employer_id).order_by(Vacancy.created_at.desc())))

    async def list_vacancies(self, land: str | None = None) -> list[tuple[Vacancy, Employer]]:
        q = (select(Vacancy, Employer).join(Employer, Employer.id == Vacancy.employer_id)
             .where(Vacancy.status == "approved", Employer.status == "approved",
                    or_(Vacancy.expires_at.is_(None), Vacancy.expires_at > now())))
        if land:
            q = q.where(Vacancy.land == land)
        return list((await self.s.execute(q.order_by(Vacancy.created_at.desc()).limit(200))).all())

    # ---------- contact requests ----------
    async def _open_duplicate(self, employer_id: int, seeker_id: int, vacancy_id: int | None) -> bool:
        n = await self.s.scalar(select(func.count(ContactRequest.id)).where(
            ContactRequest.employer_id == employer_id, ContactRequest.seeker_id == seeker_id,
            ContactRequest.vacancy_id.is_(vacancy_id) if vacancy_id is None else ContactRequest.vacancy_id == vacancy_id,
            ContactRequest.status.in_(("pending", "sent"))))
        return bool(n)

    async def offer(self, tg: int, seeker_id: int, message: str, vacancy_id: int | None = None) -> ContactRequest:
        e = await self.require_employer(tg)
        p = await self.s.get(SeekerProfile, seeker_id)
        if not p or p.status != "approved" or not p.is_active:
            raise JobsError("not_found", 404)
        if vacancy_id is not None:
            v = await self.s.get(Vacancy, vacancy_id)
            if not v or v.employer_id != e.id:
                raise JobsError("not_found", 404)
        if await self._open_duplicate(e.id, p.id, vacancy_id):
            raise JobsError("duplicate", 409)
        c = ContactRequest(kind="offer", employer_id=e.id, seeker_id=p.id, vacancy_id=vacancy_id, message=message)
        self.s.add(c)
        await self.s.flush()
        return c

    async def apply(self, tg: int, vacancy_id: int, message: str) -> ContactRequest:
        p = await self.seeker(tg)
        if not p or p.status != "approved":
            raise JobsError("seeker_not_approved", 403)
        row = next((r for r in await self.list_vacancies() if r[0].id == vacancy_id), None)
        if not row:
            raise JobsError("not_found", 404)
        v, e = row
        if await self._open_duplicate(e.id, p.id, v.id):
            raise JobsError("duplicate", 409)
        c = ContactRequest(kind="apply", employer_id=e.id, seeker_id=p.id, vacancy_id=v.id, message=message)
        self.s.add(c)
        await self.s.flush()
        return c

    async def inbox(self, tg: int) -> list[ContactRequest]:
        """Requests waiting for this user's answer (already approved by admin)."""
        p, e = await self.seeker(tg), await self.employer(tg)
        conds = []
        if p:
            conds.append((ContactRequest.kind == "offer") & (ContactRequest.seeker_id == p.id))
        if e:
            conds.append((ContactRequest.kind == "apply") & (ContactRequest.employer_id == e.id))
        if not conds:
            return []
        return list(await self.s.scalars(select(ContactRequest).where(
            or_(*conds), ContactRequest.status.in_(("sent", "accepted", "declined")))
            .order_by(ContactRequest.created_at.desc()).limit(100)))

    async def outbox(self, tg: int) -> list[ContactRequest]:
        p, e = await self.seeker(tg), await self.employer(tg)
        conds = []
        if p:
            conds.append((ContactRequest.kind == "apply") & (ContactRequest.seeker_id == p.id))
        if e:
            conds.append((ContactRequest.kind == "offer") & (ContactRequest.employer_id == e.id))
        if not conds:
            return []
        return list(await self.s.scalars(select(ContactRequest).where(or_(*conds))
                                         .order_by(ContactRequest.created_at.desc()).limit(100)))

    async def answer(self, tg: int, request_id: int, accept: bool) -> ContactRequest:
        c = await self.s.get(ContactRequest, request_id)
        if not c or c.status != "sent":
            raise JobsError("not_found", 404)
        if c.kind == "offer":
            p = await self.seeker(tg)
            ok = p is not None and p.id == c.seeker_id
        else:
            e = await self.employer(tg)
            ok = e is not None and e.id == c.employer_id
        if not ok:
            raise JobsError("not_found", 404)
        c.status = "accepted" if accept else "declined"
        c.answered_at = now()
        await self.s.flush()
        return c

    # ---------- employer leads ----------
    async def create_lead(self, tg: int, **data) -> EmployerLead:
        lead = EmployerLead(owner_tg=tg, **data)
        self.s.add(lead)
        await self.s.flush()
        return lead

    async def leads(self, tg: int, limit: int = 5) -> list[EmployerLead]:
        return list(await self.s.scalars(select(EmployerLead).where(EmployerLead.owner_tg == tg)
                                         .order_by(EmployerLead.created_at.desc(), EmployerLead.id.desc()).limit(limit)))

    # ---------- moderation ----------
    _MODEL = {"lead": EmployerLead, "seeker": SeekerProfile, "employer": Employer, "vacancy": Vacancy, "contact": ContactRequest}

    async def pending(self) -> list[tuple[str, object]]:
        out: list[tuple[str, object]] = []
        for kind in KINDS:
            m = self._MODEL[kind]
            for obj in await self.s.scalars(select(m).where(m.status == "pending").order_by(m.created_at)):
                out.append((kind, obj))
        return out

    async def get(self, kind: str, obj_id: int):
        if kind not in self._MODEL:
            raise JobsError("bad_kind")
        return await self.s.get(self._MODEL[kind], obj_id)

    async def moderate(self, kind: str, obj_id: int, approve: bool, *, pilot_days: int, vacancy_days: int):
        obj = await self.get(kind, obj_id)
        if obj is None or obj.status != "pending":
            raise JobsError("not_pending", 409)
        if kind == "contact":
            obj.status = "sent" if approve else "rejected"
        else:
            obj.status = "approved" if approve else "rejected"
        if approve and kind == "employer" and not self.has_access(obj):
            obj.access_until = now() + timedelta(days=pilot_days)
        if approve and kind == "vacancy":
            obj.expires_at = now() + timedelta(days=vacancy_days)
        await self.s.flush()
        return obj

    async def owner_of(self, kind: str, obj) -> int:
        """Telegram id of whoever created the item (to notify them)."""
        if kind in ("seeker", "employer", "lead"):
            return obj.owner_tg
        if kind == "vacancy":
            return (await self.s.get(Employer, obj.employer_id)).owner_tg
        if obj.kind == "offer":
            return (await self.s.get(Employer, obj.employer_id)).owner_tg
        return (await self.s.get(SeekerProfile, obj.seeker_id)).owner_tg

    async def recipient_of(self, c: ContactRequest) -> int:
        if c.kind == "offer":
            return (await self.s.get(SeekerProfile, c.seeker_id)).owner_tg
        return (await self.s.get(Employer, c.employer_id)).owner_tg

    # ---------- GDPR ----------
    async def delete_user(self, tg: int) -> None:
        await self.s.execute(delete(SubmissionLog).where(SubmissionLog.owner_tg == tg))
        await self.s.execute(delete(EmployerLead).where(EmployerLead.owner_tg == tg))
        p, e = await self.seeker(tg), await self.employer(tg)
        if p:
            await self.s.execute(delete(ContactRequest).where(ContactRequest.seeker_id == p.id))
            await self.s.delete(p)
        if e:
            await self.s.execute(delete(ContactRequest).where(ContactRequest.employer_id == e.id))
            await self.s.execute(delete(Vacancy).where(Vacancy.employer_id == e.id))
            await self.s.delete(e)
        await self.s.flush()

    async def export_user(self, tg: int) -> dict:
        p, e = await self.seeker(tg), await self.employer(tg)
        cols = lambda o: {c.name: (v.isoformat() if isinstance(v := getattr(o, c.name), datetime) else v)
                          for c in o.__table__.columns}
        out: dict = {}
        if p:
            out["seeker_profile"] = cols(p)
        if e:
            out["employer"] = cols(e)
            out["vacancies"] = [cols(v) for v in await self.employer_vacancies(e.id)]
        if leads := await self.leads(tg, limit=1000):
            out["employer_leads"] = [cols(x) for x in leads]
        return out
