"""Offline demo of the Jobs Source Radar: `python -m app.jobs_radar.demo [--out DIR] [--days N]`.

Runs the whole cycle (import, joins, metadata, live messages, catch-up, classification, agencies, digest,
retention purge, CSV export) on synthetic data. It never touches the configured database (a throw-away SQLite
file in a temp dir is used and deleted), never builds a Telegram client, never opens a network connection
and needs no credentials. Time is simulated, so several days run in a few seconds.
"""
import argparse
import asyncio
import contextlib
import html
import logging
import re
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.data.jobs_radar_demo import CHATS, MESSAGES, DemoChat
from app.database.models import Base, JobAgency, JobChat, JobRadarAction, JobSignal, utcnow
from app.database.repositories.jobs_radar import JobsRadarRepository
from app.database.session import make_engine, make_sessionmaker
from app.jobs_radar.catchup import catch_up_all
from app.jobs_radar.classifier import Classification, RuleClassifier
from app.jobs_radar.demo_fake import DemoClient
from app.jobs_radar.export import agencies_csv, sources_csv
from app.jobs_radar.monitor import Monitor
from app.jobs_radar.tglinks import message_link, parse_chat_link

TICK = timedelta(minutes=30)
ADMIN_ID = 1
WIDTH = 78

LABELS = {
    "seeker_question": "соискатель",
    "agency_vacancy": "агентство",
    "chat_rules": "правила чата",
    "noise": "шум",
}
JOIN_RESULTS = {
    "joined": "вступил",
    "already_participant": "уже участник",
    "request_sent": "заявка отправлена, ждём одобрения",
}


class Clock:
    """Simulated time, passed to every component that accepts a clock."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


async def _no_sleep(_seconds: float) -> None:
    return None


@dataclass
class Sent:
    at: datetime
    chat_id: int
    text: str
    parse_mode: str | None


class DemoBot:
    """Instead of sending, remembers what the admins would receive."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.sent: list[Sent] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append(Sent(self.clock(), chat_id, text, kwargs.get("parse_mode")))


class RecordingClassifier:
    """The real rule classifier plus a memory of its answers (noise is not stored in the database)."""

    def __init__(self, inner: RuleClassifier) -> None:
        self.inner = inner
        self.by_text: dict[str, Classification] = {}

    async def classify(self, text: str) -> Classification:
        result = await self.inner.classify(text)
        self.by_text[text.strip()] = result
        return result


@dataclass
class DayStat:
    day: int
    date: str
    live: int = 0
    caught_up: int = 0


@dataclass
class DemoResult:
    days: int
    seeds_created: int = 0
    keywords: int = 0
    approvals: list[tuple[int, str, str]] = field(default_factory=list)
    actions: list[tuple[datetime, str, str, str]] = field(default_factory=list)
    chats: list[JobChat] = field(default_factory=list)
    deleted_users: list[str] = field(default_factory=list)
    day_stats: list[DayStat] = field(default_factory=list)
    baselines: dict[str, int] = field(default_factory=dict)
    rows: list[tuple] = field(default_factory=list)  # classification table
    skipped: Counter = field(default_factory=Counter)
    discovered: list[tuple[str, str, str, str]] = field(default_factory=list)
    agencies: list[JobAgency] = field(default_factory=list)
    alerts: list[Sent] = field(default_factory=list)
    digests: list[Sent] = field(default_factory=list)
    aged: int = 0
    signals_purged: int = 0
    signals_after_purge: int = 0
    stats: dict = field(default_factory=dict)
    sources_path: Path | None = None
    agencies_path: Path | None = None


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _name(chat: JobChat | DemoChat | None) -> str:
    if chat is None:
        return "удалённая запись"
    if chat.username:
        return f"@{chat.username}"
    return "приватная ссылка"


