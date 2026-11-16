"""CSV export of radar sources and agencies: UTF-8 with BOM, ';' delimiter (opens in Excel), formula-injection guard."""
import csv
import io
import re
from collections.abc import Iterable
from datetime import datetime

SOURCE_COLUMNS = (
    "username", "title", "status", "entity_type", "members", "posts_per_day_7d", "ads_allowed",
    "admin_contact", "language", "city", "land", "score", "last_checked_at",
)
AGENCY_COLUMNS = (
    "name", "website", "domain", "email", "phone", "source", "signals_count", "first_seen_at", "last_seen_at",
)
_PHONE = re.compile(r"^\+[\d\s()/-]+$")  # a leading "-" is never a phone: "-1" must stay guarded


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value)
    if text[:1] in ("=", "@", "\t", "\r"):
        return "'" + text
    if text[:1] in ("+", "-") and not _PHONE.match(text):
        return "'" + text
    return text


def _build(header: Iterable[str], rows: Iterable[Iterable]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([_cell(v) for v in row])
    return buf.getvalue().encode("utf-8-sig")


def sources_csv(rows) -> bytes:
    return _build(SOURCE_COLUMNS, ([
        c.username, c.title, c.status, c.entity_type, c.members, c.posts_per_day_7d, c.ads_allowed,
        c.admin_contact, c.language, c.city, c.land, c.score, c.last_checked_at,
    ] for c in rows))


def agencies_csv(rows) -> bytes:
    return _build(AGENCY_COLUMNS, ([
        a.name, a.website, a.domain, a.email, a.phone_norm, a.source, a.signals_count,
        a.first_seen_at, a.last_seen_at,
    ] for a in rows))
