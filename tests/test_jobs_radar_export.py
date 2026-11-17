import csv
import io
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from aiogram.methods import SendDocument

from app.admin.handlers import ADMIN_HELP
from app.database.models import JobAgency, JobChat, JobSignal
from app.database.repositories.jobs_radar import JobsRadarRepository
from app.jobs_radar.export import agencies_csv, sources_csv
from tests.conftest import ADMIN_ID, Harness

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)


async def _seed(sm):
    async with sm() as s:
        for i in range(54):
            s.add(JobChat(username=f"chat_{i:02d}", title=f"Chat {i}", status="joined" if i % 2 else "approved",
                          discovered_from="seed", entity_type="group", score=i,
                          posts_per_day_7d=2.0 if i % 3 == 0 else 0.5, members=100 + i))
        for i in range(3):
            s.add(JobChat(username=f"rej_{i}", status="rejected", discovered_from="seed", entity_type="group",
                          score=1000))
        for i in range(3):
            s.add(JobChat(username=f"usr_{i}", status="candidate", discovered_from="mention", entity_type="user",
                          score=900))
        for i in range(35):
            s.add(JobAgency(name=f"Agency {i:02d}", name_norm=f"agency {i:02d}", source="telegram",
                            signals_count=i, first_seen_at=NOW - timedelta(days=i), last_seen_at=NOW - timedelta(days=i)))
        s.add(JobAgency(name="Tie old", name_norm="tie old", source="telegram", signals_count=34,
                        first_seen_at=NOW - timedelta(days=40), last_seen_at=NOW - timedelta(days=40)))
        s.add(JobSignal(chat_id=1, message_link="l1", kind="agency_vacancy", confidence=0.9, created_at=NOW - timedelta(days=1)))
        s.add(JobSignal(chat_id=1, message_link="l2", kind="agency_vacancy", confidence=0.9, created_at=NOW - timedelta(days=2)))
        s.add(JobSignal(chat_id=1, message_link="l3", kind="seeker_question", confidence=0.9, created_at=NOW - timedelta(days=3)))
        s.add(JobSignal(chat_id=1, message_link="l4", kind="seeker_question", confidence=0.9, created_at=NOW - timedelta(days=20)))
        await s.commit()


async def test_top_sources_order_and_filters(sm):
    await _seed(sm)
    async with sm() as s:
        rows = await JobsRadarRepository(s).top_sources()
    assert len(rows) == 50
    assert all(r.status != "rejected" and r.entity_type != "user" for r in rows)
    assert [r.score for r in rows] == list(range(53, 3, -1))


async def test_top_sources_tiebreak_by_posts(sm):
    async with sm() as s:
        for name, ppd in (("a_chat", 1.0), ("b_chat", 5.0)):
            s.add(JobChat(username=name, status="approved", discovered_from="seed", score=10, posts_per_day_7d=ppd))
        await s.commit()
        rows = await JobsRadarRepository(s).top_sources()
    assert [r.username for r in rows] == ["b_chat", "a_chat"]


async def test_top_agencies_order(sm):
    await _seed(sm)
    async with sm() as s:
        rows = await JobsRadarRepository(s).top_agencies()
    assert len(rows) == 30
    assert [r.name for r in rows[:3]] == ["Agency 34", "Tie old", "Agency 33"]
    assert [r.signals_count for r in rows] == sorted((r.signals_count for r in rows), reverse=True)


async def test_radar_stats(sm):
    await _seed(sm)
    async with sm() as s:
        st = await JobsRadarRepository(s).radar_stats(NOW)
    assert st["chats_by_status"] == {"joined": 27, "approved": 27, "rejected": 3, "candidate": 3}
    assert st["active_chats"] == 9  # joined (odd i) with i % 3 == 0 -> 3, 9, ..., 51
    assert st["signals_7d"] == {"agency_vacancy": 2, "seeker_question": 1}
    assert st["agencies_total"] == 36
    assert st["agencies_new_7d"] == 8  # first seen 0..7 days ago


def _parse(data: bytes) -> list[list[str]]:
    assert data.startswith(b"\xef\xbb\xbf")
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))


async def test_csv_files_parse(sm):
    await _seed(sm)
    async with sm() as s:
        repo = JobsRadarRepository(s)
        src, ag = _parse(sources_csv(await repo.top_sources())), _parse(agencies_csv(await repo.top_agencies()))
    assert src[0][:3] == ["username", "title", "status"] and len(src) == 51 and len(src[0]) == 13
    assert ag[0][0] == "name" and len(ag) == 31 and len(ag[0]) == 9
    assert all(len(r) == 13 for r in src) and all(len(r) == 9 for r in ag)


