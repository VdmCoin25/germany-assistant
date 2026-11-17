from datetime import date, datetime, timezone

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
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


class EmployerLead(Base):
    """A short request from an employer who wants to hire people. An admin reviews it and calls back
    on `contact` to agree the details; nothing from it is published."""

    __tablename__ = "employer_leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_tg: Mapped[int] = mapped_column(BigInteger, index=True)
    contact: Mapped[str] = mapped_column(String(160))          # phone, @username or e-mail — how we reach them
    contact_person: Mapped[str | None] = mapped_column(String(120))
    company: Mapped[str | None] = mapped_column(String(160))
    positions: Mapped[str] = mapped_column(String(200))        # who they are looking for
    headcount: Mapped[int | None] = mapped_column(Integer)
    land: Mapped[str | None] = mapped_column(String(8))
    city: Mapped[str | None] = mapped_column(String(80))
    details: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|approved|rejected
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


class SubmissionLog(Base):
    """One row per form submission, used for per-user hourly limits (survives restarts)."""

    __tablename__ = "submission_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_tg: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(16))  # seeker | employer
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# ---------------- Jobs Source Radar (admin-only; no message texts, no authors) ----------------

class JobChat(Base):
    __tablename__ = "job_chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    username: Mapped[str | None] = mapped_column(String(64), unique=True)  # lowercase, no @
    invite_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    title: Mapped[str | None] = mapped_column(String(255))
    members: Mapped[int | None] = mapped_column(Integer)
    posts_per_day_7d: Mapped[float] = mapped_column(Float, default=0)
    ads_allowed: Mapped[str] = mapped_column(String(8), default="unknown")  # unknown|yes|no
    admin_contact: Mapped[str | None] = mapped_column(String(120))
    language: Mapped[str | None] = mapped_column(String(8))
    city: Mapped[str | None] = mapped_column(String(80))
    land: Mapped[str | None] = mapped_column(String(8))
    discovered_from: Mapped[str] = mapped_column(String(8))  # seed|link|mention
    discovered_via_chat_id: Mapped[int | None] = mapped_column(Integer)
    entity_type: Mapped[str] = mapped_column(String(8), default="unknown")  # unknown|channel|group|user
    status: Mapped[str] = mapped_column(String(16), default="candidate", index=True)  # candidate|approved|joined|rejected
    join_error: Mapped[str | None] = mapped_column(String(120))
    score: Mapped[float] = mapped_column(Float, default=0, index=True)
    last_message_id: Mapped[int | None] = mapped_column(BigInteger)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JobChatDaily(Base):
    __tablename__ = "job_chat_daily"

    chat_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    posts: Mapped[int] = mapped_column(Integer, default=0)


class JobRadarAction(Base):
    __tablename__ = "job_radar_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)  # join|metadata
    chat_id: Mapped[int | None] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    result: Mapped[str] = mapped_column(String(64))


class JobKeyword(Base):
    __tablename__ = "job_keywords"
    __table_args__ = (UniqueConstraint("term", "lang", "kind", name="uq_job_keywords_term_lang_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term: Mapped[str] = mapped_column(String(80))
    lang: Mapped[str] = mapped_column(String(4))
    kind: Mapped[str] = mapped_column(String(8))  # include|exclude
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class JobSignal(Base):
    """A classified message: link and labels only, never the text or the author."""

    __tablename__ = "job_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(Integer, index=True)
    message_link: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(24))  # seeker_question|agency_vacancy|chat_rules
    city: Mapped[str | None] = mapped_column(String(80))
    profession: Mapped[str | None] = mapped_column(String(120))
    language: Mapped[str | None] = mapped_column(String(8))
    confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class JobAgency(Base):
    """A potential client agency: business data only."""

    __tablename__ = "job_agencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    name_norm: Mapped[str] = mapped_column(String(200), index=True)
    domain: Mapped[str | None] = mapped_column(String(120), index=True)
    phone_norm: Mapped[str | None] = mapped_column(String(32), index=True)
    email: Mapped[str | None] = mapped_column(String(160))
    website: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(16))  # telegram|jobboerse
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    signals_count: Mapped[int] = mapped_column(Integer, default=0)
    digest_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
