"""J1.2 monitor tests: everything runs on fakes, no Telegram connection and no network."""
import logging
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from telethon import errors
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import CheckChatInviteRequest
from telethon.tl.types import Channel, Chat, ChatInvite, ChatPhotoEmpty, User

from app.config import Settings
from app.database.models import JobChat, JobChatDaily, JobRadarAction, JobSignal
from app.database.repositories.jobs_radar import JobsRadarRepository
from app.jobs_radar import catchup, metadata, monitor
from app.jobs_radar.classifier import Classification
from app.jobs_radar.handler import IncomingMessage, Pipeline, handle_message
from app.jobs_radar.joiner import PAUSE_MAX_S, PAUSE_MIN_S, Joiner
from app.jobs_radar.metadata import MetadataCollector, parse_admin_contact, parse_ads_allowed
from app.jobs_radar.state import ChatRef, JoinedState

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
TERMS = (["ищу работу"], [])


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now


class StubClassifier:
    def __init__(self):
        self.calls = []

    async def classify(self, text):
        self.calls.append(text)
        return Classification(label="seeker_question", confidence=0.9, language="ru")


async def add_chat(sm, **kw) -> int:
    kw.setdefault("status", "approved")
    kw.setdefault("discovered_from", "seed")
    kw.setdefault("entity_type", "unknown")
    kw.setdefault("ads_allowed", "unknown")
    kw.setdefault("posts_per_day_7d", 0)
    kw.setdefault("score", 0)
    async with sm() as s:
        chat = JobChat(**kw)
        s.add(chat)
        await s.commit()
        return chat.id


async def get_chat(sm, chat_id) -> JobChat | None:
    async with sm() as s:
        return await JobsRadarRepository(s).get(chat_id)


async def actions(sm, kind=None) -> list[JobRadarAction]:
    async with sm() as s:
        q = select(JobRadarAction).order_by(JobRadarAction.id)
        if kind:
            q = q.where(JobRadarAction.kind == kind)
        return list((await s.scalars(q)).all())


# --- handler ---


@pytest.fixture
async def joined(sm):
    chat_id = await add_chat(sm, status="joined", tg_chat_id=-1001234567890, username="work_de")
    state = JoinedState()
    await state.reconcile(sm)
    pipeline = Pipeline(state, sm, StubClassifier(), lambda: TERMS)
    return chat_id, pipeline


def msg(text="привет", message_id=10, chat_id=-1001234567890, username=None, date_=NOW):
    return IncomingMessage(chat_id=chat_id, message_id=message_id, text=text, date=date_, chat_username=username)


async def test_handler_ignores_chats_not_joined(sm, joined):
    chat_id, pipeline = joined
    await handle_message(msg(chat_id=-1009999999999), pipeline)
    async with sm() as s:
        assert await s.scalar(select(func.count(JobChatDaily.chat_id))) == 0


async def test_handler_counts_daily_posts_and_tracks_last_id(sm, joined):
    chat_id, pipeline = joined
    await handle_message(msg(message_id=10), pipeline)
    await handle_message(msg(message_id=11), pipeline)
    await handle_message(msg(message_id=11), pipeline)  # duplicate (live + catch-up): counted once
    async with sm() as s:
        row = await s.get(JobChatDaily, (chat_id, NOW.date()))
        assert row.posts == 2
        assert (await JobsRadarRepository(s).get(chat_id)).last_message_id == 11


async def test_handler_stores_no_text_and_adds_candidates(sm, joined):
    chat_id, pipeline = joined
    secret = "ищу работу в Берлине, писать на t.me/new_jobs_chat или @other_jobs_group"
    await handle_message(msg(text=secret, username="work_de"), pipeline)
    async with sm() as s:
        names = {c.username for c in await s.scalars(select(JobChat))}
        assert {"new_jobs_chat", "other_jobs_group"} <= names
        via = {c.discovered_via_chat_id for c in await s.scalars(select(JobChat).where(JobChat.status == "candidate"))}
        assert via == {chat_id}
        stored = []
        for model in (JobChat, JobSignal):
            for row in await s.scalars(select(model)):
                stored += [str(v) for v in vars(row).values()]
        assert "Берлине" not in " ".join(stored)


