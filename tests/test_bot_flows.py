from aiogram.methods import SendDocument
from sqlalchemy import func, select

from app.database.models import AnalyticsEvent, User
from app.database.repositories.users import UserRepository
from app.i18n import t
from tests.conftest import ADMIN_ID

UID = 1001


async def register(h, uid=UID, lang="ru"):
    await h.send(uid, "/start")
    await h.press(uid, f"lang:{lang}")
    await h.press(uid, "land:BE")
    await h.send(uid, "  Berlin  ")
    await h.press(uid, "lvl:A2")
    await h.press(uid, "goal:jobs")
    await h.press(uid, "st:skip")


async def get_user(sm, uid=UID):
    async with sm() as s:
        return await UserRepository(s).get(uid)


async def test_start_shows_language_choice(h):
    await h.send(UID, "/start")
    assert t(None, "choose_language") in h.session.texts()


async def test_full_registration_is_saved(h, sm):
    await register(h)
    u = await get_user(sm)
    assert u.is_registered
    assert (u.language, u.land, u.city, u.german_level, u.goal, u.residence_status) == \
        ("ru", "BE", "Berlin", "A2", "jobs", None)
    assert t("ru", "menu_hint") in h.session.texts()


async def test_language_is_respected_after_registration(h):
    await register(h, lang="ru")
    h.session.clear()
    await h.send(UID, "/start")
    assert t("ru", "welcome_back") in h.session.texts()
    await h.send(UID, t("ru", "menu_documents"))
    assert t("ru", "section_documents") in h.session.texts()


async def test_invalid_callback_values_are_ignored(h, sm):
    await h.send(UID, "/start")
    await h.press(UID, "lang:xx")
    u = await get_user(sm)
    assert u.language is None


async def test_city_validation(h, sm):
    await h.send(UID, "/start")
    await h.press(UID, "lang:uk")
    await h.press(UID, "land:BY")
    await h.send(UID, "x" * 200)
    assert t("uk", "city_invalid") in h.session.texts()
    assert (await get_user(sm)).city is None


async def test_help_and_privacy_commands(h):
    await register(h, lang="uk")
    h.session.clear()
    await h.send(UID, "/help")
    await h.send(UID, "/privacy")
    texts = " ".join(h.session.texts())
    assert "/delete_my_data" in texts and "Datenschutzerklärung" in texts


async def test_ai_section_is_honest_without_provider(h):
    await register(h, lang="uk")
    h.session.clear()
    await h.send(UID, t("uk", "menu_ai"))
    assert t("uk", "section_ai") in h.session.texts()


async def test_export_sends_json(h):
    await register(h)
    h.session.clear()
    await h.send(UID, "/export_my_data")
    assert any(isinstance(c, SendDocument) for c in h.session.calls)


async def test_delete_my_data_removes_user_and_events(h, sm):
    await register(h)
    async with sm() as s:
        assert await s.scalar(select(func.count(AnalyticsEvent.id))) > 0
    await h.send(UID, "/delete_my_data")
    await h.press(UID, "del:yes")
    async with sm() as s:
        assert await s.scalar(select(func.count(User.id))) == 0
        assert await s.scalar(select(func.count(AnalyticsEvent.id))) == 0


async def test_delete_cancel_keeps_data(h, sm):
    await register(h)
    await h.press(UID, "del:no")
    assert await get_user(sm) is not None


async def test_admin_commands_hidden_from_regular_users(h):
    await register(h)
    h.session.clear()
    await h.send(UID, "/stats")
    assert not any("Пользователи" in x for x in h.session.texts())


async def test_admin_can_see_stats_and_block(h, sm):
    await register(h)
    await h.send(ADMIN_ID, "/stats")
    assert any("Пользователи" in x for x in h.session.texts())
    await h.send(ADMIN_ID, f"/block {UID}")
    assert (await get_user(sm)).is_blocked
    h.session.clear()
    await h.send(UID, "/start")
    assert h.session.texts() == []  # blocked users are ignored


async def test_unknown_text_falls_back_to_menu(h):
    await register(h)
    h.session.clear()
    await h.send(UID, "qwerty")
    assert t("ru", "unknown") in h.session.texts()


async def test_unregistered_user_is_asked_to_start(h):
    await h.send(UID, "hello")
    assert t("uk", "need_start") in h.session.texts()


async def test_housing_section_terms_and_docs(h):
    await register(h, lang="uk")
    h.session.clear()
    await h.send(UID, t("uk", "menu_housing"))
    await h.press(UID, "hs:terms")
    await h.press(UID, "hs:docs")
    texts = h.session.texts()
    assert any("Kaution" in x and "§ 551 BGB" in x for x in texts)
    assert any("Western Union" in x for x in texts)
    assert all(len(x) <= 4096 for x in texts)
