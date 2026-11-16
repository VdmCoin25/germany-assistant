"""Screenshot every Mini App screen and state with a mocked Telegram.WebApp (test token only).

    python scripts/ui_audit/shoot.py <out_dir>

Needs two servers from serve.py: filled data on :8101, empty data on :8102.
Matrix: sizes 390x844 and 360x740, Telegram theme light/dark, language uk/ru,
states filled / empty / loading / error.
"""
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.test_units import make_init_data  # noqa: E402

TEST_TOKEN = "42:TEST-TOKEN"
FILLED, EMPTY = "http://127.0.0.1:8101/", "http://127.0.0.1:8102/"
SIZES = {"390": (390, 844), "360": (360, 740)}
THEMES = ("light", "dark")
LANGS = ("uk", "ru")

# screen id -> (server, telegram user id, js to run after load)
SCREENS = {
    "home-filled": (FILLED, 2001, "show('home')"),
    "home-empty": (EMPTY, 5001, "show('home')"),
    "jobs-filled": (FILLED, 2001, "JOBS.sub=null;renderJobs();show('jobs')"),
    "jobs-vacancy-open": (FILLED, 2001, "JOBS.openVac=JOBS.vacancies[0]&&JOBS.vacancies[0].id;JOBS.applyFor=JOBS.openVac;renderJobs();show('jobs');setTimeout(()=>document.querySelector('.vac.open')?.scrollIntoView(),30)"),
    "jobs-empty": (EMPTY, 5001, "renderJobs();show('jobs')"),
    "jobs-form-filled": (FILLED, 2001, "JOBS.sub='form';renderJobs();show('jobs')"),
    "jobs-form-empty": (EMPTY, 5001, "JOBS.sub='form';renderJobs();show('jobs')"),
    "jobs-inbox-filled": (FILLED, 2001, "JOBS.sub='inbox';renderJobs();show('jobs')"),
    "jobs-inbox-empty": (EMPTY, 5001, "JOBS.sub='inbox';renderJobs();show('jobs')"),
    "employer-filled": (FILLED, 3001, "JOBS.view='employer';renderJobs();show('jobs')"),
    "employer-empty": (EMPTY, 5001, "JOBS.view='employer';renderJobs();show('jobs')"),
    "housing-terms": (FILLED, 2001, "HOUSING.tab='terms';renderHousing();show('housing')"),
    "housing-docs": (FILLED, 2001, "HOUSING.tab='docs';renderHousing();show('housing')"),
    "housing-calc": (FILLED, 2001, "HOUSING.tab='calc';renderHousing();show('housing')"),
    "housing-letter": (FILLED, 2001, "HOUSING.tab='letter';renderHousing();show('housing')"),
    "profile-filled": (FILLED, 2001, "show('profile')"),
    "profile-empty": (EMPTY, 5001, "show('profile')"),
    "info": (FILLED, 2001, "show('info');document.querySelector('#page-info details')&&(document.querySelector('#page-info details').open=true)"),
    "privacy": (FILLED, 2001, "show('privacy')"),
}
# states produced by intercepting the API
NETWORK_STATES = {"loading": "hang", "error": "fail"}
NETWORK_SCREENS = ("home-filled", "jobs-filled", "housing-terms", "info")

MOCK = """
(() => {
  const theme = %(theme)s;
  const params = theme === 'dark'
    ? {bg_color:'#17212b', text_color:'#f5f5f5', hint_color:'#708499', button_color:'#5288c1', secondary_bg_color:'#232e3c'}
    : {bg_color:'#ffffff', text_color:'#000000', hint_color:'#999999', button_color:'#2481cc', secondary_bg_color:'#f1f1f1'};
  window.Telegram = { WebApp: {
    initData: %(init)s, initDataUnsafe: { user: { id: %(uid)s, first_name: 'Test', language_code: %(lang)s } },
    colorScheme: theme, themeParams: params, viewportHeight: innerHeight, viewportStableHeight: innerHeight,
    ready(){}, expand(){}, close(){}, onEvent(){}, offEvent(){}, openLink(){}, showConfirm(m, cb){ cb(false); },
    setHeaderColor(){}, setBackgroundColor(){}, setBottomBarColor(){},
    HapticFeedback: { selectionChanged(){}, notificationOccurred(){}, impactOccurred(){} },
    BackButton: { show(){}, hide(){}, onClick(){}, offClick(){} },
  }};
})();
"""


async def shoot(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        jobs = []
        for sid, (base, uid, js) in SCREENS.items():
            for state in ["data"] + ([*NETWORK_STATES] if sid in NETWORK_SCREENS else []):
                jobs.append((sid, base, uid, js, state))
        for sid, base, uid, js, state in jobs:
            for size, (w, h) in SIZES.items():
                for theme in THEMES:
                    for lang in LANGS:
                        ctx = await browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1,
                                                        color_scheme=theme, reduced_motion="reduce")
                        await ctx.route("https://telegram.org/**", lambda r: r.abort())
                        init = make_init_data(uid, token=TEST_TOKEN)
                        await ctx.add_init_script(MOCK % {"theme": json.dumps(theme), "init": json.dumps(init),
                                                          "uid": uid, "lang": json.dumps(lang)})

                        def make_patch(lang):
                            async def patch_me(route, request=None):
                                resp = await route.fetch()
                                data = await resp.json()
                                if isinstance(data, dict) and "language" in data:
                                    data["language"] = lang
                                await route.fulfill(response=resp, json=data)
                            return patch_me
                        await ctx.route("**/api/me", make_patch(lang))
                        if state == "loading":
                            async def hang(route, request=None):
                                await asyncio.sleep(30)
                            await ctx.route("**/api/**", hang)
                        if state == "error":
                            await ctx.route("**/api/**", lambda r: r.fulfill(status=500, body="{}"))
                        page = await ctx.new_page()
                        await page.goto(base, wait_until="domcontentloaded")
                        await page.wait_for_timeout(700 if state != "data" else 1500)
                        if state == "data":
                            await page.evaluate(js)
                            await page.wait_for_timeout(300)
                        name = f"{sid}{'' if state == 'data' else '-' + state}__{size}_{theme}_{lang}.png"
                        await page.screenshot(path=str(out / name))
                        await ctx.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(shoot(Path(sys.argv[1])))
