import csv
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.database.models import JobChat, JobKeyword
from app.database.repositories.jobs_radar import JobsRadarRepository
from app.jobs_radar.discovery import FoundLink, extract_links
from app.jobs_radar.scoring import ACTIVE_MIN_POSTS_PER_DAY, score_chat
from app.jobs_radar.tglinks import ChatLink, message_link, parse_chat_link
from tests.conftest import ADMIN_ID, Harness

FIXTURE = Path(__file__).parent / "fixtures" / "job_chats_sample.csv"


# ---------- tglinks ----------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("@biz_kyiv", ChatLink("username", "biz_kyiv")),
        ("t.me/biz_kyiv", ChatLink("username", "biz_kyiv")),
        ("https://t.me/biz_kyiv/", ChatLink("username", "biz_kyiv")),
        ("  https://telegram.me/Biz_Kyiv  ", ChatLink("username", "Biz_Kyiv")),
        ("https://t.me/+AbCdEf123_-x", ChatLink("invite", "AbCdEf123_-x")),
        ("t.me/joinchat/AbCdEf123456", ChatLink("invite", "AbCdEf123456")),
    ],
)
def test_parse_valid(raw, expected):
    assert parse_chat_link(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "hello", "https://example.com/x", "t.me/c/123/45", "t.me/biz_kyiv/45", "@ab", "t.me/+short"],
)
def test_parse_invalid(raw):
    assert parse_chat_link(raw) is None


def test_identifier_canonical():
    assert ChatLink("username", "biz").identifier == "@biz"
    assert ChatLink("username", "Biz_Kyiv").identifier == "@biz_kyiv"
    assert ChatLink("invite", "AbCdEf123").identifier == "https://t.me/+AbCdEf123"


def test_message_link():
    assert message_link(-1001234567890, 45, "biz") == "https://t.me/biz/45"
    assert message_link(-1001234567890, 45) == "https://t.me/c/1234567890/45"
    assert message_link(-123456, 45) is None


# ---------- discovery ----------

def test_extract_links_and_mentions():
    text = "Join https://t.me/work_berlin or t.me/+AbCdEf123456, ask @Work_Munich. Mail a@example.com"
    found = extract_links(text)
    assert FoundLink(ChatLink("username", "work_berlin"), "link") in found
    assert FoundLink(ChatLink("invite", "AbCdEf123456"), "link") in found
    assert FoundLink(ChatLink("username", "Work_Munich"), "mention") in found
    assert len(found) == 3


def test_extract_dedup_and_bots_and_non_chat_paths():
    text = "@Work_Berlin t.me/work_berlin @some_helper_bot t.me/c/123/45 t.me/addstickers/pack t.me/work_berlin/77"
    found = extract_links(text)
    assert [f.link.value.lower() for f in found] == ["work_berlin"]
    assert found[0].source == "link"


# ---------- scoring ----------

def test_score_zero_and_none_members():
    assert score_chat(0, None, 0, None, False, "unknown") == 0.0


def test_score_caps_and_bonuses():
    assert score_chat(100, 10**9, 1.0, "uk", True, "yes") == 100.0
    assert score_chat(20, 0, 0, None, False, "unknown") == 40.0
    assert score_chat(200, 0, 0, None, False, "unknown") == 40.0  # activity cap


def test_score_ads_penalty_and_clamp():
    base = score_chat(20, 0, 0, "uk", False, "unknown")
    assert score_chat(20, 0, 0, "uk", False, "no") == round(base - 15, 1)
    assert score_chat(0, 0, 0, None, False, "no") == 0.0
    assert ACTIVE_MIN_POSTS_PER_DAY == 1.0


# ---------- repository ----------

