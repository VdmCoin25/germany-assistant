import sys
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.database.models import JobAgency, JobKeyword, JobSignal, utcnow
from app.database.repositories.jobs_radar import JobsRadarRepository
from app.jobs_radar.agencies import normalize_domain, normalize_name, normalize_phone, upsert_agency
from app.jobs_radar.classifier import (
    LABELS, Classification, RuleClassifier, detect_city, detect_language, detect_profession, extract_contacts,
    get_classifier,
)
from app.jobs_radar.digest import build_agency_digest, send_agency_digest
from app.jobs_radar.prefilter import check, normalize
from app.jobs_radar.signals import load_terms, process_message, purge_old_signals
from app.services.ai.base import AINotConfigured

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import eval_jobs_classifier as ev  # noqa: E402

VACANCY = ("Шукаємо працівників на склад у Гамбурзі. Зарплата від 13,50 € на годину. "
           "Nord Logistik GmbH, jobs@jobs-nord.example, +49 000 1234567")


# --- prefilter (ported) ---

def test_normalize():
    assert normalize("  Ёлка —  FRONT-end\n") == "елка front end"


def test_hyphen_and_yo_match():
    r = check("Нужен фронт-энд разработчик, всё ещё", ["фронт энд"], [])
    assert r.passed and r.matched == ["фронт энд"]
    assert check("ёлка", ["елка"], []).passed


def test_exclude_wins_over_include():
    r = check("Ищу работу, сделаю сайт", ["сайт"], ["ищу работу"])
    assert not r.passed and r.reason == "exclude:ищу работу"


def test_no_include():
    r = check("погода хорошая", ["сайт"], ["вакансия"])
    assert not r.passed and r.reason == "no_include"


def test_empty_text():
    assert not check("   ", ["сайт"], []).passed


# --- extraction ---

@pytest.mark.parametrize("text,lang", [
    ("Шукаю роботу в Києві, їду з родиною", "uk"),
    ("Ищу работу, нужен совет", "ru"),
    ("Wir suchen Fahrer in Bremen", "de"),
    ("12345 ???", None),
])
def test_language(text, lang):
    assert detect_language(text) == lang


@pytest.mark.parametrize("text,city", [
    ("Робота у Берліні", "Berlin"),
    ("работа в Мюнхене", "München"),
    ("Job in Frankfurt am Main", "Frankfurt"),
    ("Arbeit in KÖLN", "Köln"),
    ("Роботи в Гамбурзі багато", "Hamburg"),
    ("wir wollen essen gehen", None),
])
def test_city(text, city):
    assert detect_city(text) == city


@pytest.mark.parametrize("text,prof", [
    ("Потрібні працівники на склад", "warehouse"),
    ("Reinigungskraft gesucht", "cleaning"),
    ("нужен водитель", "driver"),
    ("Pflegehelfer", "care"),
    ("помічник на кухню", "kitchen"),
    ("робота на стройці", "construction"),
    ("погода гарна", None),
])
def test_profession(text, prof):
    assert detect_profession(text) == prof


def test_contacts():
    c = extract_contacts(VACANCY + " Дата 01.02.2026")
    assert c["company"] == "Nord Logistik GmbH"
    assert c["email"] == "jobs@jobs-nord.example"
    assert c["phone"] == "+49 000 1234567"
    assert c["website"] is None
    c = extract_contacts("Сайт: https://www.jobs-nord.example/kontakt, тел 0000 1112233")
    assert c["website"].startswith("https://www.jobs-nord.example")
    assert c["phone"] == "0000 1112233"
    assert extract_contacts("Зарплата 13,50 € з 01.02.2026")["phone"] is None


async def test_rule_classifier_labels_and_contacts():
    clf = RuleClassifier()
    v = await clf.classify(VACANCY)
    assert v.label == "agency_vacancy" and 0 <= v.confidence <= 1
    assert (v.city, v.profession, v.language) == ("Hamburg", "warehouse", "uk")
    assert v.company == "Nord Logistik GmbH" and v.email and v.phone
    s = await clf.classify("Підкажіть, де знайти роботу на складі в Берліні? Я новенька.")
    assert s.label == "seeker_question" and s.city == "Berlin"
    assert (s.company, s.email, s.phone, s.website) == (None, None, None, None)
    r = await clf.classify("Правила чату: реклама заборонена, за порушення бан.")
    assert r.label == "chat_rules"
    assert (await clf.classify("Привіт усім, гарного дня!")).label == "noise"
    assert (await clf.classify("")).label == "noise"
    assert {v.label, s.label, r.label} <= set(LABELS)


