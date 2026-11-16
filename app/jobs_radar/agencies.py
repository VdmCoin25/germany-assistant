"""Agency normalization and de-duplication: business data only."""
import re

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import JobAgency, utcnow
from app.jobs_radar.classifier import Classification

_LEGAL_TOKENS = {"gmbh", "mbh", "ug", "ag", "kg", "co", "ohg", "gbr", "se", "тов", "тзов", "ооо", "haftungsbeschränkt"}


def normalize_name(name: str | None) -> str:
    t = (name or "").casefold()
    t = re.sub(r"e\.\s?k\.", " ", t)
    t = re.sub(r"[^\w\s]|_", " ", t)
    return " ".join(w for w in t.split() if w not in _LEGAL_TOKENS)


def normalize_domain(value: str | None) -> str | None:
    t = (value or "").strip().casefold()
    t = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", t)
    if "@" in t:
        t = t.rsplit("@", 1)[1]
    t = re.split(r"[/?#:]", t, maxsplit=1)[0]
    t = re.sub(r"^www\.", "", t).strip(".")
    return t if "." in t else None


def normalize_phone(value: str | None) -> str | None:
    t = re.sub(r"\(\s*0\s*\)", "", value or "")
    digits = re.sub(r"\D", "", t)
    if not 7 <= len(digits) <= 15:
        return None
    if t.strip().startswith("+"):
        return "+" + digits
    if digits.startswith("00"):
        return "+" + digits[2:]
    if digits.startswith("0"):
        return "+49" + digits[1:]
    return "+" + digits


async def upsert_agency(session: AsyncSession, c: Classification, source: str = "telegram") -> JobAgency | None:
    domain = normalize_domain(c.website) or normalize_domain(c.email)
    phone = normalize_phone(c.phone)
    name_norm = normalize_name(c.company)
    if not name_norm and not domain and not phone:
        return None

    conds = []
    if name_norm:
        conds.append(JobAgency.name_norm == name_norm)
    if domain:
        conds.append(JobAgency.domain == domain)
    if phone:
        conds.append(JobAgency.phone_norm == phone)
    existing = await session.scalar(select(JobAgency).where(or_(*conds)).order_by(JobAgency.id).limit(1))

    now = utcnow()
    if existing:
        existing.last_seen_at = now
        existing.signals_count = (existing.signals_count or 0) + 1
        existing.website = existing.website or c.website
        existing.email = existing.email or c.email
        existing.domain = existing.domain or domain
        existing.phone_norm = existing.phone_norm or phone
        await session.flush()
        return existing

    name = (c.company or domain or phone or "").strip()
    agency = JobAgency(
        name=name[:200], name_norm=(name_norm or normalize_name(name) or name.casefold())[:200],
        domain=domain, phone_norm=phone, email=c.email, website=c.website, source=source,
        first_seen_at=now, last_seen_at=now, signals_count=1,
    )
    session.add(agency)
    await session.flush()
    return agency
