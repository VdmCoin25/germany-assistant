import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx
import pytest
from fastapi import HTTPException

from app.config import Settings
from app.i18n import _locales, t
from app.services.ai.base import AINotConfigured, get_provider
from app.bot.middlewares.throttling import RateLimiter
from app.webapp.api import create_app, verify_init_data
from tests.conftest import TOKEN


def make_init_data(user_id: int, token: str = TOKEN, auth_date: int | None = None) -> str:
    fields = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "AAH",
        "user": json.dumps({"id": user_id, "first_name": "T"}),
    }
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


# --- i18n ---
def test_locales_have_same_keys():
    locs = _locales()
    assert set(locs["uk"]) == set(locs["ru"])


def test_i18n_fallback():
    assert t("de", "skip") == t("uk", "skip")
    assert t("uk", "no_such_key") == "no_such_key"


# --- config ---
def test_admin_ids_parse_from_string():
    s = Settings(_env_file=None, bot_token="1:x", admin_ids="1, 2,3")
    assert s.admin_ids == [1, 2, 3]


def test_webapp_url_must_be_https():
    with pytest.raises(ValueError):
        Settings(_env_file=None, bot_token="1:x", webapp_url="http://example.com")


# --- rate limit ---
def test_rate_limiter():
    rl = RateLimiter(limit=2, window=60)
    assert rl.allow(1, 0) and rl.allow(1, 1)
    assert not rl.allow(1, 2)
    assert rl.allow(1, 61.5)
    assert rl.allow(2, 2)


# --- AI adapter ---
async def test_ai_not_configured_is_explicit():
    with pytest.raises(AINotConfigured):
        await get_provider("none", None, None).complete([])


# --- Mini App auth ---
def test_init_data_valid():
    data = verify_init_data(make_init_data(5), TOKEN, ttl=3600)
    assert data.user.id == 5


def test_init_data_bad_signature():
    with pytest.raises(HTTPException):
        verify_init_data(make_init_data(5, token="1:OTHER"), TOKEN, ttl=3600)


def test_init_data_expired():
    old = int(time.time()) - 10_000
    with pytest.raises(HTTPException):
        verify_init_data(make_init_data(5, auth_date=old), TOKEN, ttl=3600)


async def test_webapp_profile_api(settings, sm):
    app = create_app(settings, sm)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/api/me", headers={"X-Telegram-Init-Data": "bad"})).status_code == 401
        hdr = {"X-Telegram-Init-Data": make_init_data(77)}
        r = await c.patch("/api/me", headers=hdr, json={"language": "ru", "land": "HH", "german_level": "B1",
                                                         "goal": "documents", "city": "  Hamburg "})
        assert r.status_code == 200
        me = (await c.get("/api/me", headers=hdr)).json()
        assert (me["language"], me["land"], me["city"], me["german_level"], me["is_registered"]) == \
            ("ru", "HH", "Hamburg", "B1", True)
        assert "telegram_id" not in me
        assert (await c.patch("/api/me", headers=hdr, json={"land": "XX"})).status_code == 422
        assert (await c.patch("/api/me", headers=hdr, json={"language": "fr"})).status_code == 422
        assert len((await c.get("/api/sources")).json()) > 0
        assert (await c.delete("/api/me", headers=hdr)).status_code == 200
        assert (await c.get("/api/me", headers=hdr)).json()["is_registered"] is False


def test_hosting_env_defaults(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://x.onrender.com/")
    monkeypatch.setenv("PORT", "10000")
    s = Settings(_env_file=None, bot_token="1:x", database_url="postgres://u:p@h:5432/db")
    assert s.webapp_url == "https://x.onrender.com"
    assert s.webapp_port == 10000
    assert s.database_url == "postgresql+asyncpg://u:p@h:5432/db"
