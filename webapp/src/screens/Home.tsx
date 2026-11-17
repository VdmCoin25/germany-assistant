import { Cell, List, Section } from "@telegram-apps/telegram-ui";
import { RouteCell } from "../components/RouteCell";
import { useCallback } from "react";
import { Board, type Scene } from "../components/Board";
import { Route } from "../components/Route";
import type { T } from "../i18n";
import { useBottomButton } from "../tg";

export type JobsState =
  | { step: "new" }
  | { step: "rejected" }
  | { step: "review" }
  | { step: "published" }
  | { step: "paused" }
  | { step: "offers"; waiting: number }
  | { step: "contact" };

export type HomeData = { city: string | null; position: string | null; updated: string | null; jobs: JobsState };

/** Derives every part of the board from the user's job route, so nothing on it is decoration. */
export function routeOf(j: JobsState) {
  switch (j.step) {
    case "new": return { idx: 0, status: "boarding", action: true, scene: { rain: false, train: false, lamp: "signal" } };
    case "rejected": return { idx: 0, status: "boarding", action: true, scene: { rain: false, train: false, lamp: "signal" } };
    case "review": return { idx: 1, status: "enroute", action: false, scene: { rain: true, train: false, lamp: "dim" } };
    case "paused": return { idx: 2, status: "enroute", action: false, scene: { rain: false, train: false, lamp: "dim" } };
    case "published": return { idx: 2, status: "enroute", action: false, scene: { rain: true, train: false, lamp: "dim" } };
    case "offers": return { idx: 3, status: "boarding", action: true, scene: { rain: false, train: true, lamp: "signal" } };
    case "contact": return { idx: 4, status: "arrived", action: false, scene: { rain: false, train: true, lamp: "dim" } };
  }
}

type Props = { t: T; data: HomeData; go: (s: string) => void };

export function Home({ t, data, go }: Props) {
  const r = routeOf(data.jobs) as { idx: number; status: "boarding" | "enroute" | "arrived"; action: boolean; scene: Scene };
  const jobsLine =
    data.jobs.step === "new" ? t("jobs.new")
    : data.jobs.step === "rejected" ? t("jobs.rejected")
    : data.jobs.step === "review" ? t("jobs.review")
    : data.jobs.step === "published" ? t("jobs.published")
    : data.jobs.step === "paused" ? t("jobs.paused")
    : data.jobs.step === "offers" ? t.n("jobs.offers", data.jobs.waiting)
    : t("route.contact");
  const statusText = t(`status.${r.status}` as const);

  const primary = data.jobs.step === "new" ? t("btn.fillProfile")
    : data.jobs.step === "rejected" ? t("btn.fixProfile")
    : data.jobs.step === "offers" || data.jobs.step === "contact" ? t("btn.seeOffers")
    : data.jobs.step === "published" || data.jobs.step === "paused" ? t("btn.myProfile") : null;
  const onPrimary = useCallback(() => go(["new", "rejected"].includes(data.jobs.step) ? "form" : "offers"), [go, data.jobs.step]);
  useBottomButton(primary, onPrimary);

  return (
    <>
      <Board
        scene={r.scene}
        caption={t("board.yours")}
        meta={data.updated ? t("board.updated", { time: data.updated }) : undefined}
        station={data.city ? t("board.station", { city: data.city }) : t("board.noCity")}
        sub={data.position ?? t("board.noCityHint")}
      />
      <List>
        <Section>
          <RouteCell title={t("jobs.title")} explain={jobsLine} status={r.status} statusText={statusText} onClick={onPrimary} />
          <Route t={t} current={r.idx} action={r.action} size="platforms" />
        </Section>
        {data.jobs.step === "new" && <p className="hint">{t("jobs.privacy")}</p>}
        <Section header={t("help.title")}>
          <Cell subtitle={t("housing.sub")} onClick={() => go("housing")}>{t("housing.title")}</Cell>
          <Cell subtitle={t("reference.sub")} onClick={() => go("reference")}>{t("reference.title")}</Cell>
        </Section>
        <p className="quiet">{t("soon")}</p>
      </List>
    </>
  );
}
