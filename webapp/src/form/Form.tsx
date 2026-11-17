import { Cell, List, Section, Textarea } from "@telegram-apps/telegram-ui";
import { Input, Select } from "../components/Fields";
import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { api, ApiError } from "../api";
import { Route } from "../components/Route";
import type { T, Key } from "../i18n";
import { haptic, useBackButton, useBottomButton, useSecondaryButton } from "../tg";
import { Chips } from "./Chips";
import { findCities, landOf, LANDS } from "./cities";
import { clearDraft, EMPTY, loadDraft, saveDraft, type Draft } from "./draft";

const TOTAL = 6;
const LEVELS = ["A0", "A1", "A2", "B1", "B2", "C1"] as const;
const EMPLOYMENT = ["full", "part", "mini", "any"] as const;
const POPULAR = ["pos.warehouse", "pos.cleaning", "pos.kitchen", "pos.care", "pos.driver"] as const;
const MAX = { position: 120, city: 80, experience: 800, about: 500 };

type Screen = number | "preview" | "sent";
type Props = { t: T; existing: Partial<Draft> | null; exit: () => void; done: () => void };

/** The anonymous profile: one question per screen, draft saved after every step, a preview of exactly
 *  what employers will see, then a clear next step. Maps 1:1 onto PUT /api/jobs/seeker. */