async def test_candidates_dedup_and_no_resurrection(sm):
    async with sm() as s:
        repo = JobsRadarRepository(s)
        chat, created = await repo.add_manual(ChatLink("username", "Work_Berlin"))
        assert created and chat.status == "approved" and chat.username == "work_berlin"
        _, created_again = await repo.add_manual(ChatLink("username", "WORK_BERLIN"))
        assert not created_again

        links = [FoundLink(ChatLink("username", "Work_Berlin"), "mention"),
                 FoundLink(ChatLink("username", "new_chat_one"), "link"),
                 FoundLink(ChatLink("invite", "AbCdEf123456"), "link")]
        assert await repo.add_candidates(links, via_chat_id=5) == 2
        assert await repo.add_candidates(links, via_chat_id=5) == 0

        cand = await repo.get_by_username("new_chat_one")
        assert cand.status == "candidate" and cand.entity_type == "unknown"
        assert cand.discovered_from == "link" and cand.discovered_via_chat_id == 5

        await repo.set_status(cand.id, "rejected")
        assert await repo.add_candidates([FoundLink(ChatLink("username", "NEW_chat_one"), "mention")]) == 0
        assert (await repo.get_by_username("new_chat_one")).status == "rejected"
        await s.commit()


async def test_user_entities_hidden_from_candidates(sm):
    async with sm() as s:
        repo = JobsRadarRepository(s)
        await repo.add_candidates([FoundLink(ChatLink("username", "person_one"), "mention"),
                                   FoundLink(ChatLink("username", "real_chat"), "link")])
        (await repo.get_by_username("person_one")).entity_type = "user"
        await s.flush()
        assert [c.username for c in await repo.list_candidates()] == ["real_chat"]


async def test_keywords_seed_once(sm):
    async with sm() as s:
        repo = JobsRadarRepository(s)
        assert await repo.seed_keywords_if_empty() > 0
        assert await repo.seed_keywords_if_empty() == 0
        assert await s.scalar(select(func.count(JobKeyword.id))) > 0


async def test_import_csv_idempotent(sm):
    with FIXTURE.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 10
    async with sm() as s:
        assert await JobsRadarRepository(s).import_rows(rows) == (10, 0)
        await s.commit()
    async with sm() as s:
        repo = JobsRadarRepository(s)
        assert await repo.import_rows(rows) == (0, 10)
        await s.commit()
        assert await s.scalar(select(func.count(JobChat.id))) == 10
        chat = await repo.get_by_username("radar_test_chat_04")
        assert chat.ads_allowed == "no" and chat.status == "approved" and chat.discovered_from == "seed"


async def test_import_rejects_bad_ads_value(sm):
    async with sm() as s:
        with pytest.raises(ValueError):
            await JobsRadarRepository(s).import_rows([{"username": "radar_test_chat_01", "ads_allowed": "maybe"}])


# ---------- admin flow ----------

@pytest.fixture
def radar_on(settings, sm):
    return Harness(settings.model_copy(update={"jobs_radar_enabled": True}), sm)


async def _count(sm) -> int:
    async with sm() as s:
        return await s.scalar(select(func.count(JobChat.id)))


async def test_admin_add_job_chat(radar_on, sm):
    h = radar_on
    await h.send(ADMIN_ID, "/add_job_chat")
    assert any("Формат" in t for t in h.session.texts())
    h.session.clear()
    await h.send(ADMIN_ID, "/add_job_chat @radar_test_chat_01")
    assert await _count(sm) == 1
    assert any("добавлен" in t for t in h.session.texts())
    h.session.clear()
    await h.send(ADMIN_ID, "/add_job_chat t.me/Radar_Test_Chat_01")
    assert await _count(sm) == 1
    assert any("Уже есть" in t and "approved" in t for t in h.session.texts())


async def test_non_admin_gets_no_radar_response(radar_on, sm):
    h = radar_on
    await h.send(12345, "/add_job_chat @radar_test_chat_01")
    assert await _count(sm) == 0
    assert not any("добавлен" in t or "Формат" in t or "Уже есть" in t for t in h.session.texts())