async def test_handler_signal_links_public_and_private(sm):
    pub = await add_chat(sm, status="joined", tg_chat_id=-1001111111111, username="pubchat")
    priv = await add_chat(sm, status="joined", tg_chat_id=-1002222222222)
    state = JoinedState()
    await state.reconcile(sm)
    pipeline = Pipeline(state, sm, StubClassifier(), lambda: TERMS)
    await handle_message(msg("ищу работу", 5, chat_id=-1001111111111), pipeline)
    await handle_message(msg("ищу работу", 6, chat_id=-1002222222222), pipeline)
    async with sm() as s:
        links = {r.chat_id: r.message_link for r in await s.scalars(select(JobSignal))}
    assert links == {pub: "https://t.me/pubchat/5", priv: "https://t.me/c/2222222222/6"}


async def test_handler_never_raises(sm, joined, caplog):
    chat_id, pipeline = joined

    class Boom:
        async def classify(self, text):
            raise RuntimeError("boom")

    pipeline.classifier = Boom()
    with caplog.at_level(logging.ERROR):
        await handle_message(msg("ищу работу"), pipeline)
    assert "message handling failed" in caplog.text
    pipeline.sm = None  # even a broken pipeline must not raise
    await handle_message(msg("x", 99), pipeline)


# --- catch-up ---


class FakeMessages:
    def __init__(self, items):
        self.items = items
        self.calls = []

    async def get_messages(self, entity, **kw):
        self.calls.append((entity, kw))
        return self.items


async def test_catchup_reads_from_last_id_oldest_first(sm, joined):
    chat_id, pipeline = joined
    async with sm() as s:
        await JobsRadarRepository(s).set_last_message_id(chat_id, 20)
        await s.commit()
    items = [SimpleNamespace(id=i, message="ищу работу", date=NOW) for i in (23, 21, 22)]
    client = FakeMessages(items)
    seen = []
    orig = catchup.handle_message

    async def spy(m, p):
        seen.append(m.message_id)
        await orig(m, p)

    catchup.handle_message = spy
    try:
        await catchup.catch_up_all(client, pipeline, sleep=lambda s: _noop())
    finally:
        catchup.handle_message = orig
    assert client.calls == [(-1001234567890, {"min_id": 20, "limit": catchup.CATCHUP_LIMIT})]
    assert seen == [21, 22, 23]
    async with sm() as s:
        assert (await JobsRadarRepository(s).get(chat_id)).last_message_id == 23


async def _noop():
    return None


async def test_catchup_skips_chat_without_last_id_and_marks_lost(sm, joined):
    chat_id, pipeline = joined
    client = FakeMessages([])
    await catchup.catch_up_all(client, pipeline, sleep=lambda s: _noop())
    assert client.calls == []

    async with sm() as s:
        await JobsRadarRepository(s).set_last_message_id(chat_id, 5)
        await s.commit()

    class Lost:
        async def get_messages(self, *a, **kw):
            raise errors.ChannelPrivateError(request=None)

    alerts = []

    async def alert(text):
        alerts.append(text)

    await catchup.catch_up_all(Lost(), pipeline, alert=alert, sleep=lambda s: _noop())
    assert (await get_chat(sm, chat_id)).status == "rejected"
    assert -1001234567890 not in pipeline.state
    assert alerts


# --- joiner ---


class JoinFake:
    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.links = result, exc, []

    async def join(self, link):
        self.links.append(link)
        if self.exc:
            raise self.exc
        return self.result

    async def check(self, link):
        return self.result


def make_joiner(sm, fake, clock, cap=3, alerts=None, **kw):
    async def alert(text):
        if alerts is not None:
            alerts.append(text)

    return Joiner(
        sm=sm, state=JoinedState(), join_fn=fake.join, check_fn=fake.check, daily_cap=cap, alert=alert,
        clock=clock, rand=lambda a, b: a, sleep=lambda s: _noop(), **kw,
    )


async def test_joiner_joins_only_approved(sm):
    cand = await add_chat(sm, status="candidate", username="cand_chat")
    rej = await add_chat(sm, status="rejected", username="rej_chat")
    ok = await add_chat(sm, status="approved", username="ok_chat")
    fake = JoinFake(result=-1005555555555)
    joiner = make_joiner(sm, fake, Clock())
    await joiner.step()
    assert [l.value for l in fake.links] == ["ok_chat"]
    chat = await get_chat(sm, ok)
    assert (chat.status, chat.tg_chat_id) == ("joined", -1005555555555)
    assert (await get_chat(sm, cand)).status == "candidate"
    assert (await get_chat(sm, rej)).status == "rejected"
    assert joiner.state.get(-1005555555555) == ChatRef(ok, "ok_chat")
    assert [a.result for a in await actions(sm, "join")] == ["joined"]


