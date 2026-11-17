import { Cell, List, Section } from "@telegram-apps/telegram-ui";
import { useCallback } from "react";
import { Board, type Scene } from "../components/Board";
import { Route } from "../components/Route";
import type { T } from "../i18n";
import { useBottomButton } from "../tg";

export type JobsState =
  | { step: "new" }
  | { step: "review" }
  | { step: "published" }
  | { step: "offers"; waiting: number }
  | { step: "contact" };

export type HomeData = { city: string | null; position: string | null; updated: string | null; jobs: JobsState };

/** Derives every part of the board from the user's job route, so nothing on it is decoration. */
export function routeOf(j: JobsState) {
  switch (j.step) {
    case "new": return { idx: 0, status: "boarding", action: true, scene: { rain: false, train: false, lamp: "signal" } };
    case "review": return { idx: 1, status: "enroute", action: false, scene: { rain: true, train: false, lamp: "dim" } };
    case "published": return { idx: 2, status: "enroute", action: false, scene: { rain: true, train: false, lamp: "dim" } };
    case "offers": return { idx: 3, status: "arrived", action: true, scene: { rain: false, train: true, lamp: "signal" } };
    case "contact": return { idx: 4, status: "arrived", action: false, scene: { rain: false, train: true, lamp: "dim" } };
  }
}

type Props = { t: T; look: "a" | "b"; data: HomeData; go: (s: string) => void };

export function Home({ t, look, data, go }: Props) {
  const r = routeOf(data.jobs) as { idx: number; status: "boarding" | "enroute" | "arrived"; action: boolean; scene: Scene };
  const jobsLine =
    data.jobs.step === "new" ? t("jobs.new")
    : data.jobs.step === "review" ? t("jobs.review")
    : data.jobs.step === "published" ? t("jobs.published")
    : data.jobs.step === "offers" ? t.n("jobs.offers", data.jobs.waiting)
    : t("route.contact");
  const statusText = t(`status.${r.status}` as const);

  const primary = data.jobs.step === "new" ? t("btn.fillProfile")
    : data.jobs.step === "offers" || data.jobs.step === "contact" ? t("btn.seeOffers")
    : data.jobs.step === "published" ? t("btn.myProfile") : null;
  const onPrimary = useCallback(() => go(data.jobs.step === "new" ? "form" : "offers"), [go, data.jobs.step]);
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
          <Cell
            onClick={onPrimary}
            subtitle={jobsLine}
            after={<span className={`status status--${r.status}`}>{statusText}</span>}
            multiline
          >
            {t("jobs.title")}
          </Cell>
          <Route t={t} current={r.idx} action={r.action} size={look === "b" ? "platforms" : "line"} />
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
