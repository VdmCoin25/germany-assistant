"""Short answers for the reference section and the "what changed" feed.

Rules (CLAUDE.md): every rule here comes from an official or publicly funded source that was opened
and read on `checked` — not from memory, not from news. When a rule changes, update the text, the
source and the date together. Points are short on purpose: the link is for the details.
"""
from datetime import date

CHECKED = date(2026, 11, 17)

# topic -> {"uk": [...], "ru": [...], "source": (title, url)}
GUIDES: dict[str, dict] = {
    "residence": {
        "uk": [
            "Посвідка за §24, яка діяла 1 лютого 2026, автоматично діє до 4 березня 2027.",
            "Подавати заяву чи йти в Ausländerbehörde для цього не потрібно.",
            "Не стосується тих, хто приїхав після 1 лютого 2026, і тих, у кого поки лише Fiktionsbescheinigung.",
        ],
        "ru": [
            "Вид на жительство по §24, который действовал 1 февраля 2026, автоматически действует до 4 марта 2027.",
            "Подавать заявление или идти в Ausländerbehörde для этого не нужно.",
            "Не касается тех, кто приехал после 1 февраля 2026, и тех, у кого пока только Fiktionsbescheinigung.",
        ],
        "source": ("Landesamt für Einwanderung Berlin",
                   "https://www.berlin.de/einwanderung/ueber-uns/aktuelles/artikel.1647418.php"),
    },
    "jobcenter": {
        "uk": [
            "З 1 липня 2026 замість Bürgergeld виплачують Grundsicherungsgeld.",
            "Один пропущений термін у Jobcenter: мінус 30% на місяць.",
            "Три пропущені терміни: Jobcenter може зупинити виплати. Якщо в перший місяць прийти особисто, їх повертають.",
            "Відмова від запропонованої роботи: без базової виплати. Поважні причини враховують.",
        ],
        "ru": [
            "С 1 июля 2026 вместо Bürgergeld выплачивают Grundsicherungsgeld.",
            "Один пропущенный термин в Jobcenter: минус 30% на месяц.",
            "Три пропущенных термина: Jobcenter может остановить выплаты. Если в первый месяц прийти лично, их вернут.",
            "Отказ от предложенной работы: без базовой выплаты. Уважительные причины учитываются.",
        ],
        "source": ("Kreis Darmstadt-Dieburg, Kommunales Jobcenter",
                   "https://www.ladadi.de/medien/pdfs/fb-520-2-esc-kfb/buergergeld/grundsicherung-praesentation.pdf"),
    },
    "transport": {
        "uk": [
            "Поки діє статус §24, українські права дійсні в Німеччині без обміну.",
            "З 18 серпня 2026 їх можна обміняти на німецькі без іспитів.",
            "Для обміну: документ, фото, права з перекладом, Meldebescheinigung. Термін бронюйте у Führerscheinstelle свого міста.",
        ],
        "ru": [
            "Пока действует статус §24, украинские права действительны в Германии без обмена.",
            "С 18 августа 2026 их можно обменять на немецкие без экзаменов.",
            "Для обмена: документ, фото, права с переводом, Meldebescheinigung. Термин бронируйте в Führerscheinstelle своего города.",
        ],
        "source": ("Landeshauptstadt Wiesbaden",
                   "https://www.wiesbaden.de/vv/produkte/34/umschreibung-auslaendischer-fuehrerschein-ukraine"),
    },
    "children": {
        "uk": [
            "Місце в Kita шукають через Jugendamt або портал свого міста. Правила в містах різні.",
            "Берлін: спочатку заява на Kita-Gutschein у Jugendamt району.",
            "Мюнхен: реєстрація через kita finder+ до 3 березня 2027, місця розподіляють з 4 березня.",
        ],
        "ru": [
            "Место в Kita ищут через Jugendamt или портал своего города. Правила в городах разные.",
            "Берлин: сначала заявление на Kita-Gutschein в Jugendamt района.",
            "Мюнхен: регистрация через kita finder+ до 3 марта 2027, места распределяют с 4 марта.",
        ],
        "source": ("Landeshauptstadt München",
                   "https://stadt.muenchen.de/service/uk-UA/info/10470323/"),
    },
    "safety": {
        "uk": [
            "Не платіть завдаток чи за ключі, поки не побачили квартиру і не підписали договір.",
            "Підозріло: дуже низька ціна, «власник за кордоном», переписка лише в месенджері, просять фото паспорта.",
            "Справжній роботодавець не просить відкрити рахунок, пройти відеоідентифікацію чи дати дані банку на старті.",
            "Якщо вже заплатили: одразу в банк, збережіть скріншоти, заява в поліцію (можна онлайн).",
        ],
        "ru": [
            "Не платите залог или за ключи, пока не увидели квартиру и не подписали договор.",
            "Подозрительно: очень низкая цена, «хозяин за границей», переписка только в мессенджере, просят фото паспорта.",
            "Настоящий работодатель не просит открыть счёт, пройти видеоидентификацию или дать данные банка на старте.",
            "Если уже заплатили: сразу в банк, сохраните скриншоты, заявление в полицию (можно онлайн).",
        ],
        "source": ("Europäisches Verbraucherzentrum Deutschland",
                   "https://www.evz.de/einkaufen-internet/vorsicht-falle/mietbetrug.html"),
    },
    "recognition": {
        "uk": [
            "Для регульованих професій визнання обов’язкове. Для інших — ні, але воно підвищує шанси.",
            "Консультація IQ допоможе знайти німецьку назву професії і потрібну установу.",
            "Витрати на процедуру й переклади інколи покриває Jobcenter або Agentur für Arbeit.",
        ],
        "ru": [
            "Для регулируемых профессий признание обязательно. Для остальных — нет, но оно повышает шансы.",
            "Консультация IQ поможет найти немецкое название профессии и нужное ведомство.",
            "Расходы на процедуру и переводы иногда покрывает Jobcenter или Agentur für Arbeit.",
        ],
        "source": ("Netzwerk IQ",
                   "https://netzwerk-iq.de/fileadmin/Redaktion/Downloads/Fachstelle_Beratung_und_Qualifizierung/Ukraine/DE_AQB_f%C3%BCr_Ratsuchende.pdf"),
    },
}

# Newest first. Only changes confirmed on an official page; pending laws stay out until published.
CHANGES: list[dict] = [
    {"date": date(2026, 8, 18), "topic": "transport",
     "uk": "Українські права можна обміняти на німецькі без іспитів.",
     "ru": "Украинские права можно обменять на немецкие без экзаменов."},
    {"date": date(2026, 7, 1), "topic": "jobcenter",
     "uk": "Bürgergeld замінили на Grundsicherungsgeld, санкції стали суворішими.",
     "ru": "Bürgergeld заменили на Grundsicherungsgeld, санкции стали строже."},
]


def guides_json() -> dict:
    return {k: {"uk": g["uk"], "ru": g["ru"], "source": {"title": g["source"][0], "url": g["source"][1]},
                "checked": CHECKED.isoformat()} for k, g in GUIDES.items()}


def changes_json() -> list[dict]:
    return [{**c, "date": c["date"].isoformat()} for c in CHANGES]
