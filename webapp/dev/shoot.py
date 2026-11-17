"""Screenshots of the Mini App with a mocked Telegram. Usage: python dev/shoot.py <base_url> <out_dir> [shots]"""
import asyncio, pathlib, sys
from playwright.async_api import async_playwright

BASE, OUT = sys.argv[1], pathlib.Path(sys.argv[2])
MOCK = (pathlib.Path(__file__).parent / "mock-telegram.js").read_text()
LOW_UA = "Mozilla/5.0 (Linux; Android 11) Telegram-Android/11.4.2 (Samsung SM-A125F; Android 11; SDK 30; LOW)"
SHOTS = {
    "home-offers": "demo=offers", "home-new": "demo=new", "home-review": "demo=review",
    "form-city": "screen=form&q=Ber",
}

async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome")
        for look in ("a", "b"):
            for scheme in ("light", "dark"):
                for lang in ("uk", "ru"):
                    for w, h in ((390, 844), (360, 740)):
                        for name, q in SHOTS.items():
                            ctx = await b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2)
                            await ctx.route("https://telegram.org/**", lambda r: r.abort())
                            await ctx.add_init_script(MOCK)
                            pg = await ctx.new_page()
                            await pg.goto(f"{BASE}?look={look}&scheme={scheme}&lang={lang}&{q}")
                            await pg.wait_for_timeout(1600)
                            await pg.screenshot(path=str(OUT / f"{look}-{name}__{w}_{scheme}_{lang}.png"))
                            await ctx.close()
        # weak device and reduced motion: the scene must be a still frame of the same state
        for look in ("a", "b"):
            ctx = await b.new_context(viewport={"width": 360, "height": 740}, user_agent=LOW_UA, reduced_motion="reduce")
            await ctx.route("https://telegram.org/**", lambda r: r.abort())
            await ctx.add_init_script(MOCK)
            pg = await ctx.new_page()
            await pg.goto(f"{BASE}?look={look}&scheme=light&lang=ru&demo=offers")
            await pg.wait_for_timeout(600)
            await pg.screenshot(path=str(OUT / f"{look}-home-offers__360_light_ru_lowend.png"))
            await ctx.close()
        await b.close()

asyncio.run(main())