@pytest.mark.parametrize("text", [
    "Терміново потрібні пакувальники на склад у Лейпцигу! Ставка 13,50 євро/год, договір. Телефонуйте +49 000 7654321",
    "Требуются комплектовщики на склад, Франкфурт. 15 евро в час, официально. Писать @recruiter_example",
    "Helfer (m/w/d) für Produktion in Ulm gesucht, 14 €/Std., Tel. +49 000 1112223",
])
async def test_vacancies_with_hiring_verbs(text):
    assert (await RuleClassifier().classify(text)).label == "agency_vacancy"


@pytest.mark.parametrize("text", [
    "Потрібні працівники на склад, 14 євро/год, оренда житла за рахунок роботодавця. Дзвоніть +49 000 1112223",
    "Требуются сварщики, зарплата 18 евро/час, аренда жилья за счёт компании, звоните +49 000 1112223",
    "Шукаємо пакувальників, проживання в кімнатах по 2 особи. Телефонуйте +49 000 1112223",
    "Helfer (m/w/d) für Produktion gesucht, 14 €/Std., Zimmer in Wohnheim gestellt. Tel. +49 000 1112223",
    "Потрібні водії, оренда авто надається, зарплата 2000 євро, дзвоніть +49 000 1112223",
    "Требуются грузчики в Гамбург, 15 евро в час, официально. Писать @recruiter_example",
])
async def test_vacancies_mentioning_housing_stay_vacancies(text):
    assert (await RuleClassifier().classify(text)).label == "agency_vacancy"


@pytest.mark.parametrize("text", [
    "Здається кімната в Берліні, 450 євро, пишіть",
    "Wohnung zu vermieten Berlin Miete 600 €",
    "Продам велосипед, работает отлично",
])
async def test_listings_stay_noise(text):
    assert (await RuleClassifier().classify(text)).label == "noise"


async def test_long_input_is_truncated():
    c = await RuleClassifier().classify("Привіт " * 5000 + VACANCY)
    assert c.label == "noise"


def test_get_classifier():
    assert isinstance(get_classifier(Settings(_env_file=None, bot_token="42:TEST", jobs_classifier="rules")), RuleClassifier)
    with pytest.raises(AINotConfigured, match="J2b"):
        get_classifier(Settings(_env_file=None, bot_token="42:TEST", jobs_classifier="ai"))


# --- fixture quality ---

def test_fixture_precision_thresholds():
    rows = ev.load()
    assert len(rows) == 40
    res = ev.evaluate(rows)
    assert res["agency_vacancy"]["precision"] >= 0.85
    assert res["seeker_question"]["precision"] >= 0.80


def test_fixture_is_synthetic():
    for row in ev.load():
        assert set(row) == {"text", "lang", "label", "city", "profession"}
        assert row["label"] in LABELS
        assert "@" not in row["text"] or ".example" in row["text"]
        assert "t.me" not in row["text"]


# --- normalization ---

def test_normalize_name():
    assert normalize_name("Nord Logistik GmbH") == normalize_name("NORD-Logistik  gmbh.") == "nord logistik"
    assert normalize_name("Sauber Rhein UG (haftungsbeschränkt)") == "sauber rhein"
    assert normalize_name("Müller e.K.") == "müller"
    assert normalize_name("ТОВ «Елбе Продакшн»") == "елбе продакшн"
    assert normalize_name(None) == ""


def test_normalize_domain():
    assert normalize_domain("https://www.Jobs-Nord.example/kontakt?x=1") == "jobs-nord.example"
    assert normalize_domain("jobs-nord.example") == "jobs-nord.example"
    assert normalize_domain("info@jobs-nord.example") == "jobs-nord.example"
    assert normalize_domain("nodots") is None
    assert normalize_domain(None) is None


