"""Offers flow against the audit server (fresh DB!): list -> offer -> consent -> done, plus empty/answered lists.

    python webapp/dev/shoot_offers.py <out_dir>
"""
import asyncio, json, pathlib, sys
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.test_units import make_init_data  # noqa: E402

BASE = "http://127.0.0.1:8101/app-v2/"
MOCK = (pathlib.Path(__file__).parent / "mock-telegram.js").read_text()
OUT = pathlib.Path(sys.argv[1])
import os
W, H = (360, 740) if os.environ.get("NARROW") else (390, 844)


async def page(b, uid, scheme, lang, w=None, h=None):
    w, h = w or W, h or H
    ctx = await b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2)
    await ctx.route("https://telegram.org/**", lambda r: r.abort())
    await ctx.add_init_script(f"window.__TG_INIT_DATA__ = {json.dumps(make_init_data(uid, '42:TEST-TOKEN'))};"
                              f"window.__TG_USER__ = {uid}; window.__TG_LANG__ = {json.dumps(lang)};")
    await ctx.add_init_script(MOCK)
    pg = await ctx.new_page()
    await pg.goto(f"{BASE}?scheme={scheme}&lang={lang}")
    await pg.wait_for_timeout(900)
    return ctx, pg


async def snap(pg, name):
    await pg.wait_for_timeout(300)
    await pg.screenshot(path=str(OUT / f"{name}.png"))


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome")
        # read-only views for every theme/language (no answer is sent)
        for scheme in ("light", "dark"):
            for lang in ("uk", "ru"):
                sfx = f"__{W}_{scheme}_{lang}"
                ctx, pg = await page(b, 2001, scheme, lang)
                await pg.locator("#tg-main").click()
                await snap(pg, f"offers-list{sfx}")
                await pg.locator("#tg-main").click(); await snap(pg, f"offer-card{sfx}")
                await pg.locator("#tg-main").click(); await snap(pg, f"offer-consent{sfx}")
                await ctx.close()
                for uid, name in ((2004, "offers-empty"), (2002, "offers-review"), (2005, "offers-answered")):
                    ctx, pg = await page(b, uid, scheme, lang)
                    await pg.locator("#tg-main").click() if uid == 2004 or uid == 2005 else await pg.get_by_text("Робота" if lang == "uk" else "Работа", exact=True).first.click(force=True)
                    await snap(pg, f"{name}{sfx}"); await ctx.close()
        # the one write: accept the offer (user 2001), then the done screen and the answered card
        ctx, pg = await page(b, 2001, "light", "ru")
        for _ in range(4):   # home -> list -> offer -> consent -> agree
            await pg.locator("#tg-main").click(); await pg.wait_for_timeout(400)
        await pg.wait_for_timeout(800); await snap(pg, f"offer-done__{W}_light_ru")
        await ctx.close()
        await b.close()

asyncio.run(main())
