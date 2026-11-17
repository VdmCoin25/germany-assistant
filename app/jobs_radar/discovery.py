"""Find new chat candidates in message text: t.me links and @mentions."""
import re
from dataclasses import dataclass
from typing import Literal

from app.jobs_radar.tglinks import ChatLink, parse_chat_link

_LINK_RE = re.compile(r"(?:https?://)?(?:t\.me|telegram\.me)/[A-Za-z0-9_+/-]+", re.IGNORECASE)
_MENTION_RE = re.compile(r"(?<![\w@/.])@[A-Za-z][A-Za-z0-9_]{3,31}")


@dataclass(frozen=True)
class FoundLink:
    link: ChatLink
    source: Literal["link", "mention"]


def _key(link: ChatLink) -> tuple[str, str]:
    return (link.kind, link.value.lower() if link.kind == "username" else link.value)


def extract_links(text: str) -> list[FoundLink]:
    found: dict[tuple[str, str], FoundLink] = {}

    def add(raw: str, source: Literal["link", "mention"]) -> None:
        link = parse_chat_link(raw.rstrip("/.,;:!?)"))
        if link is None:
            return
        if link.kind == "username" and link.value.lower().endswith("bot"):
            return
        found.setdefault(_key(link), FoundLink(link, source))

    for m in _LINK_RE.finditer(text):
        add(m.group(0), "link")
    for m in _MENTION_RE.finditer(text):
        add(m.group(0), "mention")
    return list(found.values())
