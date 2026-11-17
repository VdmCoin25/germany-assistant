"""Keyword prefilter that runs before any classifier call."""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

_DASHES = re.compile("[‐‑‒–—\\-]")
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    t = text.casefold().replace("ё", "е")
    t = _DASHES.sub(" ", t)
    return _SPACES.sub(" ", t).strip()


@dataclass
class PrefilterResult:
    passed: bool
    reason: str
    matched: list[str] = field(default_factory=list)


def check(text: str, include: Iterable[str], exclude: Iterable[str]) -> PrefilterResult:
    norm = normalize(text or "")
    if not norm:
        return PrefilterResult(False, "empty")
    for term in exclude:
        t = normalize(term)
        if t and t in norm:
            return PrefilterResult(False, f"exclude:{t}", [t])
    matched = []
    for term in include:
        t = normalize(term)
        if t and t in norm:
            matched.append(t)
    if matched:
        return PrefilterResult(True, "include", matched)
    return PrefilterResult(False, "no_include")