export function Form({ t, existing, exit, done }: Props) {
  const [d, setD] = useState<Draft>({ ...EMPTY, ...existing });
  const [screen, setScreen] = useState<Screen>(1);
  const [fromPreview, setFromPreview] = useState(false);
  const [restored, setRestored] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (p: Partial<Draft>) => { touched.current = true; setD((x) => ({ ...x, ...p })); };

  // A newer draft wins over the published profile: the user was in the middle of editing it.
  const touched = useRef(false);
  useEffect(() => {
    loadDraft().then((saved) => {
      if (!saved || !saved.position || touched.current) return;
      setD(saved); setScreen(Math.min(Math.max(saved.step, 1), TOTAL)); setRestored(true);
    });
  }, []);

  const go = useCallback((s: Screen) => {
    setError(null);
    if (s === "preview") setFromPreview(false);   // an edit started from the preview ends there
    setD((x) => { const next = { ...x, step: typeof s === "number" ? s : x.step }; saveDraft(next); return next; });
    setScreen(s); window.scrollTo(0, 0);
  }, []);

  const valid = (s: number) =>
    s === 1 ? d.position.trim().length >= 2
    : s === 2 ? !!d.land
    : s === 4 ? !!d.german_level
    : s === 5 ? d.experience.trim().length >= 2
    : true;
  const missing: Record<number, Key> = { 1: "form.needPosition", 2: "form.needCity", 4: "form.needLevel", 5: "form.min" };

  const next = useCallback(() => {
    if (typeof screen !== "number") return;
    haptic.select();
    go(fromPreview || screen === TOTAL ? "preview" : screen + 1);
  }, [screen, fromPreview, go]);

  const back = useCallback(() => {
    if (screen === "sent") return done();
    if (screen === "preview") return go(TOTAL);
    if (fromPreview) { setFromPreview(false); return go("preview"); }
    if (screen === 1) return exit();
    go((screen as number) - 1);
  }, [screen, fromPreview, go, exit, done]);

  const send = useCallback(async () => {
    if (sending) return;   // the bottom button re-subscribes while loading; ignore a second tap
    setSending(true); setError(null);
    try {
      await api("/api/jobs/seeker", { method: "PUT", body: JSON.stringify({
        position: d.position.trim().slice(0, MAX.position), land: d.land, city: d.city.trim().slice(0, MAX.city) || null, german_level: d.german_level,
        employment: d.employment, shifts_ok: d.shifts_ok, experience: d.experience.trim(), about: d.about.trim() || null,
      }) });
      clearDraft(); haptic.success(); setScreen("sent");
    } catch (e) {
      const err = e as ApiError;
      const limit = /^submit_limit:(\d+)$/.exec(err.code ?? "");
      setError(limit ? t("err.limit", { m: limit[1] })
        : err.status === 422 ? t("err.invalid")
        : err.status === 401 ? t("load.expiredHint")
        : err.status === 403 ? t("load.blockedHint")
        : t("err.send"));
    } finally { setSending(false); }
  }, [d, t, sending]);

  // One main action per screen, rendered by Telegram.
  const isStep = typeof screen === "number";
  useBackButton(screen === "sent" || sending ? null : back);
  useBottomButton(
    screen === "sent" ? t("btn.home") : screen === "preview" ? t("btn.send") : t("btn.next"),
    screen === "sent" ? done : screen === "preview" ? send : next,
    { active: isStep ? valid(screen as number) : true, loading: sending },
  );
  const skip = useCallback(() => { set({ about: "" }); go("preview"); }, [go]);
  useSecondaryButton(screen === TOTAL ? t("btn.skip") : null, skip);

  if (screen === "sent") return <Sent t={t} />;
  if (screen === "preview") return <Preview t={t} d={d} error={error} edit={(s) => { setFromPreview(true); go(s); }} />;

  const s = screen as number;
  return (
    <>
      <div className="progress num">{t("form.progress", { n: s, total: TOTAL })}
        <div className="progress__bar" role="progressbar" aria-label={t("form.progress", { n: s, total: TOTAL })} aria-valuemin={0} aria-valuemax={TOTAL} aria-valuenow={s}>
          <i style={{ width: `${(s / TOTAL) * 100}%` }} /></div></div>
      {restored && s === d.step && <p className="hint">{t("draft.restored")}</p>}
      {s === 1 && <>
        <h1 className="q">{t("form.q1")}</h1>
        <List><Section>
          <Input header={t("form.position")} placeholder={t("form.positionPh")} value={d.position} maxLength={MAX.position}
                 onChange={(e) => set({ position: e.target.value })} />
        </Section></List>
        <p className="hint">{t("form.popular")}</p>
        <div className="chips">{POPULAR.map((k) => (
          <button key={k} type="button" className="chip" onClick={() => { haptic.select(); set({ position: t(k) }); }}>{t(k)}</button>
        ))}</div>
      </>}
      {s === 2 && <StepCity t={t} d={d} set={set} />}
      {s === 3 && <>
        <h1 className="q">{t("form.q3")}</h1>
        <Chips label={t("form.q3")} value={d.employment} onChange={(v) => set({ employment: v })}
               options={EMPLOYMENT.map((v) => ({ value: v, text: t(`emp.${v}` as Key) }))} />
        <label className="check"><input type="checkbox" checked={d.shifts_ok}
               onChange={(e) => { haptic.select(); set({ shifts_ok: e.target.checked }); }} /> {t("form.shifts")}</label>
      </>}
      {s === 4 && <>
        <h1 className="q">{t("form.q4")}</h1>
        <Chips label={t("form.q4")} value={d.german_level} onChange={(v) => set({ german_level: v })}
               options={LEVELS.map((v) => ({ value: v, text: v === "A0" ? t("level.A0") : v }))} />
        <p className="hint">{t("form.levelHint")}</p>
      </>}
      {s === 5 && <TextStep t={t} q="form.q5" ph="form.expPh" hint="form.expHint" max={MAX.experience}
                             value={d.experience} onChange={(v) => set({ experience: v })} />}
      {s === 6 && <TextStep t={t} q="form.q6" ph="form.aboutPh" hint="form.optional" max={MAX.about}
                             value={d.about} onChange={(v) => set({ about: v })} />}
      {!valid(s) && missing[s] && <p className="hint" aria-live="polite">{t(missing[s])}</p>}
    </>
  );
}

function TextStep({ t, q, ph, hint, max, value, onChange }:
  { t: T; q: Key; ph: Key; hint: Key; max: number; value: string; onChange: (v: string) => void }) {
  const id = useId();
  return (
    <>
      <h1 className="q" id={id}>{t(q)}</h1>
      <List><Section footer={`${t(hint)} · ${t("form.counter", { n: value.length, max })}`}>
        <Textarea aria-labelledby={id} placeholder={t(ph)} value={value} maxLength={max} rows={5}
                  onChange={(e) => onChange(e.target.value)} />
      </Section></List>
    </>
  );
}