async def test_admin_candidates_and_approve(radar_on, sm):
    h = radar_on
    await h.send(ADMIN_ID, "/job_candidates")
    assert "Кандидатов нет." in h.session.texts()
    async with sm() as s:
        await JobsRadarRepository(s).add_candidates([FoundLink(ChatLink("username", "cand_chat_one"), "link")])
        await s.commit()
        cid = (await JobsRadarRepository(s).get_by_username("cand_chat_one")).id
    h.session.clear()
    await h.send(ADMIN_ID, "/job_candidates")
    assert any("@cand_chat_one" in t for t in h.session.texts())
    await h.press(ADMIN_ID, f"jr:ok:{cid}")
    async with sm() as s:
        assert (await JobsRadarRepository(s).get(cid)).status == "approved"
    h.session.clear()
    await h.press(ADMIN_ID, "jr:no:9999")
    assert any(getattr(c, "show_alert", False) for c in h.session.calls)


async def test_non_admin_cannot_press_radar_buttons(radar_on, sm):
    async with sm() as s:
        await JobsRadarRepository(s).add_candidates([FoundLink(ChatLink("username", "cand_chat_two"), "link")])
        await s.commit()
        cid = (await JobsRadarRepository(s).get_by_username("cand_chat_two")).id
    await radar_on.press(12345, f"jr:ok:{cid}")
    async with sm() as s:
        assert (await JobsRadarRepository(s).get(cid)).status == "candidate"


async def test_flag_off_radar_router_not_attached(h, sm):
    async with sm() as s:
        await JobsRadarRepository(s).add_candidates([FoundLink(ChatLink("username", "cand_chat_three"), "link")])
        await s.commit()
    await h.send(ADMIN_ID, "/job_candidates")
    await h.send(ADMIN_ID, "/add_job_chat @radar_test_chat_01")
    texts = " ".join(h.session.texts())
    assert "Кандидатов" not in texts and "cand_chat_three" not in texts
    assert await _count(sm) == 1  # only the candidate created above


async def test_reimport_status_rules_and_blank_cells(sm):
    row = {"username": "radar_test_chat_01", "title": "T", "city": "Berlin", "land": "BE",
           "language": "uk", "ads_allowed": "yes"}
    async with sm() as s:
        repo = JobsRadarRepository(s)
        await repo.import_rows([row, {**row, "username": "radar_test_chat_02"},
                                {**row, "username": "radar_test_chat_03"}])
        await repo.set_status((await repo.get_by_username("radar_test_chat_01")).id, "joined")
        await repo.set_status((await repo.get_by_username("radar_test_chat_02")).id, "rejected")
        await repo.set_status((await repo.get_by_username("radar_test_chat_03")).id, "candidate")
        blank = {"title": "", "city": "", "land": "", "language": "", "ads_allowed": ""}
        await repo.import_rows([{**blank, "username": f"radar_test_chat_0{i}"} for i in (1, 2, 3)])
        c1, c2, c3 = [await repo.get_by_username(f"radar_test_chat_0{i}") for i in (1, 2, 3)]
        assert (c1.status, c2.status, c3.status) == ("joined", "approved", "approved")
        assert (c1.title, c1.city, c1.land, c1.language, c1.ads_allowed) == ("T", "Berlin", "BE", "uk", "yes")


@pytest.mark.parametrize("field,value", [("language", "x" * 9), ("land", "x" * 9), ("city", "x" * 81),
                                          ("title", "x" * 256), ("username", "a" + "b" * 64)])
async def test_import_rejects_too_long_values(sm, field, value):
    row = {"username": "radar_test_chat_01", field: value}
    async with sm() as s:
        with pytest.raises(ValueError):
            await JobsRadarRepository(s).import_rows([row])


async def test_stale_button_does_not_change_processed_chat(radar_on, sm):
    async with sm() as s:
        repo = JobsRadarRepository(s)
        chat, _ = await repo.add_manual(ChatLink("username", "stale_chat_one"))
        await repo.set_status(chat.id, "joined")
        await s.commit()
        cid = chat.id
    await radar_on.press(ADMIN_ID, f"jr:no:{cid}")
    async with sm() as s:
        assert (await JobsRadarRepository(s).get(cid)).status == "joined"
    assert any(getattr(c, "show_alert", False) for c in radar_on.session.calls)
