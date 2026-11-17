import json
from pathlib import Path

LOCALES = Path(__file__).resolve().parents[1] / "webapp" / "src" / "i18n"


def test_webapp_locales_have_identical_keys():
    uk = json.loads((LOCALES / "uk.json").read_text(encoding="utf-8"))
    ru = json.loads((LOCALES / "ru.json").read_text(encoding="utf-8"))
    assert set(uk) == set(ru)
    assert all(v.strip() for v in [*uk.values(), *ru.values()])
