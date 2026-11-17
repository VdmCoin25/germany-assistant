"""Housing, reference and settings against the audit server (read-only except none). python webapp/dev/shoot_sections.py <out>"""
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
TXT = {"uk": {"housing": "Житло", "ref": "Довідник", "set": "Налаштування і мої дані", "terms": "Терміни", "docs": "Документи для оренди",
              "calc": "Калькулятор", "letter": "Лист орендодавцю"},
       "ru": {"housing": "Жильё", "ref": "Справочник", "set": "Настройки и мои данные", "terms": "Термины", "docs": "Документы для аренды",
              "calc": "Калькулятор", "letter": "Письмо арендодателю"}}


async def page(b, scheme, lang, w=None, h=None):
    w, h = w or W, h or H
    ctx = await b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2)
    await ctx.route("https://telegram.org/**", lambda r: r.abort())
    await ctx.add_init_script(f"window.__TG_INIT_DATA__ = {json.dumps(make_init_data(2001, '42:TEST-TOKEN'))};"
                              f"window.__TG_USER__ = 2001; window.__TG_LANG__ = {json.dumps(lang)};")
    await ctx.add_init_script(MOCK)
    pg = await ctx.new_page()
    await pg.goto(f"{BASE}?scheme={scheme}&lang={lang}"); await pg.wait_for_timeout(900)
    return ctx, pg


async def click(pg, text):
    el = pg.get_by_text(text, exact=True).first
    # In Telegram the bottom button lives outside the web view; the mock draws it on top, so step around it.
    await pg.evaluate("() => { const b = document.getElementById('tg-bottom-bar'); if (b) b.style.visibility = 'hidden'; }")
    await el.click(force=True)
    await pg.evaluate("() => { const b = document.getElementById('tg-bottom-bar'); if (b) b.style.visibility = ''; }")
    await pg.wait_for_timeout(500)


async def snap(pg, name, full=False):
    await pg.wait_for_timeout(250); await pg.screenshot(path=str(OUT / f"{name}.png"), full_page=full)


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome")
        for scheme in ("light", "dark"):
            for lang in ("uk", "ru"):
                T, sfx = TXT[lang], f"__{W}_{scheme}_{lang}"
                ctx, pg = await page(b, scheme, lang)
                await click(pg, T["housing"]); await snap(pg, f"housing{sfx}")
                for k in ("terms", "docs", "calc"):
                    await click(pg, T[k]); await snap(pg, f"housing-{k}{sfx}")
                    await pg.goto(f"{BASE}?scheme={scheme}&lang={lang}"); await pg.wait_for_timeout(700); await click(pg, T["housing"])
                await click(pg, T["letter"]); await snap(pg, f"housing-letter{sfx}")
                inputs = pg.locator("input")
                await inputs.nth(0).fill("Olena Kovalenko"); await inputs.nth(1).fill("Hauptstraße 5, 2-Zimmer")
                await inputs.nth(3).fill("2023")
                await pg.locator("#tg-main").click(); await pg.wait_for_timeout(500); await snap(pg, f"housing-letter-made{sfx}", full=True)
                await pg.goto(f"{BASE}?scheme={scheme}&lang={lang}"); await pg.wait_for_timeout(700)
                await click(pg, T["ref"]); await snap(pg, f"reference{sfx}")
                await pg.locator("input").first.fill("Kinder"); await snap(pg, f"reference-search{sfx}")
                await pg.goto(f"{BASE}?scheme={scheme}&lang={lang}"); await pg.wait_for_timeout(700)
                await click(pg, T["set"]); await snap(pg, f"settings{sfx}", full=True)
                await ctx.close()
        await b.close()

asyncio.run(main())
