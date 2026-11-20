"""scripts/telegram_login.py with a fake TelegramClient: no network, no real session."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from telethon import errors
from telethon.tl import types

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "telegram_login.py"
SESSION = "FAKE-SESSION-STRING"


def _load():
    spec = importlib.util.spec_from_file_location("telegram_login_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeQr:
    def __init__(self, outcomes):
        self.url = "tg://login?token=abc"
        self.outcomes = list(outcomes)  # "ok" | "timeout" | "2fa"
        self.recreated = 0

    async def wait(self, timeout=None):
        outcome = self.outcomes.pop(0)
        if outcome == "timeout":
            raise TimeoutError
        if outcome == "2fa":
            raise errors.SessionPasswordNeededError(request=None)

    async def recreate(self):
        self.recreated += 1


class FakeClient:
    instance = None
    qr_outcomes = ["ok"]
    sign_in_errors: list = []

    def __init__(self, session, api_id, api_hash):
        self.session = SimpleNamespace(save=lambda: SESSION)
        self.qr = FakeQr(type(self).qr_outcomes)
        self.sign_in_calls = []
        self.code_requests = []
        self.connected = False
        self.disconnected = False
        self.errors = list(type(self).sign_in_errors)
        type(self).instance = self

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.disconnected = True

    async def get_me(self):
        return SimpleNamespace(first_name="Monitor", username=None, id=42)

    async def qr_login(self):
        return self.qr

    async def send_code_request(self, phone, force_sms=False):
        self.code_requests.append((phone, force_sms))
        return SimpleNamespace(
            type=types.auth.SentCodeTypeApp(length=5),
            next_type=types.auth.SentCodeTypeSms(length=5),
            phone_code_hash="hash",
        )

    async def sign_in(self, **kwargs):
        self.sign_in_calls.append(kwargs)
        if self.errors:
            raise self.errors.pop(0)


@pytest.fixture
def script(monkeypatch, tmp_path):
    module = _load()
    FakeClient.qr_outcomes = ["ok"]
    FakeClient.sign_in_errors = []
    monkeypatch.setattr(module, "TelegramClient", FakeClient)
    monkeypatch.setattr(module, "_api_credentials", lambda: (1, "hash"))
    monkeypatch.chdir(tmp_path)  # any file the script wrote would land here
    return module


def feed(monkeypatch, module, answers):
    queue = list(answers)
    prompts = []

    async def fake_ask(prompt, secret=False):
        prompts.append(prompt)
        return queue.pop(0)

    monkeypatch.setattr(module, "ask", fake_ask)
    return prompts


def assert_session_printed_not_saved(capsys, tmp_path):
    out = capsys.readouterr().out
    assert f"TG_SESSION={SESSION}" in out
    assert "Logged in as Monitor (@-, id 42)" in out
    assert list(tmp_path.iterdir()) == []
    return out


async def test_qr_login_succeeds(script, monkeypatch, capsys, tmp_path):
    feed(monkeypatch, script, [""])  # default choice = QR
    await script.main()
    client = FakeClient.instance
    assert client.qr.recreated == 0
    assert client.connected and client.disconnected
    out = assert_session_printed_not_saved(capsys, tmp_path)
    assert "Link Desktop Device" in out


async def test_qr_timeout_then_recreate_then_success(script, monkeypatch, capsys, tmp_path):
    FakeClient.qr_outcomes = ["timeout", "ok"]
    feed(monkeypatch, script, ["1"])
    await script.main()
    assert FakeClient.instance.qr.recreated == 1
    assert_session_printed_not_saved(capsys, tmp_path)


async def test_qr_needs_2fa_password(script, monkeypatch, capsys, tmp_path):
    FakeClient.qr_outcomes = ["2fa"]
    prompts = feed(monkeypatch, script, ["", "s3cret"])
    await script.main()
    assert FakeClient.instance.sign_in_calls == [{"password": "s3cret"}]
    assert any("2FA" in p for p in prompts)
    out = assert_session_printed_not_saved(capsys, tmp_path)
    assert "s3cret" not in out


async def test_code_login_describes_delivery_and_resends(script, monkeypatch, capsys, tmp_path):
    feed(monkeypatch, script, ["2", "+380 50 000 0000", "", "12345"])  # empty input = resend
    await script.main()
    client = FakeClient.instance
    assert client.code_requests == [("+380500000000", False), ("+380500000000", True)]
    assert client.sign_in_calls == [{"phone": "+380500000000", "code": "12345", "phone_code_hash": "hash"}]
    out = assert_session_printed_not_saved(capsys, tmp_path)
    assert "in the Telegram app" in out
    assert "by SMS" in out
    assert "Code re-sent" in out


async def test_code_invalid_exits(script, monkeypatch):
    FakeClient.sign_in_errors = [errors.PhoneCodeInvalidError(request=None)]
    feed(monkeypatch, script, ["2", "+380500000000", "00000"])
    with pytest.raises(SystemExit, match="rejected"):
        await script.main()
    assert FakeClient.instance.disconnected


async def test_code_flood_wait_exits(script, monkeypatch):
    async def boom(self, phone, force_sms=False):
        raise errors.FloodWaitError(request=None, capture=77)

    monkeypatch.setattr(FakeClient, "send_code_request", boom)
    feed(monkeypatch, script, ["2", "+380500000000"])
    with pytest.raises(SystemExit, match="77 s"):
        await script.main()


async def test_phone_flood_error_message(script, monkeypatch):
    async def boom(self, phone, force_sms=False):
        raise errors.PhoneNumberFloodError(request=None)

    monkeypatch.setattr(FakeClient, "send_code_request", boom)
    feed(monkeypatch, script, ["2", "+380500000000"])
    with pytest.raises(SystemExit, match="Too many login attempts"):
        await script.main()


def test_describe_unknown_type(script):
    assert script.describe(object()) == "via object"