async def test_joiner_pause_and_daily_cap(sm):
    for name in ("chat_aaa", "chat_bbb", "chat_ccc"):
        await add_chat(sm, username=name)
    clock = Clock()
    fake = JoinFake(result=-1001000000001)
    joiner = make_joiner(sm, fake, clock, cap=2)
    await joiner.step()
    assert joiner.next_at == NOW + timedelta(seconds=PAUSE_MIN_S)
    fake.result = -1001000000002
    await joiner.step()  # still inside the pause
    assert len(fake.links) == 1
    clock.now = NOW + timedelta(seconds=PAUSE_MAX_S)
    await joiner.step()
    assert len(fake.links) == 2
    clock.now = NOW + timedelta(hours=5)
    await joiner.step()  # cap of 2 per 24 h reached
    assert len(fake.links) == 2
    clock.now = NOW + timedelta(hours=25)
    fake.result = -1001000000003
    await joiner.step()
    assert len(fake.links) == 3


async def test_joiner_pause_survives_restart(sm):
    await add_chat(sm, username="chat_aaa", status="joined", tg_chat_id=-1001)
    await add_chat(sm, username="chat_bbb")
    async with sm() as s:
        await JobsRadarRepository(s).record_action("join", None, "joined", at=NOW - timedelta(minutes=10))
        await s.commit()
    fake = JoinFake(result=-1002)
    joiner = make_joiner(sm, fake, Clock())
    await joiner.step()
    assert fake.links == []


async def test_joiner_already_participant_counts_as_joined(sm):
    chat = await add_chat(sm, username="chat_aaa")
    fake = JoinFake(result=-1001000000009, exc=errors.UserAlreadyParticipantError(request=None))
    await make_joiner(sm, fake, Clock()).step()
    assert (await get_chat(sm, chat)).status == "joined"
    assert [a.result for a in await actions(sm, "join")] == ["already_participant"]


async def test_joiner_request_sent_waits_24h(sm):
    chat = await add_chat(sm, invite_hash="AbCdEfGhIjKl")
    clock = Clock()
    fake = JoinFake(exc=errors.InviteRequestSentError(request=None))
    alerts = []
    joiner = make_joiner(sm, fake, clock, alerts=alerts)
    await joiner.step()
    row = await get_chat(sm, chat)
    assert row.status == "approved" and row.join_error.startswith("request_sent")
    assert alerts
    clock.now = NOW + timedelta(hours=23)
    await joiner.step()
    assert len(fake.links) == 1
    clock.now = NOW + timedelta(hours=25)
    await joiner.step()
    assert len(fake.links) == 2


async def test_joiner_flood_wait_defers_until_seconds_passed(sm):
    await add_chat(sm, username="chat_aaa")
    await add_chat(sm, username="chat_bbb")
    clock = Clock()
    fake = JoinFake(exc=errors.FloodWaitError(request=None, capture=7200 * 3))
    alerts = []
    joiner = make_joiner(sm, fake, clock, alerts=alerts)
    await joiner.step()
    assert len(alerts) == 1
    for hours in (3, 5):  # past the normal pause but before the flood deadline
        clock.now = NOW + timedelta(hours=hours)
        await joiner.step()
    assert len(fake.links) == 1
    # a fresh process sees the same block from the journal
    other = make_joiner(sm, fake, clock)
    await other.step()
    assert len(fake.links) == 1
    clock.now = NOW + timedelta(hours=6, minutes=1)
    fake.exc = None
    fake.result = -1001000000004
    await other.step()
    assert len(fake.links) == 2


@pytest.mark.parametrize(
    "exc",
    [errors.ChannelsTooMuchError(request=None), errors.RPCError(request=None, message="FROZEN_METHOD_INVALID", code=420)],
)
async def test_joiner_stops_and_alerts_on_channels_too_much_or_frozen(sm, exc):
    chat = await add_chat(sm, username="chat_aaa")
    await add_chat(sm, username="chat_bbb")
    clock = Clock()
    fake = JoinFake(exc=exc)
    alerts = []
    joiner = make_joiner(sm, fake, clock, alerts=alerts)
    await joiner.step()
    assert joiner.stopped and len(alerts) == 1
    assert (await get_chat(sm, chat)).status == "approved"
    clock.now = NOW + timedelta(days=2)
    await joiner.step()
    assert len(fake.links) == 1


