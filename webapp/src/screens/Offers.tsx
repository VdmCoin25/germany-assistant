import { Cell, List, Placeholder, Section, Switch } from "@telegram-apps/telegram-ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ApiError } from "../api";
import { Route } from "../components/Route";
import { HomeSkeleton, LoadError } from "../components/States";
import { LANDS } from "../form/cities";
import type { Key, T } from "../i18n";
import { haptic, useBackButton, useBottomButton, useSecondaryButton } from "../tg";

type Offer = {
  id: number; kind: "offer" | "apply"; status: "sent" | "accepted" | "declined"; message: string;
  company: string | null; vacancy: string | null; created_at: string | null;
  vacancy_info: { city: string | null; land: string | null; employment: string; salary: string | null; german_level: string | null } | null;
};
type Seeker = { status: "pending" | "approved" | "rejected"; is_active: boolean; position: string; city: string | null };
type JobsMe = { seeker: Seeker | null; inbox: Offer[] };
type View = { name: "list" } | { name: "offer"; id: number } | { name: "consent"; id: number } | { name: "done" };

type Props = { t: T; exit: () => void; editProfile: () => void };

/** Offers addressed to the seeker: list → offer → consent → contact passed. Data from GET /api/jobs/me. */
export function Offers({ t, exit, editProfile }: Props) {
  const [data, setData] = useState<JobsMe | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [view, setView] = useState<View>({ name: "list" });
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const my = ++seq.current;
    setErr(null);
    try { const d = await api<JobsMe>("/api/jobs/me"); if (my === seq.current) setData(d); }
    catch (e) { if (my === seq.current) setErr(e as ApiError); }
  }, []);
  useEffect(() => { load(); return () => { seq.current++; }; }, [load]);

  const show = useCallback((v: View) => { setNote(null); setView(v); window.scrollTo(0, 0); }, []);
  const offers = (data?.inbox ?? []).filter((c) => c.kind === "offer");
  const current = "id" in view ? offers.find((o) => o.id === view.id) : undefined;

  const inFlight = useRef(false);   // state updates too late to stop a quick second tap
  const answer = useCallback(async (accept: boolean) => {
    if (!current || inFlight.current) return;
    inFlight.current = true; setBusy(true); setNote(null);
    try {
      await api(`/api/jobs/requests/${current.id}/answer`, { method: "POST", body: JSON.stringify({ accept }) });
      haptic.success();
      show(accept ? { name: "done" } : { name: "list" });   // the answer is saved: show it even if the refresh fails
      load().catch(() => {});
    } catch (e) {
      const status = (e as ApiError).status;
      setNote(status === 404 ? t("err.gone") : t("err.answer"));
      if (status === 404) load();
    } finally { inFlight.current = false; setBusy(false); }
  }, [current, load, show, t]);

  // Back: consent → offer → list → home. Done has no Back: its one action returns home.
  const back = useCallback(() => {
    if (view.name === "consent") return show({ name: "offer", id: view.id });
    if (view.name === "offer") return show({ name: "list" });
    exit();
  }, [view, show, exit]);
  useBackButton(view.name === "done" || busy ? null : back);

  const waiting = offers.filter((o) => o.status === "sent");
  const main =
    view.name === "done" ? { text: t("btn.home"), run: exit }
    : view.name === "consent" ? { text: t("btn.agree"), run: () => answer(true) }
    : view.name === "offer" && current?.status === "sent" ? { text: t("btn.accept"), run: () => show({ name: "consent", id: current.id }) }
    : view.name === "list" && waiting.length ? { text: t("btn.openOffer"), run: () => show({ name: "offer", id: waiting[0].id }) }
    : view.name === "list" && data?.seeker ? { text: t("offers.myProfile"), run: editProfile }
    : null;
  const mainRef = useRef(main); mainRef.current = main;          // stable handler: no re-subscribe on every render
  const runMain = useCallback(() => mainRef.current?.run(), []);
  useBottomButton(view.name === "done" ? main?.text ?? null : err || !data ? null : main?.text ?? null, runMain, { loading: busy });
  const decline = useCallback(() => answer(false), [answer]);
  useSecondaryButton(view.name === "offer" && current?.status === "sent" ? t("btn.decline") : null, decline);

  if (view.name === "done") return (
    <>
      <h2 className="q">{t("done.title")}</h2>
      <List><Section><Route t={t} current={4} action={false} size="platforms" /></Section></List>
      <p className="lead">{t("done.text")}</p>
      <p className="hint">{t("offer.scam")}</p>
    </>
  );

  if (err) return <LoadError t={t} status={err.status} retry={load} />;
  if (!data) return <HomeSkeleton t={t} />;

  if ((view.name === "offer" || view.name === "consent") && !current) {
    return <Placeholder header={t("err.gone")} />;
  }
  if (view.name === "consent" && current) return <Consent t={t} o={current} seeker={data.seeker} note={note} />;
  if (view.name === "offer" && current) return <OfferCard t={t} o={current} note={note} />;

  return <OfferList t={t} data={data} offers={offers} open={(id) => show({ name: "offer", id })} reload={load} />;
}