def _make_settings(db_url: str) -> Settings:
    """Built explicitly: the demo ignores .env and the real environment (dummy token, local SQLite only)."""
    return Settings(
        _env_file=None, bot_token="0:demo", database_url=db_url, admin_ids=[ADMIN_ID],
        jobs_radar_enabled=True, jobs_join_daily_cap=3, jobs_metadata_daily_cap=50,
        jobs_classifier="rules", jobs_signal_retention_days=14, jobs_digest_hour=9,
    )


async def _backdate(sm: async_sessionmaker, links: dict[str, int]) -> int:
    """Age the signals of the "old" demo messages (the demo has no weeks of real history to wait for)."""
    done = 0
    async with sm() as session:
        for link, age_days in links.items():
            res = await session.execute(
                update(JobSignal).where(JobSignal.message_link == link)
                .values(created_at=utcnow() - timedelta(days=age_days))
            )
            done += res.rowcount or 0
        await session.commit()
    return done


async def _count_signals(sm: async_sessionmaker) -> int:
    async with sm() as session:
        return await session.scalar(select(func.count(JobSignal.id))) or 0


async def _approve_candidates(mon: Monitor, day: int, result: DemoResult) -> None:
    """In the bot an admin presses a button under each candidate; here the script does it for real chats only."""
    await mon.metadata.step()  # check what was discovered late in the day
    async with mon.sm() as session:
        repo = JobsRadarRepository(session)
        for chat in await repo.list_candidates(limit=10):
            if chat.entity_type in ("group", "channel"):
                await repo.set_status(chat.id, "approved")
                result.approvals.append((day, f"{_name(chat)} ({chat.title})", "одобрен"))
            elif not any(a[1] == _name(chat) for a in result.approvals):
                result.approvals.append((day, _name(chat), "оставлен кандидатом: не удалось проверить"))
        await session.commit()


