from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.data.regions import GERMAN_LEVELS, GOALS, LANDS, STATUSES
from app.i18n import t

MENU_KEYS = [
    "menu_jobs",  # main section: full-width first row
    "menu_documents", "menu_housing",
    "menu_translator",
    "menu_ai", "menu_info",
    "menu_settings", "menu_profile",
]


def _rows(buttons: list, per_row: int) -> list[list]:
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


def ib(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def main_menu(lang: str) -> ReplyKeyboardMarkup:
    buttons = [KeyboardButton(text=t(lang, k)) for k in MENU_KEYS]
    rows = [[buttons[0]]] + _rows(buttons[1:], 2)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def webapp_kb(lang: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(lang, "open_app"), web_app=WebAppInfo(url=url))]]
    )


def language_kb(languages: list[str], prefix: str = "lang") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[ib(t(code, "language_name"), f"{prefix}:{code}")] for code in languages])


def lands_kb(lang: str) -> InlineKeyboardMarkup:
    buttons = [ib(name, f"land:{code}") for code, name in LANDS.items()]
    rows = _rows(buttons, 2) + [[ib(t(lang, "skip"), "land:skip")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def city_skip_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[ib(t(lang, "skip"), "city:skip")]])


def levels_kb(lang: str) -> InlineKeyboardMarkup:
    buttons = [ib(t(lang, "level_C1") if lvl == "C1" else lvl, f"lvl:{lvl}") for lvl in GERMAN_LEVELS]
    return InlineKeyboardMarkup(inline_keyboard=_rows(buttons, 3))


def goals_kb(lang: str) -> InlineKeyboardMarkup:
    buttons = [ib(t(lang, f"goal_{g}"), f"goal:{g}") for g in GOALS]
    return InlineKeyboardMarkup(inline_keyboard=_rows(buttons, 2))


def status_kb(lang: str) -> InlineKeyboardMarkup:
    rows = [[ib(t(lang, f"status_{s}"), f"st:{s}")] for s in STATUSES]
    rows.append([ib(t(lang, "status_skip"), "st:skip")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_kb(lang: str, broadcast_on: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib(t(lang, "btn_change_language"), "set:lang")],
        [ib(t(lang, "btn_edit_profile"), "set:edit")],
        [ib(t(lang, "btn_broadcast_off" if broadcast_on else "btn_broadcast_on"), "set:broadcast")],
        [ib(t(lang, "btn_privacy"), "set:privacy")],
        [ib(t(lang, "btn_export"), "set:export"), ib(t(lang, "btn_delete"), "set:delete")],
    ])


def profile_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib(t(lang, "btn_edit_profile"), "set:edit")],
        [ib(t(lang, "btn_export"), "set:export"), ib(t(lang, "btn_delete"), "set:delete")],
    ])


def delete_confirm_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib(t(lang, "btn_confirm_delete"), "del:yes")],
        [ib(t(lang, "cancel"), "del:no")],
    ])


def info_topics_kb(lang: str, topics: dict[str, tuple[str, str]]) -> InlineKeyboardMarkup:
    idx = 1 if lang == "ru" else 0
    return InlineKeyboardMarkup(inline_keyboard=[[ib(titles[idx], f"info:{key}")] for key, titles in topics.items()])


def links_kb(sources, back: str | None = None, lang: str = "uk") -> InlineKeyboardMarkup:
    seen, rows = set(), []
    for s in sources:
        if s.url in seen:
            continue
        seen.add(s.url)
        rows.append([InlineKeyboardButton(text=f"🔗 {s.title_ru if lang == 'ru' else s.title_uk}", url=s.url)])
    if back:
        rows.append([ib(t(lang, "back"), back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
