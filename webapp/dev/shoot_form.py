"""Walk through the profile form against the audit server and screenshot every step (test token only).

    python webapp/dev/shoot_form.py <out_dir>
"""
import asyncio, json, pathlib, sys
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.test_units import make_init_data  # noqa: E402

BASE = "http://127.0.0.1:8101/app-v2/"
MOCK = (pathlib.Path(__file__).parent / "mock-telegram.js").read_text()
OUT = pathlib.Path(sys.argv[1])


async def page(b, uid, scheme, lang, w=390, h=844, cloud=None, limit=False):
    ctx = await b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2)
    await ctx.route("https://telegram.org/**", lambda r: r.abort())
    await ctx.add_init_script(f"window.__TG_INIT_DATA__ = {json.dumps(make_init_data(uid, '42:TEST-TOKEN'))};"
                              f"window.__TG_USER__ = {uid}; window.__TG_LANG__ = {json.dumps(lang)};"
                              f"window.__TG_CLOUD__ = {json.dumps(cloud or {})};")
    await ctx.add_init_script(MOCK)
    if limit:
        await ctx.route("**/api/jobs/seeker", lambda r: r.fulfill(status=429, body='{"detail":"submit_limit:37"}')
                        if r.request.method == "PUT" else r.continue_())
    pg = await ctx.new_page()
    await pg.goto(f"{BASE}?scheme={scheme}&lang={lang}")
    await pg.wait_for_timeout(900)
    return ctx, pg


async def snap(pg, name):
    await pg.wait_for_timeout(250)
    await pg.screenshot(path=str(OUT / f"{name}.png"))


async def walk(b, scheme, lang, uid):
    sfx = f"__390_{scheme}_{lang}"
    ctx, pg = await page(b, uid, scheme, lang)
    main = pg.locator("#tg-main")
    await main.click(); await snap(pg, f"form-1-empty{sfx}")
    await pg.locator("input").first.fill("Кухар" if lang == "uk" else "Повар"); await snap(pg, f"form-1{sfx}")
    await main.click()
    inp = pg.locator("input").first
    await inp.fill(""); await inp.type("Mün"); await snap(pg, f"form-2-suggest{sfx}")
    await pg.get_by_role("option").first.click(); await snap(pg, f"form-2{sfx}")
    await main.click(); await pg.get_by_role("radio").nth(2).click(); await snap(pg, f"form-3{sfx}")
    await main.click(); await snap(pg, f"form-4-empty{sfx}"); await pg.get_by_role("radio").nth(2).click(); await snap(pg, f"form-4{sfx}")
    await main.click(); await pg.locator("textarea").fill("5 років кухарем у ресторані в Києві. Гарячий цех." if lang == "uk"
                                                          else "5 лет поваром в ресторане в Киеве. Горячий цех."); await snap(pg, f"form-5{sfx}")
    await main.click(); await snap(pg, f"form-6{sfx}")
    await pg.locator("#tg-secondary").click(); await snap(pg, f"form-preview{sfx}")
    await main.click(); await pg.wait_for_timeout(600); await snap(pg, f"form-sent{sfx}")
    await ctx.close()


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome")
        uid = 7001
        for scheme in ("light", "dark"):
            for lang in ("uk", "ru"):
                await walk(b, scheme, lang, uid); uid += 1
        # other city -> Land choice
        ctx, pg = await page(b, 7101, "light", "ru")
        await pg.locator("#tg-main").click(); await pg.locator("input").first.fill("Склад"); await pg.locator("#tg-main").click()
        inp = pg.locator("input").first; await inp.fill(""); await inp.type("Lauf an der Pegnitz")
        await snap(pg, "form-2-other__390_light_ru")
        await pg.get_by_role("option").last.click(); await snap(pg, "form-2-land__390_light_ru"); await ctx.close()
        # draft restored at step 5
        draft = {"seeker_draft_v1": json.dumps({"position": "Водій", "city": "Leipzig", "land": "SN", "employment": "full",
                                                "shifts_ok": True, "german_level": "A1", "experience": "", "about": "", "step": 5})}
        ctx, pg = await page(b, 7102, "dark", "uk", cloud=draft)
        await pg.locator("#tg-main").click(); await snap(pg, "form-draft-restored__390_dark_uk"); await ctx.close()
        # submission limit reached
        ctx, pg = await page(b, 7103, "light", "ru", limit=True,
                             cloud={"seeker_draft_v1": json.dumps({"position": "Водитель", "city": "Leipzig", "land": "SN",
                                    "employment": "full", "german_level": "A1", "experience": "3 года", "step": 6})})
        await pg.locator("#tg-main").click(); await pg.locator("#tg-secondary").click(); await pg.locator("#tg-main").click()
        await pg.wait_for_timeout(500); await snap(pg, "form-error-limit__390_light_ru"); await ctx.close()
        # existing profile opens in edit mode (user 2003: rejected)
        ctx, pg = await page(b, 2003, "light", "uk")
        await pg.locator("#tg-main").click(); await snap(pg, "form-1-edit-rejected__390_light_uk"); await ctx.close()
        # narrow screen
        ctx, pg = await page(b, 7104, "light", "ru", 360, 740)
        await pg.locator("#tg-main").click(); await pg.locator("input").first.fill("Уборка"); await pg.locator("#tg-main").click()
        await pg.locator("#tg-main").click(); await snap(pg, "form-3__360_light_ru"); await ctx.close()
        await b.close()

asyncio.run(main())
