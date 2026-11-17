"""Parsing Telegram chat links and building message links (no Telethon dependency)."""

import re
from dataclasses import dataclass
from typing import Literal

_USERNAME = r"[A-Za-z][A-Za-z0-9_]{3,31}"
_INVITE_RE = re.compile(
    r"^(?:https?://)?(?:t\.me|telegram\.me)/(?:\+|joinchat/)([A-Za-z0-9_-]{8,})/?$"
)
_PUBLIC_RE = re.compile(rf"^(?:https?://)?(?:t\.me|telegram\.me)/({_USERNAME})/?$")
_AT_RE = re.compile(rf"^@({_USERNAME})$")
_RESERVED = {"joinchat", "addstickers", "share", "proxy", "socks", "c", "s", "iv", "boost"}


@dataclass(frozen=True)
class ChatLink:
    kind: Literal["username", "invite"]
    value: str  # username without @, or invite hash

    @property
    def identifier(self) -> str:
        """Canonical form of the link, used for display and comparison."""
        if self.kind == "username":
            return f"@{self.value.lower()}"  # usernames are case-insensitive
        return f"https://t.me/+{self.value}"  # invite hashes are case-sensitive


def parse_chat_link(raw: str) -> ChatLink | None:
    """Accepts @name, t.me/name, https://t.me/+hash, t.me/joinchat/hash. None if not a chat link."""
    text = raw.strip()
    if m := _INVITE_RE.match(text):
        return ChatLink("invite", m.group(1))
    if (m := _PUBLIC_RE.match(text) or _AT_RE.match(text)) and m.group(1).lower() not in _RESERVED:
        return ChatLink("username", m.group(1))
    return None


def message_link(chat_id: int, message_id: int, username: str | None = None) -> str | None:
    """Public chats: t.me/<username>/<id>. Supergroups/channels: t.me/c/<id without -100>/<id>.
    Basic groups have no message links → None."""
    if username:
        return f"https://t.me/{username}/{message_id}"
    marked = str(chat_id)
    if marked.startswith("-100"):
        return f"https://t.me/c/{marked[4:]}/{message_id}"
    return None