def test_normalize_phone():
    assert normalize_phone("+49 000 1234567") == "+490001234567"
    assert normalize_phone("0049 000 1234567") == "+490001234567"
    assert normalize_phone("0151 000 12345") == "+4915100012345"
    assert normalize_phone("+49 (0) 000 1234567") == "+490001234567"
    assert normalize_phone("123") is None


# --- agencies ---

async def test_agency_dedup_by_name_variant(sm):
    async with sm() as s:
        a = await upsert_agency(s, Classification("agency_vacancy", 0.8, company="Nord Logistik GmbH"))
        b = await upsert_agency(s, Classification("agency_vacancy", 0.8, company="nord-logistik gmbh", website="https://www.jobs-nord.example"))
        assert a.id == b.id and b.signals_count == 2 and b.domain == "jobs-nord.example"
        assert await s.scalar(select(func.count(JobAgency.id))) == 1


async def test_agency_dedup_by_domain_and_phone(sm):
    async with sm() as s:
        a = await upsert_agency(s, Classification("agency_vacancy", 0.8, company="Alpha Personal GmbH", website="www.alpha.example"))
        b = await upsert_agency(s, Classification("agency_vacancy", 0.8, website="https://alpha.example/jobs", phone="+49 151 000 11223"))
        assert a.id == b.id and b.phone_norm == "+4915100011223" and b.signals_count == 2
        c = await upsert_agency(s, Classification("agency_vacancy", 0.8, phone="0151 000 11223"))
        assert c.id == a.id and c.signals_count == 3
        d = await upsert_agency(s, Classification("agency_vacancy", 0.8, company="Other Personal GmbH", phone="+49 000 9990000"))
        assert d.id != a.id
        assert await s.scalar(select(func.count(JobAgency.id))) == 2


async def test_agency_skipped_without_identity(sm):
    async with sm() as s:
        assert await upsert_agency(s, Classification("agency_vacancy", 0.8, email=None)) is None
        assert await s.scalar(select(func.count(JobAgency.id))) == 0


# --- signals ---

async def _terms(s):
    await JobsRadarRepository(s).seed_keywords_if_empty()
    return await load_terms(s)


async def test_load_terms_only_active(sm):
    async with sm() as s:
        s.add_all([JobKeyword(term="a", lang="de", kind="include"), JobKeyword(term="b", lang="de", kind="exclude"),
                   JobKeyword(term="c", lang="de", kind="include", active=False)])
        await s.flush()
        assert await load_terms(s) == (["a"], ["b"])


async def test_process_message_stores_labels_only(sm):
    async with sm() as s:
        terms = await _terms(s)
        clf = RuleClassifier()
        c = await process_message(s, clf, terms, chat_id=7, message_link="https://t.me/c/1/2", text=VACANCY)
        assert c.label == "agency_vacancy"
        sig = (await s.scalars(select(JobSignal))).one()
        assert (sig.kind, sig.chat_id, sig.message_link, sig.city, sig.language) == (
            "agency_vacancy", 7, "https://t.me/c/1/2", "Hamburg", "uk")
        assert {col.name for col in JobSignal.__table__.columns} == {
            "id", "chat_id", "message_link", "kind", "city", "profession", "language", "confidence", "created_at"}
        agency = (await s.scalars(select(JobAgency))).one()
        assert agency.name == "Nord Logistik GmbH" and agency.signals_count == 1

        seeker = await process_message(
            s, clf, terms, chat_id=7, message_link="https://t.me/c/1/3",
            text="Підкажіть, де знайти роботу на складі в Берліні? Я новенька.")
        assert seeker.label == "seeker_question"
        assert await s.scalar(select(func.count(JobAgency.id))) == 1


async def test_process_message_noise_and_prefilter_store_nothing(sm):
    async with sm() as s:
        terms = await _terms(s)
        clf = RuleClassifier()
        assert await process_message(s, clf, terms, chat_id=1, message_link="l1", text="Привіт, гарна погода") is None
        assert await process_message(s, clf, terms, chat_id=1, message_link="l2", text="Продам склад, роботи нема") is None
        noise = await process_message(s, clf, terms, chat_id=1, message_link="l3", text="Робота метро сьогодні змінена")
        assert noise.label == "noise"
        assert await s.scalar(select(func.count(JobSignal.id))) == 0
        assert await s.scalar(select(func.count(JobAgency.id))) == 0