async def test_joiner_other_error_retries_next_day(sm):
    chat = await add_chat(sm, username="chat_aaa")
    clock = Clock()
    fake = JoinFake(exc=errors.InviteHashExpiredError(request=None))
    joiner = make_joiner(sm, fake, clock)
    await joiner.step()
    row = await get_chat(sm, chat)
    assert row.status == "approved" and row.join_error.startswith("error:InviteHashExpiredError")
    clock.now = NOW + timedelta(hours=3)
    await joiner.step()
    assert len(fake.links) == 1
    clock.now = NOW + timedelta(hours=25)
    await joiner.step()
    assert len(fake.links) == 2
    assert len(await actions(sm, "join")) == 2


# --- metadata ---


def channel(**kw):
    kw.setdefault("title", "Work in DE")
    return Channel(id=1, photo=ChatPhotoEmpty(), date=NOW, **kw)


class MetaClient:
    def __init__(self, entities=None, about="", members=1234, invites=None):
        self.entities, self.about, self.members, self.invites = entities or {}, about, members, invites or {}
        self.requests = []
        self.looked_up = []

    async def get_entity(self, ident):
        self.looked_up.append(ident)
        value = self.entities[ident]
        if isinstance(value, Exception):
            raise value
        return value

    async def __call__(self, request):
        self.requests.append(type(request).__name__)
        if isinstance(request, GetFullChannelRequest):
            return SimpleNamespace(full_chat=SimpleNamespace(participants_count=self.members, about=self.about))
        if isinstance(request, CheckChatInviteRequest):
            return self.invites[request.hash]
        raise AssertionError(f"unexpected request {request}")


def make_meta(sm, client, cap=50, clock=None, alerts=None):
    async def alert(text):
        if alerts is not None:
            alerts.append(text)

    return MetadataCollector(
        sm=sm, client=client, daily_cap=cap, alert=alert, clock=clock or Clock(),
        sleep=lambda s: _noop(), rand=lambda a, b: a,
    )


async def test_metadata_user_and_bot_rows_are_deleted(sm):
    human = await add_chat(sm, username="some_person")
    bot = await add_chat(sm, username="helper_bot")
    keep = await add_chat(sm, username="real_chat")
    client = MetaClient({
        "some_person": User(id=5), "helper_bot": User(id=6, bot=True), "real_chat": channel(megagroup=True),
    })
    await make_meta(sm, client).step()
    assert await get_chat(sm, human) is None
    assert await get_chat(sm, bot) is None
    assert (await get_chat(sm, keep)).entity_type == "group"


async def test_metadata_channel_fields_and_privacy(sm):
    chat = await add_chat(sm, username="jobs_chan")
    about = "Вакансии в Германии. Реклама по договорённости, писать @admin_vlad или t.me/other_admin"
    client = MetaClient({"jobs_chan": channel(broadcast=True)}, about=about, members=4321)
    await make_meta(sm, client).step()
    row = await get_chat(sm, chat)
    assert (row.entity_type, row.members, row.title) == ("channel", 4321, "Work in DE")
    assert (row.ads_allowed, row.admin_contact) == ("yes", "@admin_vlad")
    assert row.last_checked_at is not None
    assert "Вакансии" not in " ".join(str(v) for v in vars(row).values())
    assert client.requests == ["GetFullChannelRequest"]


async def test_metadata_basic_group_and_invite_link(sm):
    group = await add_chat(sm, username="old_group")
    invite = await add_chat(sm, invite_hash="HashHash1234")
    client = MetaClient(
        {"old_group": Chat(id=2, title="Old", photo=ChatPhotoEmpty(), participants_count=77, date=NOW, version=1)},
        invites={"HashHash1234": ChatInvite(
            title="Private jobs", photo=ChatPhotoEmpty(), participants_count=900, participants=[],
            color=0, about="keine Werbung! Kontakt @priv_admin", broadcast=False, megagroup=True)},
    )
    await make_meta(sm, client).step()
    g = await get_chat(sm, group)
    assert (g.entity_type, g.members) == ("group", 77)
    i = await get_chat(sm, invite)
    assert (i.entity_type, i.members, i.ads_allowed, i.admin_contact) == ("group", 900, "no", "@priv_admin")
    assert "GetFullChannelRequest" not in client.requests


