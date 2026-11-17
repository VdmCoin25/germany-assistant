import { Cell, List, Section } from "@telegram-apps/telegram-ui";
import { RouteCell } from "../components/RouteCell";
import { useCallback } from "react";
import { Board, type Scene } from "../components/Board";
import { Route } from "../components/Route";
import type { T } from "../i18n";
import { CITIES, LANDS } from "../form/cities";
import { useBottomButton } from "../tg";

export type JobsState =
  | { step: "new" }
  | { step: "draft"; at: number }
  | { step: "rejected" }
  | { step: "review" }
  | { step: "published" }
  | { step: "paused" }
  | { step: "offers"; waiting: number }
  | { step: "contact" };

export type HomeData = { city: string | null; land?: string | null; position: string | null; updated: string | null; jobs: JobsState };

/** The board shows a real place: a known German city (canonical spelling), else the Land, else nothing.
 *  Free text typed at /start ("Ччч", "berlin ") never ends up on the sign. */
export function placeName(city: string | null, land?: string | null): string | null {
  const c = city?.trim().toLowerCase();
  const known = c ? CITIES.find(([name]) => name.toLowerCase() === c) : undefined;
  if (known) return known[0];
  // smaller places typed in the form: German place names are written in Latin letters
  const typed = city?.trim() ?? "";
  if (/^[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß .()\-]{2,}$/.test(typed)) return typed;
  return land && LANDS[land] ? LANDS[land] : null;
}

/** Derives every part of the board from the user's job route, so nothing on it is decoration. */
export function routeOf(j: JobsState) {
  switch (j.step) {
    case "draft": return { idx: 0, status: "boarding", action: true, scene: { rain: false, train: "passing", lamp: "signal" } };
    case "new": return { idx: 0, status: "boarding", action: true, scene: { rain: false, train: "passing", lamp: "signal" } };
    case "rejected": return { idx: 0, status: "boarding", action: true, scene: { rain: false, train: "passing", lamp: "signal" } };
    case "review": return { idx: 1, status: "enroute", action: false, scene: { rain: true, train: "passing", lamp: "dim" } };
    case "paused": return { idx: 2, status: "enroute", action: false, scene: { rain: false, train: "passing", lamp: "dim" } };
    case "published": return { idx: 2, status: "enroute", action: false, scene: { rain: true, train: "passing", lamp: "dim" } };
    case "offers": return { idx: 3, status: "boarding", action: true, scene: { rain: false, train: "standing", lamp: "signal" } };
    case "contact": return { idx: 4, status: "arrived", action: false, scene: { rain: false, train: "standing", lamp: "dim" } };
  }
}

type Props = { t: T; data: HomeData; go: (s: string) => void };

export function Home({ t, data, go }: Props) {
  const r = routeOf(data.jobs) as { idx: number; status: "boarding" | "enroute" | "arrived"; action: boolean; scene: Scene };
  const jobsLine =
    data.jobs.step === "new" ? t("jobs.new")
    : data.jobs.step === "draft" ? t("jobs.draft", { n: data.jobs.at })
    : data.jobs.step === "rejected" ? t("jobs.rejected")
    : data.jobs.step === "review" ? t("jobs.review")
    : data.jobs.step === "published" ? t("jobs.published")
    : data.jobs.step === "paused" ? t("jobs.paused")
    : data.jobs.step === "offers" ? t.n("jobs.offers", data.jobs.waiting)
    : t("route.contact");
  const statusText = t(`status.${r.status}` as const);

  // Always one clear next step: there is no state without a bottom button.
  const step = data.jobs.step;
  const primary =
    step === "new" ? t("btn.fillProfile")
    : step === "draft" ? t("btn.continueForm")
    : step === "rejected" ? t("btn.fixProfile")
    : step === "offers" ? t("btn.answerOffer")
    : step === "contact" ? t("btn.seeOffers")
    : t("hub.myProfile");
  const onPrimary = useCallback(() => go(["new", "draft", "rejected"].includes(step) ? "form" : "offers"), [go, step]);
  const openJobs = useCallback(() => go("offers"), [go]);
  useBottomButton(primary, onPrimary);

  return (
    <>
      <Board
        scene={r.scene}
        caption={t("board.yours")}
        meta={data.updated ? t("board.updated", { time: data.updated }) : undefined}
        station={placeName(data.city, data.land) ?? t("board.noCity")}
        sub={data.position ?? t("board.noCityHint")}
      />
      <List>
        <Section>
          <RouteCell title={t("jobs.title")} explain={jobsLine} status={r.status} statusText={statusText} onClick={openJobs} />
          <Route t={t} current={r.idx} action={r.action} size="platforms" />
        </Section>
        {data.jobs.step === "new" && <p className="hint">{t("jobs.privacy")}</p>}
        <Section header={t("help.title")}>
          <Cell subtitle={t("housing.sub")} onClick={() => go("housing")}>{t("housing.title")}</Cell>
          <Cell subtitle={t("reference.sub")} onClick={() => go("reference")}>{t("reference.title")}</Cell>
        </Section>
        <p className="quiet">{t("soon")}</p>
        <Section>
          <Cell onClick={() => go("settings")}>{t("home.settings")}</Cell>
        </Section>
      </List>
    </>
  );
}
