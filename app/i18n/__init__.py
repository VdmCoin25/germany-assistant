"""Tiny JSON-based i18n. Add a language by creating locales/<code>.json."""
import json
from functools import lru_cache
from pathlib import Path

LOCALES_DIR = Path(__file__).parent / "locales"
FALLBACK = "uk"


@lru_cache
def _locales() -> dict[str, dict[str, str]]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in LOCALES_DIR.glob("*.json")}


def available_languages() -> list[str]:
    return sorted(_locales())


def t(lang: str | None, key: str, **kwargs) -> str:
    locs = _locales()
    text = locs.get(lang or FALLBACK, {}).get(key) or locs[FALLBACK].get(key) or key
    return text.format(**kwargs) if kwargs else text


def all_variants(key: str) -> set[str]:
    """Every translation of a key — used to match reply-keyboard buttons in any language."""
    return {loc[key] for loc in _locales().values() if key in loc}
