"""J5: the offline demo runs the whole radar cycle on fakes: no Telegram, no network, no real database."""
import re
import socket
import tempfile
from pathlib import Path

import pytest
import telethon

from app.data.jobs_radar_demo import CHATS, MESSAGES
from app.jobs_radar import demo
from app.jobs_radar.export import AGENCY_COLUMNS, SOURCE_COLUMNS


def _forbid_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the demo must not open network connections")

    monkeypatch.setattr(telethon, "TelegramClient", boom)
    monkeypatch.setattr(socket, "create_connection", boom)


def test_demo_data_is_synthetic_and_sized():
    assert 40 <= len(MESSAGES) <= 60
    assert {m.chat for m in MESSAGES} <= {c.username for c in CHATS}
    for chat in CHATS:
        assert not chat.username or chat.username.startswith("radar_demo_")
    text = " ".join(m.text for m in MESSAGES)
    phones = re.findall(r"\+\d+(?: \d+){2,}", text)
    assert phones
    assert all(re.fullmatch(r"\+49 \d+ 0000 00\d\d", p) for p in phones)  # only obviously fake numbers
    assert all(".example" in w for w in re.findall(r"[\w.-]+@[\w.-]+|www\.[\w.-]+", text))


def test_demo_runs_end_to_end_without_touching_anything_real(tmp_path, monkeypatch, capsys):
    _forbid_network(monkeypatch)
    configured = tmp_path / "real_database.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{configured.as_posix()}")
    monkeypatch.setenv("JOBS_RADAR_ENABLED", "false")  # the demo is local-only and ignores the real environment
    monkeypatch.setenv("BOT_TOKEN", "must-not-be-used")
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    out = tmp_path / "out"

    assert demo.main(["--out", str(out), "--days", "3"]) == 0
    text = capsys.readouterr().out

    # the configured database was never created, and the throw-away one is gone
    assert not configured.exists()
    assert list(scratch.iterdir()) == []
    assert sorted(p.name for p in out.iterdir()) == ["agencies.csv", "sources.csv"]

    # CSV files: UTF-8 with BOM, ';' delimiter, the documented header, real content
    for name, columns in (("sources.csv", SOURCE_COLUMNS), ("agencies.csv", AGENCY_COLUMNS)):
        raw = (out / name).read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")
        lines = raw.decode("utf-8-sig").splitlines()
        assert lines[0] == ";".join(columns)
        assert len(lines) >= 2
    assert "radar_demo_chat_01" in (out / "sources.csv").read_text(encoding="utf-8-sig")
    assert "GmbH" in (out / "agencies.csv").read_text(encoding="utf-8-sig")

    # every step of the cycle is reported
    for heading in (
        "1. Импорт и одобрение кандидатов", "2. Вступления по дням", "3. Метаданные чатов и оценка",
        "4. Входящие сообщения и догоняющее чтение", "5. Классификация сообщений", "6. Найденные агентства",
        "7. Дайджест, который получили бы админы", "8. Чистка сигналов", "9. Итоговые счётчики",
    ):
        assert heading in text
    assert text.count("вступил") >= 3  # joined chats
    assert "FloodWait" in text and "заявка отправлена" in text
    assert "Новые агентства из Telegram-чатов" in text  # the digest the fake bot "sent" to the admin
    assert "Удалено из каталога: @radar_demo_person" in text  # a link to a person is deleted
    assert "догоне" in text and "отсеяно префильтром" in text
    purged = int(re.search(r"Удалено чисткой: (\d+)", text).group(1))
    assert purged >= 1
    assert str(out / "sources.csv") in text


def test_demo_runs_with_defaults_and_reports_the_temp_output_folder(tmp_path, monkeypatch, capsys):
    _forbid_network(monkeypatch)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    assert demo.main(["--days", "1"]) == 0
    text = capsys.readouterr().out
    path = re.search(r"Файл источников: (.+)", text).group(1).strip()
    assert Path(path).is_file()
    assert "jobs_radar_demo_out_" in path
    assert not list(tmp_path.glob("jobs_radar_demo_db_*"))