@pytest.mark.parametrize("text,kind", [
    ("Шукаємо працівників на склад у Берліні, 14 євро/год, житло надається, оренда авто за рахунок фірми. +49 000 1112223",
     "agency_vacancy"),
    ("Wir suchen Fahrer (m/w/d) in Hamburg, 15 €/Std., Wohnung wird gestellt. Tel. +49 000 1112223", "agency_vacancy"),
    ("Правила чату: реклама заборонена, за порушення бан", "chat_rules"),
])
async def test_seed_terms_pipeline_stores_signal(sm, text, kind):
    async with sm() as s:
        terms = await _terms(s)
        c = await process_message(s, RuleClassifier(), terms, chat_id=1, message_link="l", text=text)
        assert c.label == kind
        assert (await s.scalars(select(JobSignal.kind))).all() == [kind]


@pytest.mark.parametrize("text", [
    "Сдаётся квартира в Берлине, 700 евро",
    "Wohnung zu vermieten Berlin Miete 600 €",
])
async def test_seed_terms_pipeline_housing_stores_nothing(sm, text):
    async with sm() as s:
        terms = await _terms(s)
        c = await process_message(s, RuleClassifier(), terms, chat_id=1, message_link="l", text=text)
        assert c is None or c.label == "noise"
        assert await s.scalar(select(func.count(JobSignal.id))) == 0
        assert await s.scalar(select(func.count(JobAgency.id))) == 0


async def test_purge_old_signals(sm):
    async with sm() as s:
        now = utcnow()
        for days, link in ((20, "old1"), (15, "old2"), (13, "new1"), (0, "new2")):
            s.add(JobSignal(chat_id=1, message_link=link, kind="seeker_question", confidence=0.7,
                            created_at=now - timedelta(days=days)))
        await s.flush()
        assert await purge_old_signals(s, 14) == 2
        left = set(await s.scalars(select(JobSignal.message_link)))
        assert left == {"new1", "new2"}


# --- digest ---

class FakeBot:
    def __init__(self, fail_for=()):
        self.sent = []
        self.fail_for = set(fail_for)

    async def send_message(self, chat_id, text, **kwargs):
        if chat_id in self.fail_for:
            raise RuntimeError("blocked")
        self.sent.append((chat_id, text, kwargs))


async def test_digest_only_unsent_and_marks_sent(sm):
    async with sm() as s:
        await upsert_agency(s, Classification("agency_vacancy", 0.8, company="Alpha <b>Personal</b> GmbH", website="alpha.example"))
        old = await upsert_agency(s, Classification("agency_vacancy", 0.8, company="Beta Personal GmbH"))
        old.digest_sent_at = utcnow()
        await s.flush()

        text, ids = await build_agency_digest(s)
        assert len(ids) == 1 and "Beta" not in text
        assert "&lt;b&gt;Personal&lt;/b&gt;" in text and "alpha.example" in text

        bot = FakeBot()
        assert await send_agency_digest(bot, s, [11, 12]) == 1
        assert [c for c, _, _ in bot.sent] == [11, 12] and bot.sent[0][2]["parse_mode"] == "HTML"
        assert await build_agency_digest(s) == (None, [])
        assert await send_agency_digest(bot, s, [11]) == 0 and len(bot.sent) == 2


async def test_digest_limit_and_failed_delivery(sm):
    async with sm() as s:
        for i in range(35):
            await upsert_agency(s, Classification("agency_vacancy", 0.8, company=f"Firma{i:02d} GmbH"))
        text, ids = await build_agency_digest(s)
        assert len(ids) == 30 and "35" in text and "5" in text.splitlines()[-1]

        assert await send_agency_digest(FakeBot(fail_for=[1]), s, [1]) == 0
        assert (await build_agency_digest(s))[1] == ids
        assert await send_agency_digest(FakeBot(), s, [1]) == 30
        assert len((await build_agency_digest(s))[1]) == 5