async def test_metadata_keeps_admin_set_ads_value_when_text_is_silent(sm):
    chat = await add_chat(sm, username="jobs_chan", ads_allowed="yes")
    await make_meta(sm, MetaClient({"jobs_chan": channel(broadcast=True)}, about="hello")).step()
    assert (await get_chat(sm, chat)).ads_allowed == "yes"


async def test_metadata_daily_cap(sm):
    for i in range(5):
        await add_chat(sm, username=f"chat_{i}_aa")
    client = MetaClient({f"chat_{i}_aa": channel(broadcast=True) for i in range(5)})
    meta = make_meta(sm, client, cap=3)
    assert await meta.step() == 3
    assert await meta.step() == 0
    assert len(client.looked_up) == 3
    assert len(await actions(sm, "metadata")) == 3


@pytest.mark.parametrize(
    "exc,status",
    [
        (errors.ChannelPrivateError(request=None), "approved"),
        (errors.ChannelInvalidError(request=None), "approved"),
        (errors.ChannelPublicGroupNaError(request=None), "approved"),
        (errors.UsernameNotOccupiedError(request=None), "rejected"),
        (errors.UsernameInvalidError(request=None), "rejected"),
    ],
)
async def test_metadata_errors_keep_row(sm, exc, status):
    chat = await add_chat(sm, username="gone_chat")
    await make_meta(sm, MetaClient({"gone_chat": exc})).step()
    row = await get_chat(sm, chat)
    assert row is not None and row.status == status and row.last_checked_at is not None
    assert (await actions(sm, "metadata"))[0].result == type(exc).__name__


async def test_metadata_flood_wait_blocks(sm):
    await add_chat(sm, username="chat_aaa")
    await add_chat(sm, username="chat_bbb")
    clock = Clock()
    client = MetaClient({"chat_aaa": errors.FloodWaitError(request=None, capture=600), "chat_bbb": channel(broadcast=True)})
    alerts = []
    meta = make_meta(sm, client, clock=clock, alerts=alerts)
    await meta.step()
    assert client.looked_up == ["chat_aaa"] and len(alerts) == 1
    await meta.step()
    assert client.looked_up == ["chat_aaa"]
    clock.now = NOW + timedelta(minutes=11)
    client.entities["chat_aaa"] = channel(broadcast=True)
    await meta.step()
    assert client.looked_up[1:] == ["chat_aaa", "chat_bbb"]


async def test_metadata_due_selection(sm):
    now = NOW
    fresh = await add_chat(sm, username="fresh_chat", entity_type="group", last_checked_at=now - timedelta(days=1))
    stale = await add_chat(sm, username="stale_chat", entity_type="group", last_checked_at=now - timedelta(days=8))
    new = await add_chat(sm, username="new_chat")
    await add_chat(sm, username="rej_chat", status="rejected")
    async with sm() as s:
        due = [c.id for c in await JobsRadarRepository(s).chats_for_metadata(now, 10)]
    assert due == [new, stale] and fresh not in due


def test_metadata_text_rules():
    assert parse_ads_allowed("Реклама заборонена") == "no"
    assert parse_ads_allowed("реклама запрещена!") == "no"
    assert parse_ads_allowed("Keine Werbung bitte") == "no"
    assert parse_ads_allowed("Реклама за домовленістю з адміном") == "yes"
    assert parse_ads_allowed("Платная реклама") == "yes"
    assert parse_ads_allowed("просто чат") == "unknown"
    assert parse_admin_contact("пиши @helper_one потом @two_two") == "@helper_one"
    assert parse_admin_contact("https://t.me/admin_x") == "@admin_x"
    assert parse_admin_contact("https://t.me/+AbCdEfGhIjKl") is None
    assert parse_admin_contact("нет контактов") is None


# --- repository: stats and purge ---


