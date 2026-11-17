"""Synthetic data for the offline Jobs Source Radar demo (`python -m app.jobs_radar.demo`).

Everything here is fictional: chats, companies, phone numbers (+49 .. 0000 00xx), e-mails and websites
(".example" domains). No real people, companies or chat usernames. Only plain data, no Telethon imports.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class DemoChat:
    username: str | None  # public chats and users; None for private invite links
    kind: str  # group | channel | invite | user | dead
    title: str = ""
    members: int = 0
    about: str = ""  # public description: the metadata step parses "ads policy" and the admin contact from it
    invite_hash: str | None = None
    join: str = "ok"  # ok | flood_once (FloodWait on the first attempt) | request_sent (admin approval needed)
    seed: bool = True  # False: not imported, only reachable through a link found in a message
    language: str | None = None  # hints from the seed list (like columns of the import CSV)
    city: str | None = None


@dataclass(frozen=True)
class DemoMessage:
    chat: str  # DemoChat.username
    day: int  # simulated day: 0 = first day, -1 = history from before the demo starts
    hour: int  # hour of the day (UTC), 8..22 so every join of that day has already happened
    text: str
    offline: bool = False  # posted while the monitor was "offline": only the catch-up finds it
    age_days: int = 0  # > 0: the signal is aged by this many days, to show the retention purge


CHATS: tuple[DemoChat, ...] = (
    DemoChat("radar_demo_chat_01", "group", "Демо: Работа в Берлине", 18400,
             "Вакансии и вопросы о работе. Реклама заборонена. Адмін: @radar_demo_admin_01",
             language="uk", city="Berlin"),
    DemoChat("radar_demo_chat_02", "channel", "Демо: Робота в Баварії", 5200,
             "Вакансії для українців. Реклама по договорённости, писати @radar_demo_admin_02",
             join="flood_once", language="uk"),
    DemoChat("radar_demo_chat_03", "group", "Demo: Minijob Deutschland", 9300,
             "Minijobs und Aushilfen. Keine Werbung.", language="de"),
    DemoChat("radar_demo_chat_04", "group", "Демо: Работа в Гамбурге", 2100,
             "Чат про работу в Гамбурге. Платная реклама, контакт t.me/radar_demo_admin_04",
             language="ru", city="Hamburg"),
    DemoChat(None, "invite", "Демо: закрытая биржа", 640,
             "Заявки одобряет админ @radar_demo_admin_05", invite_hash="DemoInviteHash01", join="request_sent",
             seed=True),
    DemoChat("radar_demo_person", "user"),  # a link to a private person pasted by mistake: must be deleted
    DemoChat("radar_demo_chat_05", "group", "Демо: Зарплаты и графики", 12000,
             "Обсуждаем зарплаты, графики и договоры.", language="ru"),
    DemoChat("radar_demo_chat_06", "group", "Демо: Склад и логистика", 3400,
             "Работа на складах. Реклама запрещена.", language="uk"),
    DemoChat("radar_demo_chat_07", "group", "Демо: Уход и Pflege", 1500,
             "Вакансии в сфере ухода.", language="uk"),
    DemoChat("radar_demo_chat_08", "channel", "Демо: Новые вакансии", 800, "Канал вакансий.", language="ru"),
    # found only through links in messages (candidates)
    DemoChat("radar_demo_chat_09", "group", "Демо: Работа в Лейпциге", 2700, "Реклама заборонена.",
             seed=False, language="uk"),
    DemoChat("radar_demo_chat_10", "group", "Демо: Работа в Германии", 6100, "Реклама по договорённости.",
             seed=False, language="ru"),
    DemoChat("radar_demo_gone", "dead", seed=False),
    DemoChat("radar_demo_manager", "user", seed=False),  # a person's handle in an ad: becomes a candidate, then deleted
    DemoChat(None, "dead", invite_hash="DemoInviteHash02", seed=False),  # expired private link from a message
)

# The joiner takes approved chats by score, so the order of joins is fixed by the seed data below:
# chat_01 and chat_02 on day 1, chat_04, chat_05 and chat_07 on day 2, chat_08 and chat_10 on day 3.
_C1, _C2, _C4, _C5, _C7, _C8, _C10 = (
    f"radar_demo_chat_{n:02d}" for n in (1, 2, 4, 5, 7, 8, 10)
)


def _m(chat, day, hour, text, **kw) -> DemoMessage:
    return DemoMessage(chat, day, hour, text, **kw)


MESSAGES: tuple[DemoMessage, ...] = (
    # --- history from before the demo: the monitor never processes it (baseline is set at join) ---
    _m(_C1, -1, 10, "Шукаємо працівників на склад. Демо-історія: цей пост з'явився до вступу монітора."),
    _m(_C2, -1, 11, "Требуется водитель, оплата 17 евро/час. Старый пост до вступления монитора."),
    # --- day 0: chat_01 and chat_02 are joined ---
    _m(_C1, 0, 8, "Wir suchen Lagerhelfer (m/w/d) in Berlin. Beispiel Zeitarbeit GmbH, Stundenlohn 14 €, Vollzeit. "
                  "Bewerbung: jobs@beispiel-zeitarbeit.example, Tel. +49 30 0000 0011"),
    _m(_C1, 0, 9, "Подскажите, где найти работу в Берлине без знания немецкого? Ищу работу уборщицей"),
    _m(_C1, 0, 10, "Правила чата: реклама запрещена, спам и флуд — бан. Добро пожаловать!"),
    _m(_C1, 0, 11, "Доброго ранку всім! Гарного дня і хорошого настрою"),
    _m(_C1, 0, 12, "Шукаємо працівників на склад у Берліні. Зарплата 15 євро/год, оформлення за Arbeitsvertrag. "
                   "Агентство Demo Personal GmbH, пишіть +49 30 0000 0012 або www.demo-personal.example, "
                   "менеджер @radar_demo_manager"),
    _m(_C1, 0, 13, "Шукаю роботу на складі у Гамбурзі, підкажіть, будь ласка, як знайти вакансії?"),
    _m(_C1, 0, 14, "Продам детскую коляску, Берлин, самовывоз"),
    _m(_C1, 0, 15, "Корисна група по роботі в Лейпцигу: t.me/radar_demo_chat_09 і ще @radar_demo_chat_10"),
    _m(_C1, 0, 16, "Mietwohnung in Leipzig zu vermieten, 2 Zimmer, nur von privat"),
    _m(_C2, 0, 9, "Запрошуємо на роботу у сфері прибирання. ТОВ «Демо Рекрут», Лейпциг, 13 євро/год. "
                  "Контакт: info@demo-rekrut.example"),
    _m(_C2, 0, 10, "Ищу подработку в Мюнхене, кто знает агентства?"),
    _m(_C2, 0, 11, "Заробіток у інтернеті без вкладень! Робота на телефоні, пиши в особисті, 500 євро на день"),
    _m(_C2, 0, 12, "Требуются водители категории B в Гамбург. Ставка 16 €/час, график 5/2. "
                   "Musterfirma Logistik GmbH, звоните +49 40 0000 0021"),
    _m(_C2, 0, 13, "Чи є робота для водія в Кельні? Допоможіть, будь ласка"),
    _m(_C2, 0, 14, "Курс криптовалют, швидкий заробіток, переходьте за посиланням"),
    _m(_C2, 0, 18, "Закрита група для обміну досвідом (за запрошенням): https://t.me/+DemoInviteHash02 "
                   "та ще @radar_demo_gone", offline=True),
    # --- day 1: chat_04, chat_05 and chat_07 are joined during the next day ---
    _m(_C1, 1, 9, "Beispiel Zeitarbeit GmbH sucht Reinigungskräfte in Köln, Teilzeit, 13,50 €. "
                  "Bewerbung per Tel. +49 30 0000 0011"),
    _m(_C1, 1, 10, "Suche Minijob in Köln, wer kennt gute Firmen? Wo finde ich Arbeit ohne Deutschkenntnisse?"),
    _m(_C1, 1, 12, "Кто работает на складе в Берлине? Какой график и зарплата?"),
    _m(_C1, 1, 14, "Verkaufe Sofa, zu verkaufen, Abholung Hamburg"),
    _m(_C1, 1, 17, "Ищем поваров и помощников на кухню, Дрезден. Оплата 15 евро/час. "
                   "Demo Gastro GmbH, +49 351 0000 0033", offline=True),
    _m(_C1, 1, 19, "Шукаю роботу, підкажіть, чи є вакансії для сиделки?", offline=True),
    _m(_C2, 1, 9, "Вакансія: комплектувальник на склад, Франкфурт. Шукаємо людей, 15 євро/год, зміни. "
                  "Muster Logistik Partner GmbH, kontakt@muster-logistik.example"),
    _m(_C2, 1, 11, "Мені потрібна підробіток на вихідні, підкажіть де шукати роботу?"),
    _m(_C2, 1, 13, "Правила групи: реклама заборонена, за порушення бан. Ласкаво просимо"),
    _m(_C2, 1, 15, "Продам велосипед б/у, Лейпциг, недорого"),
    _m(_C2, 1, 20, "Помогите найти работу поваром в Дрездене, подскажите пожалуйста", offline=True),
    _m(_C7, 1, 8, "Wir suchen Fahrer (m/w/d) für Nürnberg. Stellenangebot der Fiktiv Transport GmbH, "
                  "Gehalt ab 2.400 €, Vollzeit. Bewerbung unter www.fiktiv-transport.example"),
    _m(_C7, 1, 10, "Hilfe, ich suche Arbeit als Fahrer in Hamburg. Gibt es Stellen?"),
    _m(_C7, 1, 12, "Guten Morgen zusammen, schönes Wochenende!"),
    _m(_C7, 1, 16, "Chatregeln: keine Werbung, Spam führt zur Sperre. Regeln beachten. Willkommen"),
    _m(_C7, 1, 21, "Aushilfe gesucht, Minijob im Lager, Frankfurt. Stundenlohn 13 €. "
                    "Demo Lager Service GmbH, Tel. +49 69 0000 0055",
       offline=True),
    _m(_C4, 1, 9, "Вакансия: водитель-экспедитор, Гамбург. Требуется человек с правами, ставка 16 €/час. "
                  "Musterfirma Logistik GmbH, +49 40 0000 0021"),
    _m(_C4, 1, 12, "Подскажите, как найти работу в Гамбурге без немецкого? Ищу работу на складе"),
    _m(_C4, 1, 18, "Сдаётся комната в Гамбурге, 450 €, звоните +49 40 0000 0044"),
    _m(_C4, 1, 20, "Всем привет! Как дела, чат?", offline=True),
    # --- day 2: chat_08 and chat_10 are joined; some signals are aged to show the retention purge ---
    _m(_C1, 2, 9, "Fiktiv Pflege UG: Stellenangebot Pflegehelfer (m/w/d) in München, Gehalt ab 2.600 €, "
                  "Vollzeit. Bewerbung unter www.fiktiv-pflege.example"),
    _m(_C1, 2, 11, "Ищу работу в Берлине, есть ли вакансии для сиделки? Подскажите",
       age_days=18),
    _m(_C1, 2, 13, "Шукаємо кухарів та помічників на кухню, Берлін. Зарплата 15 євро/год. "
                   "Агентство Demo Personal GmbH, +49 30 0000 0012", age_days=20),
    _m(_C1, 2, 21, "Хто знає, де знайти роботу електриком? Підкажіть, будь ласка", offline=True),
    _m(_C2, 2, 10, "Ищем сварщиков на работу в Мюнхене, зарплата 20 евро/час. "
                   "Beispiel Zeitarbeit GmbH, jobs@beispiel-zeitarbeit.example", age_days=25),
    _m(_C2, 2, 14, "Шукаю роботу в Німеччині, підкажіть, як знайти вакансії для жінок?", age_days=16),
    _m(_C2, 2, 19, "Корисний чат з працевлаштування: t.me/radar_demo_chat_09", offline=True),
    _m(_C7, 2, 9, "Stellenangebot: Reinigungskraft (m/w/d), Teilzeit, Berlin. "
                  "Beispiel Zeitarbeit GmbH, Tel. +49 30 0000 0011"),
    _m(_C7, 2, 13, "Suche Arbeit im Lager, Minijob, wer kennt Firmen? Gibt es Stellen in Nürnberg?"),
    _m(_C7, 2, 20, "Zu verkaufen: Fahrrad, Mietwohnung gesucht", offline=True),
    _m(_C4, 2, 10, "Работа: ищем упаковщиков на склад в Гамбурге, 14 евро/час, график по сменам. "
                   "Demo Logistik Partner GmbH, kontakt@demo-logistik.example"),
    _m(_C4, 2, 15, "Ищу работу, подскажите как найти подработку в Гамбурге?", offline=True),
    _m(_C5, 2, 9, "Правила группы: реклама запрещена, нарушители получают бан. Добро пожаловать в чат"),
    _m(_C5, 2, 12, "Кто знает, какая зарплата на складе в Лейпциге? Подскажите, пожалуйста"),
    _m(_C5, 2, 16, "Требуются сборщики мебели, Дрезден. Оплата 16 €/час, оформление Arbeitsvertrag. "
                   "Fiktiv Montage GmbH, +49 351 0000 0066", offline=True),
    _m(_C5, 2, 21, "Привет всем, хорошего вечера!", offline=True),
    _m(_C8, 2, 10, "Нова вакансія: охоронець на об'єкт, Дрезден. Зарплата 14 євро/год. "
                   "Fiktiv Sicherheit GmbH, +49 351 0000 0088"),
    _m(_C8, 2, 15, "Правила каналу: реклама заборонена, за порушення бан. Ласкаво просимо"),
    _m(_C10, 2, 9, "Шукаємо комплектувальників на склад у Лейпцигу. Зарплата 15 євро/год, зміни. "
                  "Muster Logistik Partner GmbH, +49 341 0000 0077"),
    _m(_C10, 2, 14, "Підкажіть, будь ласка, де знайти роботу водієм у Лейпцигу? Допоможіть"),
    _m(_C10, 2, 19, "Guten Abend! Продам куртку, Leipzig, zu verkaufen", offline=True),
)