async def _simulate(days: int, db_url: str, out_dir: Path) -> DemoResult:
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    def day_start(day: int) -> datetime:
        return midnight - timedelta(days=days - 1 - day)

    clock = Clock(day_start(0))
    messages = [replace(m, day=min(m.day, days - 1)) for m in MESSAGES]
    tg = DemoClient(CHATS, messages, clock, day_start)
    bot = DemoBot(clock)
    result = DemoResult(days=days)

    engine = make_engine(db_url)

    @event.listens_for(engine.sync_engine, "connect")
    def _fast_throwaway_db(dbapi_connection, _record):  # the file is deleted at the end: no need to fsync
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA synchronous=OFF")
        cursor.execute("PRAGMA journal_mode=MEMORY")
        cursor.close()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sm = make_sessionmaker(engine)
        settings = _make_settings(db_url)
        mon = Monitor(settings, tg, sm, bot)
        recorder = RecordingClassifier(RuleClassifier())
        mon.pipeline.classifier = recorder
        for part in (mon.joiner, mon.metadata):  # simulated clock, no real pauses
            part.clock, part.sleep, part.rand = clock, _no_sleep, lambda a, b: a

        # 1. import of seed chats and approval (what /add_job_chat and the CSV import do)
        async with sm() as session:
            repo = JobsRadarRepository(session)
            result.keywords = await repo.seed_keywords_if_empty()
            rows = [
                {"username": c.username, "language": c.language, "city": c.city}
                for c in CHATS if c.seed and c.username
            ]
            created, _ = await repo.import_rows(rows)
            for c in CHATS:
                if c.seed and c.invite_hash:
                    link = parse_chat_link(f"https://t.me/+{c.invite_hash}")
                    created += (await repo.add_manual(link))[1]
            result.seeds_created = created
            await session.commit()
        await mon.refresh()

        # 2-4. simulated days: metadata and joins every 30 minutes, live messages, evening catch-up
        for day in range(days):
            stat = DayStat(day + 1, day_start(day).date().isoformat())
            end = day_start(day) + timedelta(days=1)
            t = prev = day_start(day)
            while t < end:
                clock.now = t
                await mon.metadata.step()
                await mon.joiner.step()  # its on_joined hook refreshes state and sets the baseline
                for chat, m in tg.due(prev, t):
                    if m.spec.offline:
                        continue  # the monitor was "offline": the catch-up has to find it
                    tg_id = tg.tg_id(chat)
                    stat.live += tg_id in mon.state
                    await mon.on_new_message(SimpleNamespace(
                        chat_id=tg_id, out=False, chat=SimpleNamespace(username=chat.username),
                        message=SimpleNamespace(id=m.id, message=m.message, date=m.date),
                    ))
                prev, t = t, t + TICK
            clock.now = end - timedelta(minutes=1)
            served = sum(tg.served_by_catchup.values())
            await catch_up_all(tg, mon.pipeline, alert=mon.notifier.alert, sleep=_no_sleep)
            stat.caught_up = sum(tg.served_by_catchup.values()) - served
            result.day_stats.append(stat)

            old_links = {
                message_link(tg.tg_id(chat), m.id, chat.username): m.spec.age_days
                for chat, m in tg.due(day_start(day), end) if m.spec.age_days
            }
            result.aged += await _backdate(sm, old_links)
            await _approve_candidates(mon, day + 1, result)

            before = await _count_signals(sm)
            await mon.daily_job()  # recompute stats and scores, purge, agency digest
            result.signals_after_purge = await _count_signals(sm)
            result.signals_purged += before - result.signals_after_purge

        # collect everything the report shows
        async with sm() as session:
            repo = JobsRadarRepository(session)
            chats = list((await session.scalars(select(JobChat).order_by(JobChat.id))).all())
            names = {c.id: _name(c) for c in chats}
            for a in (await session.scalars(select(JobRadarAction).order_by(JobRadarAction.at, JobRadarAction.id))):
                label = names.get(a.chat_id, "—") if a.chat_id else "—"
                result.actions.append((_aware(a.at), a.kind, label, a.result))
            result.chats = chats
            present = {c.username for c in chats}
            result.deleted_users = [c.username for c in CHATS if c.kind == "user" and c.username not in present]
            for c in chats:
                if c.discovered_from != "seed":
                    via = names.get(c.discovered_via_chat_id, "—")
                    result.discovered.append((_name(c), c.discovered_from, via, c.status))
            sources = await repo.top_sources(limit=50)
            result.agencies = await repo.top_agencies(limit=30)
            result.stats = await repo.radar_stats(utcnow())
            out_dir.mkdir(parents=True, exist_ok=True)
            result.sources_path = out_dir / "sources.csv"
            result.agencies_path = out_dir / "agencies.csv"
            result.sources_path.write_bytes(sources_csv(sources))
            result.agencies_path.write_bytes(agencies_csv(result.agencies))

            by_tg = {c.tg_chat_id: c for c in chats if c.tg_chat_id}
        for tg_id, items in tg.history.items():
            chat = tg.chat_of(tg_id)
            row = by_tg.get(tg_id)
            baseline = tg.baselines.get(tg_id)
            if baseline is not None:
                result.baselines[_name(chat)] = baseline
            for m in items:
                if row is None:
                    result.skipped["чат не вступлен, сообщения не читаются"] += 1
                elif baseline is not None and m.id <= baseline:
                    result.skipped["история до вступления"] += 1
                elif row.last_message_id is None or m.id > row.last_message_id:
                    result.skipped["после конца демо"] += 1
                else:
                    cls = recorder.by_text.get(m.message.strip())
                    result.rows.append((m.date, m.id, _name(chat), cls, m.message))
        result.rows.sort(key=lambda r: (r[0], r[1]))
        result.alerts = [s for s in bot.sent if not s.parse_mode]
        result.digests = [s for s in bot.sent if s.parse_mode]
        return result
    finally:
        await engine.dispose()


# --- console report (Russian, admin-facing) ---