/** City: ARIA combobox over the big-city list; any other place can be typed, then the Land is chosen. */
function StepCity({ t, d, set }: { t: T; d: Draft; set: (p: Partial<Draft>) => void }) {
  const [q, setQ] = useState(d.city);
  const [active, setActive] = useState(-1);
  const [closed, setClosed] = useState(!!d.land);
  const listId = useId();
  const hits = useMemo(() => findCities(q), [q]);
  const typed = q.trim();
  const other = typed.length >= 2 && !hits.some(([c]) => c.toLowerCase() === typed.toLowerCase());
  const options: { city: string; land: string | null }[] = [
    ...hits.map(([city, land]) => ({ city, land })), ...(other ? [{ city: typed, land: null }] : []),
  ];
  const open = !closed && options.length > 0;
  const pick = (o: { city: string; land: string | null }) => {
    setQ(o.city); setClosed(true); setActive(-1); haptic.select();
    set({ city: o.city, land: o.land ?? landOf(o.city) ?? null });
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!open) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => (i + 1) % options.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((i) => (i <= 0 ? options.length - 1 : i - 1)); }
    else if (e.key === "Enter" && active >= 0) { e.preventDefault(); pick(options[active]); }
    else if (e.key === "Escape") { setClosed(true); setActive(-1); }
  };
  const knownLand = landOf(d.city);
  return (
    <>
      <h1 className="q">{t("form.where")}</h1>
      <List>
        <Section footer={d.land && knownLand ? t("form.landAuto") : undefined}>
          <Input header={t("form.city")} placeholder={t("form.cityPh")} value={q} autoComplete="off" maxLength={MAX.city}
                 onChange={(e) => { setQ(e.target.value); setClosed(false); setActive(-1); set({ city: e.target.value, land: null }); }}
                 onKeyDown={onKey} role="combobox" aria-expanded={open} aria-controls={listId} aria-autocomplete="list"
                 aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined} />
          {open && (
            <div role="listbox" id={listId} aria-label={t("form.city")}>
              {options.map((o, i) => (
                <Cell key={o.city + (o.land ?? "-")} id={`${listId}-${i}`} role="option" aria-selected={i === active}
                      className={i === active ? "is-active" : undefined} onClick={() => pick(o)}
                      subtitle={o.land ? LANDS[o.land] : undefined}>
                  {o.land ? o.city : t("form.useTyped", { city: o.city })}
                </Cell>
              ))}
            </div>
          )}
        </Section>
        {closed && !knownLand && (
          <Section>
            <Select header={t("form.land")} value={d.land ?? ""} onChange={(e) => set({ land: e.target.value || null })}>
              <option value="">—</option>
              {Object.entries(LANDS).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
            </Select>
          </Section>
        )}
      </List>
    </>
  );
}

function Preview({ t, d, error, edit }: { t: T; d: Draft; error: string | null; edit: (s: number) => void }) {
  const where = [d.city, d.land ? LANDS[d.land] : null].filter((x, i, a) => x && a.indexOf(x) === i).join(", ");
  const rows: [number, Key, string][] = [
    [1, "row.position", d.position], [2, "row.city", where],
    [3, "row.employment", t(`emp.${d.employment}` as Key) + (d.shifts_ok ? `, ${t("tag.shifts").toLowerCase()}` : "")],
    [4, "row.level", d.german_level === "A0" ? t("level.A0") : d.german_level ?? ""],
    [5, "row.experience", d.experience], [6, "row.about", d.about || "—"],
  ];
  return (
    <>
      <h1 className="q">{t("preview.title")}</h1>
      <article className="preview" aria-label={t("preview.title")}>
        <h3>{d.position}</h3>
        <p className="preview__meta">{[where, t(`emp.${d.employment}` as Key)].filter(Boolean).join(" · ")}</p>
        <p className="preview__tags">
          <span>{d.german_level && d.german_level !== "A0" ? t("tag.german", { level: d.german_level }) : t("tag.noGerman")}</span>
          {d.shifts_ok && <span>{t("tag.shifts")}</span>}
        </p>
        <p className="preview__text">{d.experience}</p>
        {d.about && <p className="preview__text">{d.about}</p>}
        <p className="preview__hidden">{t("preview.hidden")}</p>
      </article>
      {error && <p className="form-error" role="alert">{error}</p>}
      <List><Section footer={t("preview.next")}>
        {rows.map(([s, k, v]) => (
          <Cell key={k} onClick={() => edit(s)} subtitle={v} multiline
                after={<span className="edit">{t("preview.edit")}</span>}>{t(k)}</Cell>
        ))}
      </Section></List>
    </>
  );
}

function Sent({ t }: { t: T }) {
  return (
    <>
      <h1 className="q">{t("sent.title")}</h1>
      <List><Section>
        <Route t={t} current={1} action={false} size="platforms" />
      </Section></List>
      <p className="lead">{t("sent.text")}</p>
      <p className="hint">{t("sent.noDeadline")}</p>
    </>
  );
}
