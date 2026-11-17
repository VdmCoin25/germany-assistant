import { Cell, Input, List, Section } from "@telegram-apps/telegram-ui";
import { useCallback, useId, useMemo, useState, type KeyboardEvent } from "react";
import { Board } from "../components/Board";
import type { T } from "../i18n";
import { haptic, useBackButton, useBottomButton } from "../tg";

// Prototype sample. The real list comes from an official source (see docs/redesign/J0-research.md, item 5).
const CITIES: [string, string][] = [
  ["Berlin", "Berlin"], ["Bergisch Gladbach", "Nordrhein-Westfalen"], ["Bernau bei Berlin", "Brandenburg"],
  ["Bremen", "Bremen"], ["Bremerhaven", "Bremen"], ["München", "Bayern"], ["Hamburg", "Hamburg"], ["Leipzig", "Sachsen"],
];

type Props = { t: T; look: "a" | "b"; step: number; total: number; initial?: string; back: () => void; next: () => void };

/** One question per screen. The city field is an ARIA combobox: typing filters a listbox,
 *  arrows move the active option, Enter picks it, Escape closes the list. */
export function FormCity({ t, look, step, total, initial = "", back, next }: Props) {
  const [q, setQ] = useState(initial);
  const [picked, setPicked] = useState<string | null>(null);
  const [active, setActive] = useState(-1);
  const [closed, setClosed] = useState(false);
  const listId = useId();
  const hits = useMemo(() => q.trim().length < 2 ? [] :
    CITIES.filter(([c]) => c.toLowerCase().startsWith(q.trim().toLowerCase())).slice(0, 5), [q]);
  const open = !picked && !closed && hits.length > 0;

  useBackButton(back);
  const onNext = useCallback(() => { haptic.success(); next(); }, [next]);
  useBottomButton(t("btn.next"), onNext, { active: !!picked });

  const pick = (city: string) => { setPicked(city); setActive(-1); haptic.select(); };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!open) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => (i + 1) % hits.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((i) => (i <= 0 ? hits.length - 1 : i - 1)); }
    else if (e.key === "Enter" && active >= 0) { e.preventDefault(); pick(hits[active][0]); }
    else if (e.key === "Escape") { setClosed(true); setActive(-1); }
  };

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
            onChange={(e) => { setQ(e.target.value); setPicked(null); setClosed(false); setActive(-1); }}
            onKeyDown={onKey}
            role="combobox"
            aria-expanded={open}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
            autoComplete="off"
          />
          {open && (
            <div role="listbox" id={listId} aria-label={t("form.city")}>
              {hits.map(([city, land], i) => {
                const n = q.trim().length;
                return (
                  <Cell key={city} id={`${listId}-${i}`} role="option" aria-selected={i === active}
                        className={i === active ? "is-active" : undefined}
                        subtitle={land} onClick={() => pick(city)}>
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
