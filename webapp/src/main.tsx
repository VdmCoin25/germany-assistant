import "@telegram-apps/telegram-ui/dist/styles.css";
import "./styles.css";
import { AppRoot } from "@telegram-apps/telegram-ui";
import { useCallback, useState } from "react";
import { createRoot } from "react-dom/client";
import { makeT, type Lang } from "./i18n";
import { FormCity } from "./screens/FormCity";
import { Home, type HomeData, type JobsState } from "./screens/Home";
import { tg, useColorScheme } from "./tg";

// J2 prototype: data comes from ?demo=… presets; the API is wired in J4.
const params = new URLSearchParams(location.search);
const look = (params.get("look") === "b" ? "b" : "a") as "a" | "b";
const lang: Lang = (params.get("lang") ?? tg?.initDataUnsafe.user?.language_code) === "ru" ? "ru" : "uk";
const demo = params.get("demo") ?? "offers";

const PRESETS: Record<string, HomeData> = {
  new: { city: null, position: null, updated: null, jobs: { step: "new" } },
  review: { city: "Berlin", position: lang === "ru" ? "Повар / помощник повара" : "Кухар / помічник кухаря", updated: "21:01", jobs: { step: "review" } },
  offers: { city: "Berlin", position: lang === "ru" ? "Повар / помощник повара" : "Кухар / помічник кухаря", updated: "21:01", jobs: { step: "offers", waiting: 2 } as JobsState },
};

function App() {
  const scheme = useColorScheme();
  const t = makeT(lang);
  const [screen, setScreen] = useState(params.get("screen") ?? "home");
  const go = useCallback((s: string) => setScreen(s), []);
  const back = useCallback(() => setScreen("home"), []);
  return (
    <AppRoot appearance={scheme}>
      <div className={`app look-${look}`} data-scheme={scheme}>
        {screen === "form"
          ? <FormCity t={t} look={look} step={2} total={6} initial={params.get("q") ?? ""} back={back} next={back} />
          : <Home t={t} look={look} data={PRESETS[demo] ?? PRESETS.offers} go={go} />}
      </div>
    </AppRoot>
  );
}

tg?.ready(); tg?.expand();
createRoot(document.getElementById("root")!).render(<App />);