const place = (o: Offer) => {
  const i = o.vacancy_info;
  return i ? [i.city, i.land ? LANDS[i.land] : null].filter((x, k, a) => x && a.indexOf(x) === k).join(", ") : "";
};
const empKey = (e?: string) => (e ? (`emp.${e}` as Key) : null);

function OfferList({ t, data, offers, open, reload }:
  { t: T; data: JobsMe; offers: Offer[]; open: (id: number) => void; reload: () => void }) {
  const waiting = offers.filter((o) => o.status === "sent");
  const answered = offers.filter((o) => o.status !== "sent");
  const s = data.seeker;
  const [active, setActive] = useState(s?.is_active ?? true);
  const [saving, setSaving] = useState(false);
  const toggle = async (on: boolean) => {
    setActive(on); setSaving(true); haptic.select();
    try { await api("/api/jobs/seeker/active", { method: "POST", body: JSON.stringify({ active: on }) }); reload(); }
    catch { setActive(!on); } finally { setSaving(false); }
  };
  const step = !s ? 0 : s.status === "pending" ? 1 : waiting.length ? 3 : answered.some((o) => o.status === "accepted") ? 4 : 2;
  const line = (o: Offer) => [o.company, place(o), o.vacancy_info?.salary].filter(Boolean).join(" · ");
  return (
    <>
      <h2 className="q">{t("offers.title")}</h2>
      <List>
        <Section><Route t={t} current={step} action={waiting.length > 0} size="platforms" /></Section>
        {waiting.length > 0 && (
          <Section header={t("offers.waiting", { n: waiting.length })}>
            {waiting.map((o) => (
              <Cell key={o.id} onClick={() => open(o.id)} subtitle={line(o)} multiline
                    after={<span className="status status--boarding">{t("status.boarding")}</span>}>
                {o.vacancy ?? t("offers.noVacancy")}
              </Cell>
            ))}
          </Section>
        )}
        {answered.length > 0 && (
          <Section header={t("offers.answered")}>
            {answered.map((o) => (
              <Cell key={o.id} onClick={() => open(o.id)} subtitle={line(o)} multiline
                    after={o.status === "accepted"
                      ? <span className="status status--arrived">{t("route.contact")}</span>
                      : <span className="status status--expected">{t("offers.declined")}</span>}>
                {o.vacancy ?? t("offers.noVacancy")}
              </Cell>
            ))}
          </Section>
        )}
        {!offers.length && <p className="lead">{s?.status === "pending" ? t("offers.emptyReview") : t("offers.empty")}</p>}
        {s?.status === "approved" && (
          <Section header={t("offers.profile")} footer={active ? t("offers.visibleOn") : t("offers.visibleOff")}>
            <Cell Component="label" multiline subtitle={s.position}
                  after={<Switch checked={active} disabled={saving} onChange={(e) => toggle(e.target.checked)} />}>
              {t("offers.visible")}
            </Cell>
          </Section>
        )}
      </List>
    </>
  );
}

function OfferCard({ t, o, note }: { t: T; o: Offer; note: string | null }) {
  const i = o.vacancy_info, emp = empKey(i?.employment);
  return (
    <>
      <h2 className="q">{o.vacancy ?? t("offers.noVacancy")}</h2>
      {o.company && <p className="lead">{t("offer.from", { company: o.company })}</p>}
      {note && <p className="form-error" role="alert">{note}</p>}
      <List>
        {i && (
          <Section>
            {place(o) && <Cell subhead={t("offer.city")} multiline>{place(o)}</Cell>}
            {emp && <Cell subhead={t("offer.employment")}>{t(emp)}</Cell>}
            {i.salary && <Cell subhead={t("offer.salary")}>{i.salary}</Cell>}
            {i.german_level && <Cell subhead={t("offer.german")}>{i.german_level}</Cell>}
          </Section>
        )}
        <Section header={t("offer.message")}>
          <p className="message">«{o.message}»</p>
        </Section>
      </List>
      <p className="warn">{t("offer.scam")}</p>
      <p className="hint">{o.status === "sent" ? t("offer.declineNote") : o.status === "accepted" ? t("offer.acceptedNote") : t("offer.declinedNote")}</p>
    </>
  );
}

function Consent({ t, o, seeker, note }: { t: T; o: Offer; seeker: Seeker | null; note: string | null }) {
  const company = o.company ?? "";
  return (
    <>
      <h2 className="q">{t("consent.q")}</h2>
      {note && <p className="form-error" role="alert">{note}</p>}
      <List>
        <Section header={t("consent.theyGet", { company })}>
          <Cell subtitle={t("consent.tgSub")} multiline>{t("consent.tg")}</Cell>
          <Cell subtitle={[seeker?.position, seeker?.city].filter(Boolean).join(", ")} multiline>{t("consent.job")}</Cell>
        </Section>
        <Section header={t("consent.youGet")} footer={t("consent.final")}>
          <Cell subtitle={t("consent.employerSub")} multiline>{t("consent.employer")}</Cell>
        </Section>
      </List>
    </>
  );
}