async def test_recompute_stats_and_score(sm):
    busy = await add_chat(sm, status="joined", username="busy_chat", members=10000, language="uk", city="Berlin")
    quiet = await add_chat(sm, status="joined", username="quiet_chat")
    async with sm() as s:
        repo = JobsRadarRepository(s)
        for offset, posts in ((0, 70), (3, 70), (8, 500)):  # 8 days ago is outside the 7-day window
            s.add(JobChatDaily(chat_id=busy, day=(NOW - timedelta(days=offset)).date(), posts=posts))
        for _ in range(14):
            s.add(JobSignal(chat_id=busy, message_link="https://t.me/x/1", kind="seeker_question", confidence=0.9,
                            created_at=NOW - timedelta(days=1)))
        s.add(JobSignal(chat_id=busy, message_link="https://t.me/x/2", kind="seeker_question", confidence=0.9,
                        created_at=NOW - timedelta(days=10)))
        await repo.recompute_stats(NOW)
        await s.commit()
    b, q = await get_chat(sm, busy), await get_chat(sm, quiet)
    assert b.posts_per_day_7d == 20.0
    from app.jobs_radar.scoring import score_chat

    assert b.score == score_chat(20.0, 10000, 14 / 140, "uk", True, "unknown")
    assert (q.posts_per_day_7d, q.score) == (0, 0)


async def test_purge_daily_and_helpers(sm):
    chat = await add_chat(sm)
    today = datetime.now(UTC).date()
    async with sm() as s:
        repo = JobsRadarRepository(s)
        s.add(JobChatDaily(chat_id=chat, day=today - timedelta(days=31), posts=5))
        s.add(JobChatDaily(chat_id=chat, day=today - timedelta(days=29), posts=5))
        await s.flush()
        assert await repo.purge_daily(30) == 1
        await repo.set_last_message_id(chat, 9)
        await repo.set_last_message_id(chat, 4)  # never goes back
        assert (await repo.get(chat)).last_message_id == 9
        await repo.delete_chat(chat)
        await s.commit()
    async with sm() as s:
        assert await s.scalar(select(func.count(JobChatDaily.chat_id))) == 0
        assert await s.get(JobChat, chat) is None


# --- monitor entry ---


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, bot_token="1:x", database_url="sqlite+aiosqlite://", **kw)


def test_monitor_exits_0_when_flag_is_off(caplog):
    with caplog.at_level(logging.INFO):
        assert monitor.main(_settings(jobs_radar_enabled=False, tg_api_id=1, tg_api_hash="h", tg_session="s")) == 0


def test_monitor_exits_1_when_credentials_missing(caplog):
    with caplog.at_level(logging.ERROR):
        assert monitor.main(_settings(jobs_radar_enabled=True, tg_api_id=1)) == 1
    assert "TG_API_HASH" in caplog.text and "TG_SESSION" in caplog.text
    assert "TG_API_ID" not in caplog.text


async def test_build_monitor_event_and_daily_job(sm):
    class FakeBot:
        def __init__(self):
            self.sent = []

        async def send_message(self, chat_id, text, **kw):
            self.sent.append((chat_id, text))

    class NoNetworkClient:
        def __getattr__(self, name):
            raise AssertionError(f"client.{name} must not be used here")

    chat = await add_chat(sm, status="joined", tg_chat_id=-1001234567890, username="work_de")
    settings = _settings(jobs_radar_enabled=True, admin_ids=[7])
    bot = FakeBot()
    mon = monitor.build_monitor(settings, NoNetworkClient(), sm, bot)
    async with sm() as s:
        await JobsRadarRepository(s).seed_keywords_if_empty()
        await s.commit()
    await mon.refresh()
    assert -1001234567890 in mon.state and mon.terms[0]

    event = SimpleNamespace(
        chat_id=-1001234567890, out=False, chat=SimpleNamespace(username="work_de"),
        message=SimpleNamespace(id=3, message="hello", date=NOW),
    )
    await mon.on_new_message(event)
    await mon.on_new_message(SimpleNamespace(chat_id=-100777, out=False))  # unknown chat: nothing is touched
    assert (await get_chat(sm, chat)).last_message_id == 3

    await mon.daily_job()
    assert (await get_chat(sm, chat)).posts_per_day_7d == round(1 / 7, 3)


def test_blank_values_fall_back_to_defaults():
    s = Settings(
        _env_file=None, bot_token="1:x", tg_api_id="", tg_api_hash=" ", tg_session="", ai_api_key="", ai_model=" ",
        jobs_radar_enabled="", jobs_join_daily_cap="", jobs_metadata_daily_cap=" ",
        jobs_signal_retention_days="", jobs_digest_hour="",
    )
    assert (s.tg_api_id, s.tg_api_hash, s.tg_session, s.ai_api_key, s.ai_model) == (None,) * 5
    assert s.jobs_radar_enabled is False
    assert (s.jobs_join_daily_cap, s.jobs_metadata_daily_cap) == (3, 50)
    assert (s.jobs_signal_retention_days, s.jobs_digest_hour) == (14, 9)


