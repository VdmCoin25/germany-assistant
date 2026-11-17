"""Live-data screenshots of the new Mini App against the audit server (test token only).

    python webapp/dev/shoot_live.py <out_dir> [only_prefix]

Needs scripts/ui_audit/serve.py ... filled on :8101 (it also serves webapp/dist at /app-v2).
Users: 5001 new, 2002 in review, 2003 rejected, 2004 published, 2001 offer waiting, 2005 contact passed.
"""
import asyncio, json, pathlib, sys
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.test_units import make_init_data  # noqa: E402

BASE = "http://127.0.0.1:8101/app-v2/"
TOKEN = "42:TEST-TOKEN"
MOCK = (pathlib.Path(__file__).parent / "mock-telegram.js").read_text()
OUT = pathlib.Path(sys.argv[1]); ONLY = sys.argv[2] if len(sys.argv) > 2 else ""
USERS = {"new": 5001, "review": 2002, "rejected": 2003, "published": 2004, "offers": 2001, "contact": 2005, "paused": 2006}
SPECIAL = ("loading", "error", "expired", "offline", "outside")


async def shot(b, name, uid, w, h, scheme, lang, special=None):
    ctx = await b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2)
    await ctx.route("https://telegram.org/**", lambda r: r.abort())
    init = "" if special == "outside" else make_init_data(uid, TOKEN)
    await ctx.add_init_script(f"window.__TG_INIT_DATA__ = {json.dumps(init)}; window.__TG_USER__ = {uid}; window.__TG_LANG__ = {json.dumps(lang)};")
    await ctx.add_init_script(MOCK)
    if special == "loading":
        async def hang(route, request=None): await asyncio.sleep(30)
        await ctx.route("**/api/**", hang)
    if special == "error":
        await ctx.route("**/api/**", lambda r: r.fulfill(status=500, body="{}"))
    if special == "expired":
        await ctx.route("**/api/**", lambda r: r.fulfill(status=401, body='{"detail":"init data expired"}'))
    pg = await ctx.new_page()
    await pg.goto(f"{BASE}?scheme={scheme}&lang={lang}")
    if special == "offline":
        await ctx.set_offline(True); await pg.evaluate("dispatchEvent(new Event('offline'))")
    await pg.wait_for_timeout(1500)
    await pg.screenshot(path=str(OUT / f"{name}__{w}_{scheme}_{lang}.png"))
    await ctx.close()


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome")
        for scheme in ("light", "dark"):
            for lang in ("uk", "ru"):
                for w, h in ((390, 844), (360, 740)):
                    for state, uid in USERS.items():
                        if f"home-{state}".startswith(ONLY):
                            await shot(b, f"home-{state}", uid, w, h, scheme, lang)
                    for sp in SPECIAL:
                        if f"home-{sp}".startswith(ONLY):
                            await shot(b, f"home-{sp}", 2001, w, h, scheme, lang, sp)
        await b.close()

asyncio.run(main())
