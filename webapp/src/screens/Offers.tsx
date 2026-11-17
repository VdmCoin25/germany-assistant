import { Cell, List, Placeholder, Section } from "@telegram-apps/telegram-ui";
import { Switch } from "../components/Fields";
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
type Seeker = { status: "pending" | "approved" | "rejected"; is_active: boolean; position: string; city: string | null;
  land: string | null; german_level: string | null; employment: string; shifts_ok: boolean; experience: string; about: string | null };
type JobsMe = { seeker: Seeker | null; inbox: Offer[] };
type View = { name: "list" } | { name: "offer"; id: number } | { name: "consent"; id: number } | { name: "done" };

type Props = { t: T; exit: () => void; editProfile: () => void; draftStep?: number | null };

/** Offers addressed to the seeker: list → offer → consent → contact passed. Data from GET /api/jobs/me. */
export function Offers({ t, exit, editProfile, draftStep = null }: Props) {
  const hasDraft = !!draftStep;
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
    : view.name === "list" ? { run: editProfile, text:
        hasDraft ? t("btn.continueForm")
        : !data?.seeker ? t("btn.fillProfile")
        : data.seeker.status === "rejected" ? t("btn.fixProfile")
        : t("btn.editProfile") }
    : null;
  const mainRef = useRef(main); mainRef.current = main;          // stable handler: no re-subscribe on every render
  const runMain = useCallback(() => mainRef.current?.run(), []);
  useBottomButton(view.name === "done" ? main?.text ?? null : err || !data ? null : main?.text ?? null, runMain, { loading: busy });
  const decline = useCallback(() => answer(false), [answer]);
  useSecondaryButton(view.name === "offer" && current?.status === "sent" ? t("btn.decline") : null, decline);

  if (view.name === "done") return (
    <>
      <h1 className="q">{t("done.title")}</h1>
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

  return <JobHub t={t} data={data} offers={offers} draftStep={draftStep} open={(id) => show({ name: "offer", id })} edit={editProfile} reload={load} />;
}

const place = (o: Offer) => {
  const i = o.vacancy_info;
  return i ? [i.city, i.land ? LANDS[i.land] : null].filter((x, k, a) => x && a.indexOf(x) === k).join(", ") : "";
};
const empKey = (e?: string) => (e ? (`emp.${e}` as Key) : null);

type HubState = "new" | "draft" | "review" | "rejected" | "published" | "paused" | "offers" | "contact";
const ROUTE_STEP: Record<HubState, number> = { new: 0, draft: 0, rejected: 0, review: 1, published: 2, paused: 2, offers: 3, contact: 4 };

/** "Work" in one screen: what is happening now and what comes next, the profile as employers see it, invitations. */
function JobHub({ t, data, offers, draftStep, open, edit, reload }:
  { t: T; data: JobsMe; offers: Offer[]; draftStep: number | null; open: (id: number) => void; edit: () => void; reload: () => void }) {
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
  const state: HubState =
    !s ? (draftStep ? "draft" : "new")
    : s.status === "rejected" ? "rejected" : s.status === "pending" ? "review"
    : waiting.length ? "offers" : answered.some((o) => o.status === "accepted") ? "contact"
    : !s.is_active ? "paused" : "published";
  const line = (o: Offer) => [o.company, place(o), o.vacancy_info?.salary].filter(Boolean).join(" · ");
  const where = s ? [s.city, s.land ? LANDS[s.land] : null].filter((x, i, a) => x && a.indexOf(x) === i).join(", ") : "";
  const emp = s ? (s.employment === "any" ? ("emp.anyLong" as Key) : empKey(s.employment)) : null;
  return (
    <>
      <h1 className="q">{t("jobs.title")}</h1>
      <List>
        <Section>
          <div className="hub-status" role="status">
            <h2>{t(`hub.h.${state}` as Key)}</h2>
            <p>{t(`hub.t.${state}` as Key, { n: draftStep ?? 1 })}</p>
          </div>
          <Route t={t} current={ROUTE_STEP[state]} action={["new", "draft", "rejected", "offers"].includes(state)} size="platforms" />
        </Section>

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

        {s && (
          <Section header={t("hub.myProfile")}>
            <Cell multiline onClick={edit} after={<span className="edit">{t("hub.edit")}</span>}
                  subtitle={[where, emp ? t(emp) : null, s.german_level === "A0" ? t("tag.noGerman") : s.german_level ? t("tag.german", { level: s.german_level }) : null]
                    .filter(Boolean).join(" · ")}>
              {s.position}
            </Cell>
            {s.status === "approved" && (
              <Cell Component="label" multiline subtitle={active ? t("offers.visibleOn") : t("offers.visibleOff")}
                    after={<Switch label={t("offers.visible")} checked={active} disabled={saving} onChange={(e) => toggle(e.target.checked)} />}>
                {t("offers.visible")}
              </Cell>
            )}
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
        {s && !offers.length && <Section header={t("hub.invites")}><Cell multiline>{t("hub.noInvites")}</Cell></Section>}
      </List>
    </>
  );
}

function OfferCard({ t, o, note }: { t: T; o: Offer; note: string | null }) {
  const i = o.vacancy_info, emp = empKey(i?.employment);
  return (
    <>
      <h1 className="q">{o.vacancy ?? t("offers.noVacancy")}</h1>
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
      <h1 className="q">{t("consent.q")}</h1>
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