def test_blank_env_values_do_not_crash(monkeypatch):
    for name in ("TG_API_ID", "TG_API_HASH", "TG_SESSION", "JOBS_RADAR_ENABLED", "JOBS_JOIN_DAILY_CAP",
                 "JOBS_METADATA_DAILY_CAP", "JOBS_SIGNAL_RETENTION_DAYS", "JOBS_DIGEST_HOUR", "AI_API_KEY"):
        monkeypatch.setenv(name, "")
    s = Settings(_env_file=None, bot_token="1:x")
    assert s.tg_api_id is None and s.jobs_radar_enabled is False and s.jobs_join_daily_cap == 3
    monkeypatch.setenv("TG_API_ID", "123")
    monkeypatch.setenv("JOBS_JOIN_DAILY_CAP", "5")
    s = Settings(_env_file=None, bot_token="1:x")
    assert (s.tg_api_id, s.jobs_join_daily_cap) == (123, 5)


async def test_delete_chat_removes_signals_and_unlinks_actions(sm):
    chat = await add_chat(sm, username="gone_chat")
    other = await add_chat(sm, username="other_chat")
    async with sm() as s:
        repo = JobsRadarRepository(s)
        for cid in (chat, other):
            s.add(JobSignal(chat_id=cid, message_link="https://t.me/x/1", kind="seeker_question", confidence=0.9))
        await repo.record_action("metadata", chat, "ok")
        await repo.delete_chat(chat)
        await s.commit()
    async with sm() as s:
        assert [x.chat_id for x in await s.scalars(select(JobSignal))] == [other]
        acts = list((await s.scalars(select(JobRadarAction))).all())
        assert [(a.chat_id, a.result) for a in acts] == [(None, "ok")]


async def test_catchup_warns_at_limit_and_join_sets_baseline(sm, joined, caplog):
    chat_id, pipeline = joined
    async with sm() as s:
        await JobsRadarRepository(s).set_last_message_id(chat_id, 1)
        await s.commit()
    items = [SimpleNamespace(id=i, message="", date=NOW) for i in range(2, 2 + catchup.CATCHUP_LIMIT)]
    with caplog.at_level(logging.WARNING):
        await catchup.catch_up_chat(FakeMessages(items), pipeline, -1001234567890)
    assert "gap may be larger" in caplog.text

    fresh = await add_chat(sm, status="joined", tg_chat_id=-1003333333333, username="fresh_one")
    await pipeline.state.reconcile(sm)
    client = FakeMessages([SimpleNamespace(id=500, message="ищу работу", date=NOW)])
    await catchup.set_baseline(client, pipeline, -1003333333333)
    assert client.calls == [(-1003333333333, {"limit": 1})]
    row = await get_chat(sm, fresh)
    assert row.last_message_id == 500
    async with sm() as s:
        assert await s.scalar(select(func.count(JobSignal.id))) == 0  # nothing was processed


async def test_join_hook_sees_committed_row_on_separate_connections(tmp_path):
    """The on_joined hook reconciles in a new session: the joined row must already be committed."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.database.models import Base

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'radar.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        chat_id = await add_chat(sm, username="ok_chat")
        client = FakeMessages([SimpleNamespace(id=77, message="x", date=NOW)])
        mon = monitor.Monitor(_settings(jobs_radar_enabled=True), client, sm, bot=None)
        mon.joiner.join_fn = JoinFake(result=-1005555555555).join
        mon.joiner.clock, mon.joiner.rand = Clock(), lambda a, b: a

        await mon.joiner.step()

        assert mon.state.get(-1005555555555) == ChatRef(chat_id, "ok_chat")
        assert (await get_chat(sm, chat_id)).last_message_id == 77
    finally:
        await engine.dispose()


def test_seconds_until_hour():
    assert monitor.seconds_until_hour(datetime(2026, 11, 16, 8, 0, tzinfo=UTC), 9) == 3600
    assert monitor.seconds_until_hour(datetime(2026, 11, 16, 9, 0, tzinfo=UTC), 9) == 86400
