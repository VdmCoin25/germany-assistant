"""Checks Back/Next around the preview (edit from preview returns there, Back then walks the steps). Needs the audit server on :8101."""
import asyncio, json, pathlib, sys
sys.path.insert(0, ".")
from playwright.async_api import async_playwright
from tests.test_units import make_init_data
MOCK = pathlib.Path("webapp/dev/mock-telegram.js").read_text()
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome")
        ctx = await b.new_context(viewport={"width": 390, "height": 844})
        await ctx.route("https://telegram.org/**", lambda r: r.abort())
        draft = {"seeker_draft_v1": json.dumps({"position": "Водитель", "city": "Leipzig", "land": "SN", "employment": "full",
                 "german_level": "A1", "experience": "3 года", "step": 6})}
        await ctx.add_init_script(f"window.__TG_INIT_DATA__={json.dumps(make_init_data(7201,'42:TEST-TOKEN'))};window.__TG_USER__=7201;window.__TG_CLOUD__={json.dumps(draft)};")
        await ctx.add_init_script(MOCK + ";window.__backs=[];const B=window.Telegram.WebApp.BackButton;B.onClick=f=>window.__backs.push(f);B.offClick=f=>{window.__backs=window.__backs.filter(x=>x!==f)};")
        pg = await ctx.new_page(); await pg.goto("http://127.0.0.1:8101/app-v2/?lang=ru"); await pg.wait_for_timeout(800)
        q = lambda: pg.locator("h2.q").first.inner_text()
        back = lambda: pg.evaluate("window.__backs.at(-1)()")
        await pg.locator("#tg-main").click(); await pg.wait_for_timeout(300); print("restored:", await q())
        await pg.locator("#tg-secondary").click(); await pg.wait_for_timeout(200); print("skip ->", await q())
        await pg.get_by_text("Город", exact=True).click(force=True); await pg.wait_for_timeout(200); print("edit city ->", await q())
        await pg.locator("#tg-main").click(); await pg.wait_for_timeout(200); print("next ->", await q())
        await back(); await pg.wait_for_timeout(200); print("back ->", await q())
        await back(); await pg.wait_for_timeout(200); print("back ->", await q())
        await b.close()
asyncio.run(main())
