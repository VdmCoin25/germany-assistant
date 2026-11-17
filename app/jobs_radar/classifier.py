"""Message classifier for the Jobs Source Radar. The default implementation is rule-based and local."""
import re
from dataclasses import dataclass
from typing import Protocol

from app.config import Settings
from app.data.jobs_radar_vocab import CITIES, PROFESSIONS
from app.jobs_radar.prefilter import normalize
from app.services.ai.base import AINotConfigured

LABELS = ("seeker_question", "agency_vacancy", "chat_rules", "noise")


@dataclass
class Classification:
    label: str
    confidence: float
    city: str | None = None
    profession: str | None = None
    language: str | None = None
    company: str | None = None
    website: str | None = None
    email: str | None = None
    phone: str | None = None


class JobClassifier(Protocol):
    async def classify(self, text: str) -> Classification: ...


def _compile(rules: list[tuple[str, float]]) -> list[tuple[re.Pattern, float]]:
    return [(re.compile(p), w) for p, w in rules]


_VACANCY = _compile([
    (r"(?<!\w)(шукаємо|ищем|набираємо|набираем|wir suchen|suchen wir|we are hiring|we're hiring)(?!\w)", 2.0),
    (r"(?<!\w)(запрошуємо|приглашаем|пропонуємо|предлагаем|wir bieten|bieten wir|wir stellen)", 1.5),
    (r"(?<!\w)(вакансі|вакансия|вакансии|вакансий|stellenangebot|stellenanzeige|offene stelle)", 1.5),
    (r"(зарплат|оплата|ставка|stundenlohn|gehalt|(?<!\w)lohn(?!\w)|(?<!\w)\d+(?:[.,]\d+)?\s?(?:€|eur|euro|євро|евро)|€\s?\d)", 1.0),
    (r"(zeitarbeit|personalvermittlung|personaldienstleist|arbeitnehmerueberlassung|arbeitnehmerüberlassung|gmbh|(?<!\w)тов(?!\w)|рекрутингов|кадрове агентство|кадровое агентство)", 1.5),
    (r"(оформлення|оформление|трудовий договір|трудовой договор|arbeitsvertrag|vollzeit|teilzeit|full.?time|schichtarbeit|змін[аи]|смен[аы])", 0.7),
    (r"(пишіть|пишите|звоніть|звоните|дзвоніть|телефонуйте|bewerbung|bewerben sie|melden sie sich|rufen sie)", 1.0),
])

_VACANCY_CORE = (0, 1, 2, 4)
_VACANCY_PAY_OR_SCHEDULE = (3, 5)

_HIRING = re.compile(
    r"(?<!\w)(потрібн[іиаео]|треба|требуются|требуется|нужны|нужен|нужна|gesucht|suchen ab sofort|ab sofort)(?!\w)"
)
_HIRING_CONTEXT = re.compile(r"\(m/w/d\)|\(w/m/d\)|\(m/f/d\)")
_NOT_A_JOB = re.compile(
    r"(?<!\w)(здається|здаю|сдаю|сдается|сдам|продам|продається|продается|zu vermieten|vermiete|zu verkaufen|verkaufe)(?!\w)"
    r"|(?<!\w)(wohnung|zimmer|miete)\s+(frei|zu vermieten|gesucht von privat)"
)
_HANDLE = re.compile(r"(?<![\w@/.])@[A-Za-z][A-Za-z0-9_]{3,31}")  # scoring hint only, never stored
_MAX_LEN = 4096

