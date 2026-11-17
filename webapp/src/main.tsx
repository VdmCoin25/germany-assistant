import "@telegram-apps/telegram-ui/dist/styles.css";
import "./styles.css";
import { AppRoot } from "@telegram-apps/telegram-ui";
import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { HomeSkeleton, LoadError, OfflineNote, OutsideTelegram } from "./components/States";
import { useHomeData, useOnline } from "./data";
import { makeT, type Lang } from "./i18n";
import { Form } from "./form/Form";
import { FormCity } from "./screens/FormCity";
import { Home, type HomeData } from "./screens/Home";
import { Offers } from "./screens/Offers";
import { tg, useColorScheme, useSettingsButton } from "./tg";

// Secondary sections load on first open: the home screen and the job route stay in the first download.
const HousingScreen = lazy(() => import("./screens/Housing").then((m) => ({ default: m.HousingScreen })));
const Reference = lazy(() => import("./screens/Reference").then((m) => ({ default: m.Reference })));
const Settings = lazy(() => import("./screens/Settings").then((m) => ({ default: m.Settings })));
const Kit = lazy(() => import("./screens/Kit").then((m) => ({ default: m.Kit })));   // review page, not in the main bundle

const BOT = "ukraineingermany_bot";
const params = new URLSearchParams(location.search);
const pickLang = (...c: (string | null | undefined)[]): Lang => (c.find(Boolean) === "ru" ? "ru" : "uk");


/** Design review only: ?demo=new|review|offers or ?screen=kit|form render fixed data. */
function Demo() {
  const lang = pickLang(params.get("lang"));
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  const t = makeT(lang);
  const pos = lang === "ru" ? "Повар / помощник повара" : "Кухар / помічник кухаря";
  const presets: Record<string, HomeData> = {
    new: { city: null, position: null, updated: null, jobs: { step: "new" } },
    review: { city: "Berlin", position: pos, updated: "21:01", jobs: { step: "review" } },
    offers: { city: "Berlin", position: pos, updated: "21:01", jobs: { step: "offers", waiting: 2 } },
  };
  const back = useCallback(() => history.back(), []);
  const screen = params.get("screen");
  if (screen === "kit") return <Suspense fallback={null}><Kit t={t} /></Suspense>;
  if (screen === "form") return <FormCity t={t} step={2} total={6} initial={params.get("q") ?? ""} back={back} next={back} />;
  return <Home t={t} data={presets[params.get("demo") ?? "offers"] ?? presets.offers} go={() => {}} />;
}

/** Real data from our API, signed with Telegram initData. */
function Live() {
  const online = useOnline();
  const { res, reload } = useHomeData();
  type Screen = "home" | "form" | "offers" | "housing" | "reference" | "settings";
  const [screen, setScreen] = useState<Screen>("home");
  const go = useCallback((s: string) => { setScreen(s as Screen); window.scrollTo(0, 0); }, []);
  const openSettings = useCallback(() => go("settings"), [go]);
  useSettingsButton(screen === "home" ? openSettings : null);   // not mid-form: opening Settings there would drop the answers
  const toHome = useCallback(() => { setScreen("home"); reload(); window.scrollTo(0, 0); }, [reload]);
  const toForm = useCallback(() => { setScreen("form"); window.scrollTo(0, 0); }, []);
  const sent = useCallback(() => { setScreen("home"); reload(); }, [reload]);
  const [langSet, setLangSet] = useState<string | null>(null);   // changed in Settings, before the next reload
  const lang = pickLang(params.get("lang"), langSet, res.state === "ok" ? res.data.language : null, tg?.initDataUnsafe.user?.language_code);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  const t = makeT(lang);
  return (
    <>
      {!online && <OfflineNote t={t} />}
      {res.state === "loading" && <HomeSkeleton t={t} />}
      {res.state === "error" && <LoadError t={t} status={res.status} retry={reload} />}
      {res.state === "ok" && screen === "home" && <Home t={t} data={res.data} go={go} />}
      {res.state === "ok" && screen === "form" && <Form t={t} existing={res.data.seed} exit={toHome} done={sent} />}
      {res.state === "ok" && screen === "offers" && <Offers t={t} exit={toHome} editProfile={toForm} />}
      <Suspense fallback={<HomeSkeleton t={t} />}>
        {res.state === "ok" && screen === "housing" && <HousingScreen t={t} lang={lang} city={res.data.city} level={res.data.seed.german_level ?? null} exit={toHome} />}
        {res.state === "ok" && screen === "reference" && <Reference t={t} lang={lang} exit={toHome} />}
        {res.state === "ok" && screen === "settings" && <Settings t={t} exit={toHome} onLanguage={setLangSet} />}
      </Suspense>
    </>
  );
}

function App() {
  const scheme = useColorScheme();
  const demo = params.has("demo") || params.has("screen");
  const outside = !demo && !tg?.initData;
  return (
    <AppRoot appearance={scheme}>
      <main className="app" data-scheme={scheme}>
        {demo ? <Demo /> : outside ? <OutsideTelegram t={makeT(pickLang(navigator.language.slice(0, 2)))} bot={BOT} /> : <Live />}
      </main>
    </AppRoot>
  );
}

tg?.ready(); tg?.expand();
createRoot(document.getElementById("root")!).render(<App />);