def _short(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _hm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _head(num: int, title: str) -> list[str]:
    return ["", "=" * WIDTH, f"{num}. {title}", "=" * WIDTH]


def _details(c: Classification | None) -> str:
    if c is None:
        return "отсеяно префильтром"
    parts = [f"{c.confidence:.2f}"]
    if c.label == "agency_vacancy":
        parts += [x for x in (c.company, c.phone or c.website or c.email) if x]
    else:
        parts += [x for x in (c.city, c.profession) if x]
    return ", ".join(parts)


def render(r: DemoResult) -> list[str]:
    out = [f"Демо радара источников вакансий: {r.days} дн., без Telegram, сети и боевой базы."]
    out += _head(1, "Импорт и одобрение кандидатов")
    seeds = [c for c in CHATS if c.seed]
    out.append(f"Загружено стартовых ключевых слов: {r.keywords}. Добавлено чатов (статус approved): {r.seeds_created}.")
    out.append("Среди них: открытые чаты, одна закрытая инвайт-ссылка и одна ссылка на человека (по ошибке).")
    out.append(f"Всего в стартовом списке: {len(seeds)}. Вступать радар будет только в approved.")
    out.append("Кандидаты, найденные в сообщениях (в боте админ жмёт «Одобрить»/«Отклонить»):")
    for day, name, action in r.approvals:
        out.append(f"  день {day}: {name} — {action}")
    if not r.approvals:
        out.append("  кандидатов не было")

    out += _head(2, "Вступления по дням (лимит 3 в сутки, паузы, FloodWait)")
    by_day: dict[int, list] = {}
    first = min((a[0] for a in r.actions), default=None)
    for at, kind, label, res in r.actions:
        if kind == "join":
            by_day.setdefault((at.date() - first.date()).days + 1, []).append((at, label, res))
    for day in range(1, r.days + 1):
        rows = by_day.get(day, [])
        out.append(f"День {day}: попыток вступления {len(rows)} из 3")
        for at, label, res in rows:
            if res.startswith("flood@"):
                until = datetime.fromisoformat(res.partition("@")[2])
                text = f"FloodWait: Telegram просит подождать, вступления стоят до {_hm(until)}"
            else:
                text = JOIN_RESULTS.get(res, res)
            out.append(f"  {_hm(at)}  {label}: {text}")
    out.append("Уведомления, которые получили бы админы (бот не отправляет, только запоминает):")
    for s in r.alerts:
        out.append(f"  [{s.at:%d.%m %H:%M}] админу {s.chat_id}: {_short(s.text, 100)}")

    out += _head(3, "Метаданные чатов и оценка")
    counts = Counter(a[3].split("@")[0] for a in r.actions if a[1] == "metadata")
    out.append("Проверки метаданных: " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    for name in r.deleted_users:
        out.append(f"Удалено из каталога: @{name} — это человек, не чат (личные данные не храним).")
    out.append(f"  {'чат':<22}{'тип':<8}{'участн.':>8}  {'реклама':<8}{'контакт':<22}{'оценка':>6}  статус")
    for c in sorted(r.chats, key=lambda c: -c.score):
        out.append(
            f"  {_name(c):<22}{c.entity_type:<8}{c.members if c.members is not None else '?':>8}  "
            f"{c.ads_allowed:<8}{c.admin_contact or '—':<22}{c.score:>6g}  {c.status}"
        )

    out += _head(4, "Входящие сообщения и догоняющее чтение")
    for s in r.day_stats:
        out.append(f"День {s.day} ({s.date}): живых сообщений {s.live}, прочитано при догоне {s.caught_up}")
    out.append("Точка отсчёта при вступлении (историю не читаем): " + (
        ", ".join(f"{n} → id {b}" for n, b in r.baselines.items()) or "—"))
    for reason, n in r.skipped.items():
        out.append(f"Не обработано: {reason} — {n}")
    out.append("Ссылки на другие чаты, найденные в сообщениях:")
    for name, source, via, status in r.discovered:
        out.append(f"  {name} ({source}, из {via}) — {status}")

    out += _head(5, "Классификация сообщений")
    out.append(f"  {'id':<6}{'чат':<20}{'метка':<14}детали / текст")
    for _, mid, chat, cls, text in r.rows:
        label = LABELS[cls.label] if cls else "—"
        out.append(f"  {mid:<6}{chat.replace('@radar_demo_', ''):<20}{label:<14}{_details(cls)}")
        out.append(f"  {'':<40}«{_short(text, 62)}»")
    labels = Counter((LABELS[c.label] if c else "отсеяно префильтром") for _, _, _, c, _ in r.rows)
    out.append("Итого: " + ", ".join(f"{k}: {v}" for k, v in labels.most_common()))

    out += _head(6, "Найденные агентства")
    out.append(f"  {'название':<30}{'сайт':<30}{'e-mail':<34}{'телефон':<16}упом.")
    for a in r.agencies:
        out.append(
            f"  {_short(a.name, 28):<30}{a.website or '—':<30}{a.email or '—':<34}"
            f"{a.phone_norm or '—':<16}{a.signals_count}"
        )

    out += _head(7, "Дайджест, который получили бы админы")
    for s in r.digests:
        text = html.unescape(re.sub(r"</?b>", "", s.text))
        out.append(f"[{s.at:%d.%m %H:%M}] админу {s.chat_id}:")
        out += [f"  {line}" for line in text.splitlines()]
    if not r.digests:
        out.append("новых агентств не было")

    out += _head(8, "Чистка сигналов по сроку хранения (14 дней)")
    out.append(f"Для показа состарено сигналов: {r.aged} (в демо нет двух недель реальной истории).")
    out.append(
        f"Удалено чисткой: {r.signals_purged}, осталось сигналов: {r.signals_after_purge} "
        f"(в базе только метки, текстов сообщений нет)."
    )

    out += _head(9, "Итоговые счётчики (как в /stats)")
    s = r.stats
    out.append("Чатов по статусам: " + ", ".join(f"{k}: {v}" for k, v in sorted(s["chats_by_status"].items())))
    out.append(f"Активных чатов (>= 1 поста в день): {s['active_chats']}")
    out.append("Сигналов за 7 дней: " + (", ".join(f"{k}: {v}" for k, v in sorted(s["signals_7d"].items())) or "0"))
    out.append(f"Агентств всего: {s['agencies_total']}, новых за 7 дней: {s['agencies_new_7d']}")
    out.append("")
    out.append(f"Файл источников: {r.sources_path}")
    out.append(f"Файл агентств:   {r.agencies_path}")
    return out


def main(argv: list[str] | None = None) -> int:
    with contextlib.suppress(AttributeError, ValueError, OSError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles (cp1251) fail on "ü" etc.
    parser = argparse.ArgumentParser(prog="python -m app.jobs_radar.demo", description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=None, help="folder for sources.csv and agencies.csv (default: new temp folder)")
    parser.add_argument("--days", type=int, default=3, help="simulated days (default 3)")
    args = parser.parse_args(argv)
    if args.days < 1:
        parser.error("--days must be at least 1")
    out_dir = args.out or Path(tempfile.mkdtemp(prefix="jobs_radar_demo_out_"))

    logging.disable(logging.WARNING)  # expected "warnings" (FloodWait etc.) are shown in the report instead
    try:
        with tempfile.TemporaryDirectory(prefix="jobs_radar_demo_db_", ignore_cleanup_errors=True) as db_dir:
            db_url = f"sqlite+aiosqlite:///{(Path(db_dir) / 'radar_demo.db').as_posix()}"
            result = asyncio.run(_simulate(args.days, db_url, out_dir))
    finally:
        logging.disable(logging.NOTSET)
    print("\n".join(render(result)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