_SEEKER = _compile([
    (r"(шукаю|ищу|suche|sucht)\s+(?:\w+\s+){0,2}(роботу|работу|робот|подработк|підробіт|arbeit|job|stelle|minijob)", 3.0),
    (r"(?<!\w)(підкажіть|подскажите|підкажи|подскажи|порадьте|посоветуйте|поділіться|поделитесь|wo finde ich|kann mir jemand|kennt jemand|wer kennt|хто знає|кто знает|як знайти|как найти|як можна знайти|как можно найти)", 2.0),
    (r"(знайти|найти|найду|знайду|finde ich|finden)\s+(?:\w+\s+){0,2}(роботу|работу|arbeit|job|стелле|stelle)", 1.5),
    (r"(?<!\w)(допоможіть|помогите|hilfe|hilft mir)", 1.0),
    (r"(?<!\w)(чи є|есть ли|gibt es|чи можна|можно ли|darf ich|может ли)", 1.0),
    (r"(?<!\w)(чи є|есть ли|gibt es)\s+(?:\w+\s+){0,2}(робот|работ|arbeit|job|вакансі|вакансии|стелле|stelle)", 1.0),
    (r"(?<!\w)(я|мені|мене|мне|меня|мій|мой|моя|ich|mir|mich|mein|meine)(?!\w)", 0.7),
])

_RULES = _compile([
    (r"(правила (чату|чата|групи|группы|спільноти|сообщества)|chatregeln|gruppenregeln|(?<!\w)regeln(?!\w)|(?<!\w)rules(?!\w))", 3.0),
    (r"(реклама (заборонена|запрещена|тільки|только)|рекламу? (заборонено|запрещено)|werbung (ist )?(verboten|nicht erlaubt)|keine werbung|заборонена реклама|запрещена реклама)", 2.0),
    (r"((?<!\w)бан(?!\w)|(?<!\w)бан[уеом]|забан|заблок|(?<!\w)ban(?!\w)|gesperrt|verstoss|за порушення|за нарушение)", 1.5),
    (r"(ласкаво просимо|добро пожаловать|willkommen|вітаємо в)", 1.0),
    (r"(?<!\w)(спам|флуд|offtopic|оффтоп|офтоп)", 1.0),
])

_JOB_WORD = re.compile(
    r"(робот|работ|arbeit|(?<!\w)job|minijob|підробіт|подработ|вакансі|зайнятіст|працевлаш|трудоустр|стелле|(?<!\w)stelle)"
)

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
_URL = re.compile(
    r"(?:https?://|www\.)[^\s,;)>\]]+"
    r"|(?<![\w@.])(?:[a-z0-9\-]+\.)+(?:de|com|eu|net|org|info|jobs|work|example|ua|pl|at|ch|io|biz|online|cc)"
    r"(?:/[^\s,;)>\]]*)?(?![\w@])",
    re.IGNORECASE,
)
_DATE = re.compile(r"\b\d{1,2}\.\d{1,2}\.(?:\d{4}|\d{2})\b")
_PHONE = re.compile(r"(?<![\w.])(?:\+|00|0)\d[\d \t().\-/]{6,18}\d(?!\w)")
_COMPANY_LEGAL = re.compile(
    r"\b((?:[A-ZÄÖÜ][\wÄÖÜäöüß&\-]*\s+){1,4}"
    r"(?:GmbH(?:\s*&\s*Co\.?\s*KG)?|mbH|UG(?:\s*\(haftungsbeschränkt\))?|AG|KG|e\.\s?K\.))"
)
_COMPANY_QUOTED = re.compile(
    r"(?:ТОВ|ТзОВ|ООО|компанія|компания|фірма|фирма|агентство|агенція|Firma|Agentur)\s*[«\"“]([^»\"”\n]{2,60})[»\"”]",
    re.IGNORECASE,
)


def detect_language(text: str) -> str | None:
    cyr = len(re.findall(r"[а-яіїєґё]", text, re.IGNORECASE))
    lat = len(re.findall(r"[a-zäöüß]", text, re.IGNORECASE))
    if cyr == 0 and lat == 0:
        return None
    if cyr >= lat:
        return "uk" if re.search(r"[іїєґ]", text, re.IGNORECASE) else "ru"
    return "de"


def _city_patterns() -> list[tuple[str, re.Pattern]]:
    out = []
    for city, variants in CITIES.items():
        parts = []
        for v in variants:
            if re.search(r"[a-zäöüß]", v):
                parts.append(f"{re.escape(v.capitalize())}|{re.escape(v.upper())}")
            else:
                parts.append(f"(?i:{re.escape(v)})")
        out.append((city, re.compile(r"(?<!\w)(?:" + "|".join(parts) + r")")))
    return out


