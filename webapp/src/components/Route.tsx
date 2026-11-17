import type { T } from "../i18n";

export const STEPS = ["route.profile", "route.review", "route.offers", "route.consent", "route.contact"] as const;

type Props = {
  t: T;
  current: number;          // 0-based index into STEPS
  action: boolean;          // current step needs the user's action ("Посадка")
  size?: "line" | "platforms";
};

/** Train-line progress: passed stops filled, the current one marked, the next ones grey.
 *  "platforms" draws the step numbers as platform plates (look B). */
export function Route({ t, current, action, size = "line" }: Props) {
  return (
    <div className={`route route--${size}`}>
      <p className="route__caption">{t("route.step", { n: current + 1, total: STEPS.length })} · {t(STEPS[current])}</p>
      <ol className="route__line">
        {STEPS.map((k, i) => {
          const state = i < current ? "done" : i === current ? (action ? "now act" : "now") : "next";
          return (
            <li key={k} className={`route__stop ${state}`} aria-current={i === current ? "step" : undefined}>
              <span className="route__mark" aria-hidden="true">{size === "platforms" ? i + 1 : ""}</span>
              <span className={size === "platforms" ? "route__label" : "route__label sr"}>{t(k)}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
