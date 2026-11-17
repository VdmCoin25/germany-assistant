"""axe-core over every v2 screen (light/dark) against the audit server with a fresh DB.

    python webapp/dev/qa_axe.py <path to axe.min.js> <out.json>
"""
import asyncio, json, pathlib, sys
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.test_units import make_init_data  # noqa: E402

BASE = "http://127.0.0.1:8101/app-v2/"
MOCK = (pathlib.Path(__file__).parent / "mock-telegram.js").read_text()
AXE = pathlib.Path(sys.argv[1]).read_text()
OUT = pathlib.Path(sys.argv[2])
M = "#tg-main"

# name -> (user, steps); a step is ("main",) | ("text", "...") | ("fill", n, "...")
FLOWS = {
    "home-new": (5001, []), "home-review": (2002, []), "home-offers": (2001, []), "home-contact": (2005, []),
    "form-1": (5002, [("main",)]), "form-2": (5003, [("main",), ("fill", 0, "Повар"), ("main",), ("fill", 0, "Mün")]),
    "form-3": (5004, [("main",), ("fill", 0, "Повар"), ("main",), ("fill", 0, "Berlin"), ("text", "Berlin"), ("main",)]),
    "offers-list": (2001, [("main",)]), "offer-card": (2001, [("main",), ("main",)]),
    "offer-consent": (2001, [("main",), ("main",), ("main",)]),
    "housing": (2001, [("text", "Жильё")]), "housing-calc": (2001, [("text", "Жильё"), ("text", "Калькулятор")]),
    "housing-letter": (2001, [("text", "Жильё"), ("text", "Письмо арендодателю")]),
    "reference": (2001, [("text", "Справочник")]), "settings": (2001, [("text", "Настройки и мои данные")]),
}


async def main():
    report = {}
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome")
        for scheme in ("light", "dark"):
            for name, (uid, steps) in FLOWS.items():
                ctx = await b.new_context(viewport={"width": 390, "height": 844})
                await ctx.route("https://telegram.org/**", lambda r: r.abort())
                await ctx.add_init_script(f"window.__TG_INIT_DATA__={json.dumps(make_init_data(uid, '42:TEST-TOKEN'))};"
                                          f"window.__TG_USER__={uid};window.__TG_LANG__='ru';")
                await ctx.add_init_script(MOCK)
                pg = await ctx.new_page()
                await pg.goto(f"{BASE}?scheme={scheme}&lang=ru"); await pg.wait_for_timeout(900)
                for s in steps:
                    if s[0] == "main": await pg.locator(M).click()
                    elif s[0] == "text": await pg.get_by_text(s[1], exact=True).first.click(force=True)
                    else: await pg.locator("input").nth(s[1]).fill(s[2])
                    await pg.wait_for_timeout(450)
                await pg.add_script_tag(content=AXE)
                res = await pg.evaluate("""async () => { const r = await axe.run({ exclude: [['#tg-bottom-bar']] }, { runOnly: ['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice'] });
                    return r.violations.map(v => ({id: v.id, impact: v.impact, help: v.help, n: v.nodes.length,
                      targets: v.nodes.slice(0,3).map(x => x.target.join(' '))})); }""")
                report[f"{name}:{scheme}"] = res
                await ctx.close()
        await b.close()
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    agg = {}
    for k, vs in report.items():
        for v in vs:
            a = agg.setdefault((v["id"], v["impact"]), [v["help"], 0, []]); a[1] += v["n"]; a[2].append(k)
    for (i, imp), (h, n, where) in sorted(agg.items(), key=lambda x: str(x[0][1])):
        print(f"{imp:9} {i:28} nodes={n:3} screens={len(where)}  {h}  e.g. {where[:3]}")
    print("screens checked:", len(report))

asyncio.run(main())
