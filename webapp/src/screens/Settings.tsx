import { Button, Cell, Input, List, Section, Select, Switch } from "@telegram-apps/telegram-ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ApiError } from "../api";
import { HomeSkeleton, LoadError } from "../components/States";
import { LANDS } from "../form/cities";
import type { Key, T } from "../i18n";
import { haptic, tg, useBackButton } from "../tg";

type Me = { language: string | null; land: string | null; city: string | null; german_level: string | null;
  goal: string | null; residence_status: string | null; broadcast_consent: boolean };

const LEVELS = ["A0", "A1", "A2", "B1", "B2", "C1"];
const GOALS = ["documents", "jobs", "housing", "translation", "other"];
const STATUSES = ["p24", "other"];

/** Settings and "my data": every change is saved at once (PATCH /api/me); deletion asks Telegram's own confirm dialog. */
export function Settings({ t, exit, onLanguage }: { t: T; exit: () => void; onLanguage: (l: string) => void }) {
  const [me, setMe] = useState<Me | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const load = useCallback(async () => {
    setErr(null);
    try { setMe(await api<Me>("/api/me")); } catch (e) { setErr(e as ApiError); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useBackButton(exit);

  const timer = useRef<number>();
  const save = useCallback(async (patch: Partial<Me>) => {
    setMe((m) => (m ? { ...m, ...patch } : m)); setNote(null);
    try {
      await api("/api/me", { method: "PATCH", body: JSON.stringify(patch) });
      haptic.select(); setNote(t("set.saved"));
      window.clearTimeout(timer.current); timer.current = window.setTimeout(() => setNote(null), 2000);
      if (patch.language) onLanguage(patch.language);
    } catch { setNote(t("set.saveError")); load(); }
  }, [t, load, onLanguage]);

  const remove = useCallback(() => {
    const go = async (yes: boolean) => {
      if (!yes) return;
      setDeleting(true);
      try {
        await api("/api/me", { method: "DELETE" }); setNote(t("data.deleted")); haptic.success();
        setTimeout(() => (tg?.close ? tg.close() : location.replace("about:blank")), 1500);   // never reload: GET /api/me would recreate the user
      }
      catch { setNote(t("set.saveError")); setDeleting(false); }
    };
    if (tg?.showConfirm) tg.showConfirm(t("data.deleteConfirm"), go); else go(window.confirm(t("data.deleteConfirm")));
  }, [t]);

  if (err) return <LoadError t={t} status={err.status} retry={load} />;
  if (!me) return <HomeSkeleton t={t} />;
  const opt = (v: string | null) => v ?? "";
  const sel = (k: keyof Me, label: Key, values: string[], text: (v: string) => string) => (
    <Select header={t(label)} value={opt(me[k] as string | null)}
            onChange={(e) => save({ [k]: e.target.value || null } as Partial<Me>)}>
      {k !== "language" && <option value="">{t("set.notSet")}</option>}
      {values.map((v) => <option key={v} value={v}>{text(v)}</option>)}
    </Select>
  );
  return (
    <>
      <h2 className="q">{t("set.title")}</h2>
      {note && <p className="offline" role="status">{note}</p>}
      <List>
        <Section>
          {sel("language", "set.language", ["uk", "ru"], (v) => (v === "uk" ? "Українська" : "Русский"))}
          {sel("land", "set.land", Object.keys(LANDS), (v) => LANDS[v])}
          <Input key={me.city ?? ""} header={t("set.city")} maxLength={80} defaultValue={me.city ?? ""}
                 onBlur={(e) => e.target.value.trim() !== (me.city ?? "") && save({ city: e.target.value.trim() || null })} />
          {sel("german_level", "set.level", LEVELS, (v) => (v === "A0" ? t("level.A0") : v))}
          {sel("goal", "set.goal", GOALS, (v) => t(`goal.${v}` as Key))}
          {sel("residence_status", "set.status", STATUSES, (v) => t(`st.${v}` as Key))}
          <Cell Component="label" multiline after={<Switch checked={me.broadcast_consent} onChange={(e) => save({ broadcast_consent: e.target.checked })} />}>
            {t("set.broadcast")}
          </Cell>
        </Section>
        <Section header={t("data.title")} footer={t("data.notLawyer")}>
          <p className="message">{t("data.text")}</p>
          <p className="message"><b>{t("data.warn")}</b></p>
        </Section>
      </List>
      <div className="action">
        <Button size="l" stretched mode="plain" className="danger-button" loading={deleting} onClick={remove}>{t("data.delete")}</Button>
      </div>
    </>
  );
}
