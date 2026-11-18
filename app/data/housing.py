"""Housing reference content (uk/ru). Facts are limited to what is written in federal law,
checked against gesetze-im-internet.de on 16.11.2026. Anything that depends on the person's
situation (who pays rent, social housing eligibility) is phrased as "ask your office"."""

CHECKED = "2026-11-16"

SOURCES = [
    {"title": "§ 551 BGB — Kaution", "url": "https://www.gesetze-im-internet.de/bgb/__551.html"},
    {"title": "§ 573c BGB — Kündigungsfristen", "url": "https://www.gesetze-im-internet.de/bgb/__573c.html"},
    {"title": "§ 19 BMG — Wohnungsgeberbestätigung", "url": "https://www.gesetze-im-internet.de/bmg/__19.html"},
    {"title": "§ 2 WoVermittG — Maklerprovision", "url": "https://www.gesetze-im-internet.de/wovermrg/__2.html"},
    {"title": "SCHUFA — Datenkopie nach Art. 15 DSGVO", "url": "https://www.meineschufa.de/"},
]

TERMS = [
    {"de": "Kaltmiete", "uk": "Оренда без комунальних і опалення. Від неї рахують кауцію.",
     "ru": "Аренда без коммунальных и отопления. От неё считают залог."},
    {"de": "Nebenkosten", "uk": "Аванс за воду, сміття, опалення. Раз на рік — перерахунок.",
     "ru": "Аванс за воду, мусор, отопление. Раз в год — перерасчёт."},
    {"de": "Warmmiete", "uk": "Kaltmiete + Nebenkosten: стільки платите щомісяця. Світло окремо.",
     "ru": "Kaltmiete + Nebenkosten: столько платите в месяц. Свет отдельно."},
    {"de": "Kaution", "uk": "До 3 Kaltmiete. Можна платити трьома частинами (§ 551 BGB).",
     "ru": "До 3 Kaltmiete. Можно платить тремя частями (§ 551 BGB)."},
    {"de": "Wohnungsgeberbestätigung", "uk": "Довідка від орендодавця для Anmeldung. Видати зобов’язаний (§ 19 BMG).",
     "ru": "Справка от арендодателя для Anmeldung. Выдать обязан (§ 19 BMG)."},
    {"de": "SCHUFA", "uk": "Кредитна історія. Якщо ви тут недавно і записів немає — це нормально.",
     "ru": "Кредитная история. Если вы здесь недавно и записей нет — это нормально."},
    {"de": "Maklerprovision", "uk": "Ріелтора найняв орендодавець — ви не платите (§ 2 WoVermittG).",
     "ru": "Риелтора нанял арендодатель — вы не платите (§ 2 WoVermittG)."},
    {"de": "WBS", "uk": "Дозвіл на соціальне житло. Видає Wohnungsamt вашого міста.",
     "ru": "Разрешение на социальное жильё. Выдаёт Wohnungsamt вашего города."},
    {"de": "Übergabeprotokoll", "uk": "Протокол стану квартири. Сфотографуйте пошкодження — це захищає кауцію.",
     "ru": "Протокол состояния квартиры. Сфотографируйте повреждения — это защищает залог."},
    {"de": "Kündigungsfrist", "uk": "Орендар розриває договір за 3 місяці (§ 573c BGB).",
     "ru": "Арендатор расторгает договор за 3 месяца (§ 573c BGB)."},
]

CHECKLIST = {
    "uk": [
        "Паспорт і дозвіл на перебування.",
        "Дохід: 3 останні Gehaltsabrechnungen або договір.",
        "Платить Jobcenter чи Sozialamt — їхня письмова згода на цю квартиру до підписання.",
        "SCHUFA-Auskunft, якщо вже є записи.",
        "Mieterselbstauskunft від орендодавця.",
    ],
    "ru": [
        "Паспорт и разрешение на пребывание.",
        "Доход: 3 последних Gehaltsabrechnungen или договор.",
        "Платит Jobcenter или Sozialamt — их письменное согласие на эту квартиру до подписания.",
        "SCHUFA-Auskunft, если уже есть записи.",
        "Mieterselbstauskunft от арендодателя.",
    ],
}

SAFETY = {
    "uk": [
        "Гроші — лише після перегляду і підписаного договору.",
        "«Власник за кордоном», Western Union чи крипта — обман.",
    ],
    "ru": [
        "Деньги — только после просмотра и подписанного договора.",
        "«Владелец за границей», Western Union или крипта — обман.",
    ],
}