def test_csv_injection_guard():
    def agency(name, phone=None):
        return SimpleNamespace(name=name, website=None, domain=None, email=None, phone_norm=phone, source="telegram",
                               signals_count=1, first_seen_at=NOW, last_seen_at=NOW)

    rows = _parse(agencies_csv([agency("=cmd"), agency("@x"), agency("-1"), agency("+49 000 1234567"),
                                agency("+evil", "+49 (30) 123-45"), agency("ok; name")]))
    names = [r[0] for r in rows[1:]]
    assert names == ["'=cmd", "'@x", "'-1", "+49 000 1234567", "'+evil", "ok; name"]
    assert rows[5][4] == "+49 (30) 123-45"
    assert rows[1][7] == NOW.isoformat()


# ---------- admin flow ----------

@pytest.fixture
def radar_on(settings, sm):
    return Harness(settings.model_copy(update={"jobs_radar_enabled": True}), sm)


def _documents(h):
    return [c for c in h.session.calls if isinstance(c, SendDocument)]


async def test_admin_lists_and_csv(radar_on, sm):
    h = radar_on
    await h.send(ADMIN_ID, "/job_sources")
    await h.send(ADMIN_ID, "/job_agencies")
    assert h.session.texts() == ["Пусто.", "Пусто."]
    await h.press(ADMIN_ID, "jr:csv:sources")
    assert not _documents(h)

    await _seed(sm)
    h.session.clear()
    await h.send(ADMIN_ID, "/job_sources")
    texts = h.session.texts()
    assert all(len(t) <= 4000 for t in texts)
    joined = "\n".join(texts)
    assert "1. Chat 53" in joined and "50. Chat 4 " in joined and "51." not in joined
    kbs = [c.reply_markup for c in h.session.calls if getattr(c, "reply_markup", None)]
    assert [b.callback_data for k in kbs for r in k.inline_keyboard for b in r] == ["jr:csv:sources"]

    h.session.clear()
    await h.send(ADMIN_ID, "/job_agencies")
    assert "1. Agency 34" in "\n".join(h.session.texts()) and "31." not in "\n".join(h.session.texts())

    h.session.clear()
    await h.press(ADMIN_ID, "jr:csv:sources")
    await h.press(ADMIN_ID, "jr:csv:agencies")
    docs = _documents(h)
    assert [d.document.filename for d in docs] == ["job_sources.csv", "job_agencies.csv"]
    assert docs[0].document.data.startswith(b"\xef\xbb\xbf")


async def test_non_admin_gets_no_lists_or_files(radar_on, sm):
    await _seed(sm)
    await radar_on.send(12345, "/job_sources")
    await radar_on.send(12345, "/job_agencies")
    await radar_on.press(12345, "jr:csv:sources")
    assert not any("Chat" in t or "Agency" in t for t in radar_on.session.texts())
    assert not _documents(radar_on)


async def test_old_callbacks_still_work_with_csv_regex(radar_on, sm):
    async with sm() as s:
        s.add(JobChat(username="cand_x", status="candidate", discovered_from="link"))
        await s.commit()
        cid = (await JobsRadarRepository(s).get_by_username("cand_x")).id
    await radar_on.press(ADMIN_ID, f"jr:ok:{cid}")
    async with sm() as s:
        assert (await JobsRadarRepository(s).get(cid)).status == "approved"


# ---------- /stats and /admin ----------

async def test_stats_and_admin_flag_on_vs_off(h, radar_on, sm):
    await _seed(sm)
    await h.send(ADMIN_ID, "/stats")
    await h.send(ADMIN_ID, "/admin")
    off_stats, off_admin = h.session.texts()
    assert "Радар" not in off_stats and "job_sources" not in off_admin
    assert off_admin == ADMIN_HELP

    await radar_on.send(ADMIN_ID, "/stats")
    await radar_on.send(ADMIN_ID, "/admin")
    on_stats, on_admin = radar_on.session.texts()
    assert on_stats.startswith(off_stats) and on_stats[len(off_stats):].startswith("\n\n<b>Радар вакансий</b>")
    assert "Активные чаты: 9" in on_stats and "Агентства: 36" in on_stats
    assert on_admin.startswith(off_admin)
    for cmd in ("/add_job_chat", "/job_candidates", "/job_sources", "/job_agencies"):
        assert cmd in on_admin
