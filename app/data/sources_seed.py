"""Initial catalog of official sources.

Only official / public-sector sites. `checked_at` = date the link was confirmed
reachable, not a legal review of the content. Admins update entries in the DB.
"""
from datetime import datetime, timezone

CHECKED = datetime(2026, 11, 16, tzinfo=timezone.utc)

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
    "jobcenter": ("Jobcenter і Bürgergeld", "Jobcenter и Bürgergeld"),
    "jobs": ("Пошук роботи", "Поиск работы"),
    "recognition": ("Визнання кваліфікацій", "Признание квалификаций"),
    "health": ("Медичне страхування", "Медицинское страхование"),
    "bank": ("Банківський рахунок", "Банковский счёт"),
    "housing": ("Житло", "Жильё"),
    "education": ("Освіта і мовні курси", "Образование и языковые курсы"),
    "transport": ("Транспорт", "Транспорт"),
    "taxes": ("Податки і зарплата", "Налоги и зарплата"),
}

_LINKS = {
    "anmeldung": [(G4U, "Germany4Ukraine")],
    "residence": [(G4U, "Germany4Ukraine"), (BAMF, "BAMF")],
    "jobcenter": [(BA, "Bundesagentur für Arbeit"), (G4U, "Germany4Ukraine")],
    "jobs": [(JOBS, "Jobbörse — Bundesagentur für Arbeit"), (MIIG, "Make it in Germany")],
    "recognition": [(ANER, "Anerkennung in Deutschland")],
    "health": [(G4U, "Germany4Ukraine")],
    "bank": [(G4U, "Germany4Ukraine")],
    "housing": [(G4U, "Germany4Ukraine")],
    "education": [(BAMF, "BAMF — Integrationskurse"), (G4U, "Germany4Ukraine")],
    "transport": [(G4U, "Germany4Ukraine")],
    "taxes": [(MIIG, "Make it in Germany"), (G4U, "Germany4Ukraine")],
}

SEED = [
    {"topic": topic, "title_uk": title, "title_ru": title, "url": url, "checked_at": CHECKED}
    for topic, links in _LINKS.items()
    for url, title in links
]
