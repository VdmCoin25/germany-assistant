import { Cell, Input, List, Section } from "@telegram-apps/telegram-ui";
import { useCallback, useId, useMemo, useState } from "react";
import { Board } from "../components/Board";
import type { T } from "../i18n";
import { haptic, useBackButton, useBottomButton } from "../tg";

// Prototype sample. The real list comes from an official source (see docs/redesign/J0-research.md, item 5).
const CITIES: [string, string][] = [
  ["Berlin", "Berlin"], ["Bergisch Gladbach", "Nordrhein-Westfalen"], ["Bernau bei Berlin", "Brandenburg"],
  ["Bremen", "Bremen"], ["Bremerhaven", "Bremen"], ["München", "Bayern"], ["Hamburg", "Hamburg"], ["Leipzig", "Sachsen"],
];

type Props = { t: T; look: "a" | "b"; step: number; total: number; initial?: string; back: () => void; next: () => void };

/** One question per screen. The city field is a combobox: typed text filters a listbox of real places. */
export function FormCity({ t, look, step, total, initial = "", back, next }: Props) {
  const [q, setQ] = useState(initial);
  const [picked, setPicked] = useState<string | null>(null);
  const listId = useId();
  const hits = useMemo(() => q.trim().length < 2 ? [] :
    CITIES.filter(([c]) => c.toLowerCase().startsWith(q.trim().toLowerCase())).slice(0, 5), [q]);

  useBackButton(back);
  const onNext = useCallback(() => { haptic.success(); next(); }, [next]);
  useBottomButton(t("btn.next"), onNext, { active: !!picked });

  return (
    <>
      {look === "b"
        ? <Board size="compact" scene={{ rain: false, train: false, lamp: "signal" }}
                 caption={t("route.step", { n: step, total })} station={t("jobs.title")} />
        : <div className="progress num">{t("form.progress", { n: step, total })}
            <div className="progress__bar"><i style={{ width: `${(step / total) * 100}%` }} /></div></div>}
      <h2 className="q">{t("form.where")}</h2>
      <List>
        <Section footer={picked ? t("form.landAuto") : t("form.pickCity")}>
          <Input
            header={t("form.city")}
            placeholder={t("form.cityPh")}
            value={picked ?? q}
            onChange={(e) => { setQ(e.target.value); setPicked(null); }}
            role="combobox"
            aria-expanded={hits.length > 0 && !picked}
            aria-controls={listId}
            aria-autocomplete="list"
            autoComplete="off"
          />
          {!picked && hits.length > 0 && (
            <div role="listbox" id={listId}>
              {hits.map(([city, land]) => {
                const n = q.trim().length;
                return (
                  <Cell key={city} role="option" aria-selected={false} subtitle={land}
                        onClick={() => { setPicked(city); haptic.select(); }}>
                    <mark>{city.slice(0, n)}</mark>{city.slice(n)}
                  </Cell>
                );
              })}
            </div>
          )}
        </Section>
      </List>
      <p className="hint">{t("form.draft")}</p>
    </>
  );
}
