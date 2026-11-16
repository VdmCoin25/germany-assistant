from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    """Minimal profile. No names, phone numbers or documents are stored here."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    language: Mapped[str | None] = mapped_column(String(8))
    land: Mapped[str | None] = mapped_column(String(8))
    city: Mapped[str | None] = mapped_column(String(80))
    german_level: Mapped[str | None] = mapped_column(String(8))
    goal: Mapped[str | None] = mapped_column(String(16))
    residence_status: Mapped[str | None] = mapped_column(String(16))
    is_registered: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    broadcast_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalyticsEvent(Base):
    """Pseudonymous product events. Never stores message or document content."""

    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    feature: Mapped[str | None] = mapped_column(String(64))
    user_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class InfoSource(Base):
    """Catalog of official links, editable by admins without code changes."""

    __tablename__ = "info_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(String(32), index=True)
    title_uk: Mapped[str] = mapped_column(String(200))
    title_ru: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


# ---------------- Job exchange (every public item is moderated by an admin) ----------------

class SeekerProfile(Base):
    """A job seeker's profile. Shown to verified employers WITHOUT name or contacts."""

    __tablename__ = "seeker_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_tg: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    position: Mapped[str] = mapped_column(String(120))
    land: Mapped[str | None] = mapped_column(String(8))
    city: Mapped[str | None] = mapped_column(String(80))
    german_level: Mapped[str | None] = mapped_column(String(8))
    employment: Mapped[str] = mapped_column(String(16))  # full | part | mini | any
    shifts_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    experience: Mapped[str] = mapped_column(Text)
    about: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|approved|rejected
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Employer(Base):
    __tablename__ = "employers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_tg: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    company: Mapped[str] = mapped_column(String(160))
    address: Mapped[str] = mapped_column(String(240))
    register_no: Mapped[str] = mapped_column(String(80))  # Handelsregister / Gewerbeanmeldung / USt-IdNr.
    contact_person: Mapped[str] = mapped_column(String(120))
    contact: Mapped[str] = mapped_column(String(160))  # business phone or e-mail shown to accepted seekers
    website: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|approved|rejected
    access_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Vacancy(Base):
    __tablename__ = "vacancies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employer_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(120))
    land: Mapped[str | None] = mapped_column(String(8))
    city: Mapped[str] = mapped_column(String(80))
    german_level: Mapped[str | None] = mapped_column(String(8))
    employment: Mapped[str] = mapped_column(String(16))
    salary: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|approved|rejected|closed
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContactRequest(Base):
    """An employer's offer to a seeker, or a seeker's application to a vacancy.

    pending (admin review) -> sent -> accepted | declined;  or pending -> rejected by admin.
    Contacts of both sides are exchanged only when the recipient accepts.
    """

    __tablename__ = "contact_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(8))  # offer | apply
    employer_id: Mapped[int] = mapped_column(Integer, index=True)
    seeker_id: Mapped[int] = mapped_column(Integer, index=True)
    vacancy_id: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
