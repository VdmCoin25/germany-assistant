"""Initial catalog of official sources.

Only official / public-sector sites. `checked_at` = date the link was confirmed
reachable, not a legal review of the content. Admins update entries in the DB.
"""
from datetime import datetime, timezone

CHECKED = datetime(2026, 11, 17, tzinfo=timezone.utc)

G4U = "https://www.germany4ukraine.de"
BAMF = "https://www.bamf.de"
BA = "https://www.arbeitsagentur.de"
JOBS = "https://www.arbeitsagentur.de/jobsuche/"
MIIG = "https://www.make-it-in-germany.com"
ANER = "https://www.anerkennung-in-deutschland.de"

TOPICS = {
    # topic: (uk, ru)
    "anmeldung": ("Anmeldung (реєстрація місця проживання)", "Anmeldung (регистрация по месту жительства)"),
    "residence": ("Перебування і §24", "Пребывание и §24"),
    "jobcenter": ("Jobcenter і Grundsicherung", "Jobcenter и Grundsicherung"),
    "jobs": ("Пошук роботи", "Поиск работы"),
    "recognition": ("Визнання кваліфікацій", "Признание квалификаций"),
    "health": ("Медичне страхування", "Медицинское страхование"),
    "bank": ("Банківський рахунок", "Банковский счёт"),
    "housing": ("Житло", "Жильё"),
    "education": ("Освіта і мовні курси", "Образование и языковые курсы"),
    "transport": ("Транспорт і права водія", "Транспорт и водительские права"),
    "children": ("Діти і Kita", "Дети и Kita"),
    "safety": ("Обережно: шахраї", "Осторожно: мошенники"),
    "taxes": ("Податки і зарплата", "Налоги и зарплата"),
}

_LINKS = {
    "anmeldung": [(G4U, "Germany4Ukraine")],
    "residence": [("https://www.berlin.de/einwanderung/ueber-uns/aktuelles/artikel.1647418.php", "Landesamt für Einwanderung Berlin: §24 до 04.03.2027"),
                  (G4U, "Germany4Ukraine"), (BAMF, "BAMF")],
    "jobcenter": [("https://www.ladadi.de/medien/pdfs/fb-520-2-esc-kfb/buergergeld/grundsicherung-praesentation.pdf", "Kommunales Jobcenter Darmstadt-Dieburg: Grundsicherung"),
                  (BA, "Bundesagentur für Arbeit"), (G4U, "Germany4Ukraine")],
    "jobs": [(JOBS, "Jobbörse — Bundesagentur für Arbeit"), (MIIG, "Make it in Germany")],
    "recognition": [(ANER, "Anerkennung in Deutschland"), ("https://www.netzwerk-iq.de", "Netzwerk IQ")],
    "health": [(G4U, "Germany4Ukraine")],
    "bank": [(G4U, "Germany4Ukraine")],
    "housing": [(G4U, "Germany4Ukraine")],
    "education": [(BAMF, "BAMF — Integrationskurse"), (G4U, "Germany4Ukraine")],
    "transport": [("https://www.wiesbaden.de/vv/produkte/34/umschreibung-auslaendischer-fuehrerschein-ukraine", "Wiesbaden: обмін українських прав / обмен прав"),
                  (G4U, "Germany4Ukraine")],
    "children": [("https://stadt.muenchen.de/service/uk-UA/info/10470323/", "München: Kita"),
                 ("https://www.berlin.de/ba-mitte/politik-und-verwaltung/aemter/jugendamt/aktuelles/artikel.1364066.php", "Berlin-Mitte: Kita-Gutschein")],
    "safety": [("https://www.evz.de/einkaufen-internet/vorsicht-falle/mietbetrug.html", "EVZ: Mietbetrug"),
               ("https://www.verbraucherzentrale-niedersachsen.de/wissen/digitale-welt/datenschutz/vorsicht-vor-jobscamming-gefaelschte-jobangebote-gefaehrden-ihre-identitaet-120421", "Verbraucherzentrale: Jobscamming")],
    "taxes": [(MIIG, "Make it in Germany"), (G4U, "Germany4Ukraine")],
}

SEED = [
    {"topic": topic, "title_uk": title, "title_ru": title, "url": url, "checked_at": CHECKED}
    for topic, links in _LINKS.items()
    for url, title in links
]
