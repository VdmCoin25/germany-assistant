"""Import seed job chats from CSV: python scripts/import_job_chats.py path.csv

Header: username,title,city,land,language,ads_allowed. Re-running updates rows, never duplicates.
"""
import asyncio
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.database.repositories.jobs_radar import JobsRadarRepository  # noqa: E402
from app.database.session import make_engine, make_sessionmaker  # noqa: E402


async def run(path: str) -> None:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    engine = make_engine(get_settings().database_url)
    try:
        async with make_sessionmaker(engine)() as session:
            created, updated = await JobsRadarRepository(session).import_rows(rows)
            await session.commit()
    finally:
        await engine.dispose()
    print(f"created: {created}, updated: {updated}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/import_job_chats.py path.csv")
    asyncio.run(run(sys.argv[1]))