_CITY_PATTERNS = _city_patterns()
_PROFESSION_PATTERNS = [
    (name, re.compile("|".join(r"(?<!\w)" + re.escape(s) for s in stems))) for name, stems in PROFESSIONS.items()
]


def _earliest(patterns: list[tuple[str, re.Pattern]], text: str) -> str | None:
    best: tuple[int, str] | None = None
    for name, pat in patterns:
        m = pat.search(text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), name)
    return best[1] if best else None


def detect_city(text: str) -> str | None:
    return _earliest(_CITY_PATTERNS, text)


def detect_profession(text: str) -> str | None:
    return _earliest(_PROFESSION_PATTERNS, normalize(text))


def extract_contacts(text: str) -> dict[str, str | None]:
    email_m = _EMAIL.search(text)
    rest = _EMAIL.sub(" ", text)
    url_m = _URL.search(rest)
    cleaned = _DATE.sub(" ", _URL.sub(" ", rest))
    phone = None
    for m in _PHONE.finditer(cleaned):
        if 8 <= len(re.sub(r"\D", "", m.group())) <= 15:
            phone = m.group().strip()
            break
    company = None
    m = _COMPANY_LEGAL.search(text)
    if m:
        company = re.sub(r"\s+", " ", m.group(1)).strip()
    else:
        m = _COMPANY_QUOTED.search(text)
        if m:
            company = m.group(1).strip()
    return {
        "company": company,
        "website": url_m.group().rstrip(".") if url_m else None,
        "email": email_m.group().lower() if email_m else None,
        "phone": phone,
    }


def _score(rules: list[tuple[re.Pattern, float]], text: str) -> float:
    return sum(w for p, w in rules if p.search(text))


def _confidence(score: float) -> float:
    return round(min(0.95, 0.45 + 0.1 * (score - 2.0)), 2)


class RuleClassifier:
    async def classify(self, text: str) -> Classification:
        return self.classify_sync(text)

    def classify_sync(self, text: str) -> Classification:
        text = (text or "")[:_MAX_LEN]
        norm = normalize(text)
        if not norm:
            return Classification("noise", 0.9)
        lang = detect_language(text)
        contacts = extract_contacts(text)
        has_contact = any(contacts[k] for k in ("website", "email", "phone")) or bool(_HANDLE.search(text))

        vacancy = _score(_VACANCY, norm)
        core = sum(w for i, (p, w) in enumerate(_VACANCY) if i in _VACANCY_CORE and p.search(norm))
        if _HIRING.search(norm) and (_JOB_WORD.search(norm) or _HIRING_CONTEXT.search(norm) or detect_profession(text)):
            vacancy += 2.0
            core += 2.0
        pay = any(_VACANCY[i][0].search(norm) for i in _VACANCY_PAY_OR_SCHEDULE)
        if has_contact and (core > 0 or pay):
            vacancy += 1.5
        if core == 0 and _NOT_A_JOB.search(norm):
            vacancy -= 3.0
        seeker = _score(_SEEKER, norm) + (1.0 if "?" in text else 0.0)
        if not _JOB_WORD.search(norm):
            seeker = min(seeker, 1.5)
        rules = _score(_RULES, norm)

        if rules >= 3.0 and rules >= vacancy:
            return Classification("chat_rules", _confidence(rules), language=lang)
        if vacancy >= 3.0 and vacancy > seeker:
            return Classification(
                "agency_vacancy", _confidence(vacancy), detect_city(text), detect_profession(text), lang, **contacts
            )
        if seeker >= 3.0:
            return Classification("seeker_question", _confidence(seeker), detect_city(text), detect_profession(text), lang)
        return Classification("noise", 0.6, language=lang)


def get_classifier(settings: Settings) -> JobClassifier:
    name = (settings.jobs_classifier or "rules").lower()
    if name == "rules":
        return RuleClassifier()
    if name == "ai":
        raise AINotConfigured("JOBS_CLASSIFIER=ai is not implemented yet: the AI classifier is a later step (J2b)")
    raise ValueError(f"Unknown JOBS_CLASSIFIER value: {settings.jobs_classifier!r}")
