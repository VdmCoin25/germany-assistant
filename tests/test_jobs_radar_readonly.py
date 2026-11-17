"""The monitor account is read-only: scan its modules for anything that could write, send or mark as read."""
import re
from pathlib import Path

ROOT = Path(__file__).parents[1] / "app" / "jobs_radar"
TELETHON_MODULES = ("telegram.py", "state.py", "handler.py", "catchup.py", "joiner.py", "metadata.py", "monitor.py")

FORBIDDEN = (
    ".send_message",
    ".send_file",
    ".send_read_acknowledge",
    ".reply(",
    ".respond(",
    "mark_read",
    "forward_messages",
    "edit_message",
    "delete_messages",
    ".edit(",
    ".delete(",
    ".forward_to(",
    "client.action",
    "SendMessageRequest",
    "ReadHistoryRequest",
    "SetTypingRequest",
    "GetFullUserRequest",
    "GetCommonChatsRequest",
    "GetParticipantsRequest",
    "get_participants",
    "iter_participants",
)


ALLOWED_CLIENT_METHODS = {
    "get_entity", "get_messages", "get_permissions", "get_dialogs", "connect", "is_user_authorized",
    "disconnect", "start", "run_until_disconnected", "add_event_handler", "on",
}
ALLOWED_REQUESTS = {"JoinChannelRequest", "ImportChatInviteRequest", "CheckChatInviteRequest", "GetFullChannelRequest"}


def _text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def telethon_modules() -> list[str]:
    return sorted(
        p.name for p in ROOT.glob("*.py")
        if re.search(r"^\s*(?:from|import)\s+telethon", p.read_text(encoding="utf-8"), re.M)
    )


def violations(text: str) -> list[str]:
    found = [f"forbidden token {t}" for t in FORBIDDEN if t in text]
    found += [f"client.{m}(" for m in set(re.findall(r"client\.(\w+)\(", text)) - ALLOWED_CLIENT_METHODS]
    found += [f"{r}" for r in set(re.findall(r"\b(\w+Request)\b", text)) - ALLOWED_REQUESTS]
    return found


def test_scanner_flags_forbidden_snippets():
    assert violations("await client.send_message(chat, 'hi')")
    assert violations("await self.client.get_participants(chat)")
    assert violations("await client(GetParticipantsRequest(chan))")
    assert violations("await client(SomeNewRequest(x))")
    assert not violations("await client.get_messages(chat, limit=1)")


def test_telethon_modules_are_discovered():
    assert {"telegram.py", "joiner.py", "metadata.py", "catchup.py", "monitor.py"} <= set(telethon_modules())


def test_monitor_modules_use_only_allowed_calls():
    for name in sorted(set(telethon_modules()) | set(TELETHON_MODULES)):
        assert not violations(_text(name)), f"{name}: {violations(_text(name))}"


def test_notify_and_digest_do_not_import_telethon():
    for name in ("notify.py", "digest.py"):
        assert not re.search(r"^\s*(?:from|import)\s+telethon", _text(name), re.M), name


def test_catchup_uses_only_get_messages():
    calls = set(re.findall(r"client\.(\w+)\(", _text("catchup.py")))
    assert calls <= {"get_messages"}
