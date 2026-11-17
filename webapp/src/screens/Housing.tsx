import { Cell, Input, List, Section, Select, Switch } from "@telegram-apps/telegram-ui";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ApiError } from "../api";
import { HomeSkeleton, LoadError } from "../components/States";
import type { Key, Lang, T } from "../i18n";
import { haptic, openLink, useBackButton, useBottomButton } from "../tg";

type Housing = {
  terms: { de: string; uk: string; ru: string }[];
  checklist: Record<Lang, string[]>; safety: Record<Lang, string[]>;
  sources: { title: string; url: string }[]; checked: string;
};
type Page = "list" | "terms" | "docs" | "calc" | "letter";

const fmtDate = (iso: string) => { const [y, m, d] = iso.split("-"); return `${d}.${m}.${y}`; };
const host = (u: string) => { try { return new URL(u).host.replace(/^www\./, ""); } catch { return u; } };

/** Housing: four entries instead of tabs; texts and sources come from /api/housing (checked against the laws). */
export function HousingScreen({ t, lang, exit, city, level }: { t: T; lang: Lang; exit: () => void; city: string | null; level: string | null }) {
  const [data, setData] = useState<Housing | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [page, setPage] = useState<Page>("list");
  const load = useCallback(async () => {
    setErr(null);
    try { setData(await api<Housing>("/api/housing")); } catch (e) { setErr(e as ApiError); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const open = (p: Page) => { haptic.select(); setPage(p); window.scrollTo(0, 0); };
  const back = useCallback(() => (page === "list" ? exit() : setPage("list")), [page, exit]);
  useBackButton(back);

  if (err) return <LoadError t={t} status={err.status} retry={load} />;
  if (!data) return <HomeSkeleton t={t} />;
  const sources = (
    <Section header={t("h.sources")} footer={t("h.checked", { date: fmtDate(data.checked) })}>
      {data.sources.map((s) => <Cell key={s.url} subtitle={host(s.url)} multiline onClick={() => openLink(s.url)}>{s.title}</Cell>)}
    </Section>
  );

  if (page === "terms") return (
    <><h2 className="q">{t("h.terms")}</h2>
      <List><Section>{data.terms.map((x) => <Cell key={x.de} subtitle={x[lang] || x.uk} multiline>{x.de}</Cell>)}</Section>{sources}</List></>
  );
  if (page === "docs") return (
    <><h2 className="q">{t("h.docs")}</h2>
      <List>
        <Section>{(data.checklist[lang] || data.checklist.uk).map((x) => <Cell key={x} multiline>{x}</Cell>)}</Section>
        <Section header={t("h.safety")}>{(data.safety[lang] || data.safety.uk).map((x) => <Cell key={x} multiline>{x}</Cell>)}</Section>
        {sources}
      </List></>
  );
  if (page === "calc") return <Calc t={t} />;
  if (page === "letter") return <Letter t={t} lang={lang} city={city} level={level} />;

  const entries: [Page, Key, Key][] = [["terms", "h.terms", "h.termsSub"], ["docs", "h.docs", "h.docsSub"],
    ["calc", "h.calc", "h.calcSub"], ["letter", "h.letter", "h.letterSub"]];
  return (
    <><h2 className="q">{t("housing.title")}</h2>
      <List><Section footer={t("h.checked", { date: fmtDate(data.checked) })}>
        {entries.map(([p, a, b]) => <Cell key={p} subtitle={t(b)} multiline onClick={() => open(p)}>{t(a)}</Cell>)}
      </Section></List></>
  );
}

const eur = (n: number) => new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n);

/** Move-in cost: deposit up to 3 net rents, payable in three instalments (§ 551 BGB). Numbers stay on the phone. */
function Calc({ t }: { t: T }) {
  const [v, setV] = useState({ kalt: "500", neben: "150", months: "3", makler: "0", other: "300" });
  const [rates, setRates] = useState(true);
  const n = (s: string) => Math.max(0, parseFloat(s.replace(",", ".")) || 0);
  const kalt = n(v.kalt), warm = kalt + n(v.neben), kaution = kalt * Math.min(3, n(v.months));
  const part = rates ? kaution / 3 : kaution;
  const atMove = warm + part + n(v.makler) + n(v.other), m23 = warm + (rates ? kaution / 3 : 0);
  const num = (k: keyof typeof v, label: Key) => (
    <Input header={t(label)} type="number" inputMode="decimal" min={0} value={v[k]} onChange={(e) => setV({ ...v, [k]: e.target.value })} />
  );
  return (
    <><h2 className="q">{t("h.calc")}</h2><p className="lead">{t("h.calcIntro")}</p>
      <List>
        <Section footer={t("h.kMonthsHint")}>
          {num("kalt", "h.kalt")}{num("neben", "h.neben")}
          <Select header={t("h.kMonths")} value={v.months} onChange={(e) => setV({ ...v, months: e.target.value })}>
            {["3", "2", "1", "0"].map((m) => <option key={m} value={m}>{m}</option>)}
          </Select>
          <Cell Component="label" multiline after={<Switch checked={rates} onChange={(e) => setRates(e.target.checked)} />}>{t("h.rates")}</Cell>
          {num("makler", "h.makler")}{num("other", "h.other")}
        </Section>
        <Section footer={t("h.calcNote")}>
          <Cell after={<b className="num">{eur(warm)}</b>}>{t("h.warm")}</Cell>
          <Cell after={<b className="num">{eur(kaution)}</b>}>{t("h.kaution")}</Cell>
          <Cell after={<b className="num">{eur(atMove)}</b>} multiline><b>{t("h.atMove")}</b></Cell>
          <Cell after={<b className="num">{eur(m23)}</b>}>{t("h.m23")}</Cell>
          <Cell after={<b className="num">{eur(atMove + 2 * m23)}</b>} multiline>{t("h.first3")}</Cell>
        </Section>
      </List></>
  );
}

type LetterFields = { name: string; object: string; city: string; since: string; adults: number; kids: number;
  income: "job" | "jobcenter" | "sozialamt" | "none"; job: string; level: string; moveIn: string; contact: string };

/** German letter with the same content in the user's language, so they know what they send. Built on the phone. */
export function buildLetter(f: LetterFields, lang: Lang) {
  const tr = (uk: string, ru: string) => (lang === "ru" ? ru : uk);
  const kidsDe = (n: number) => (n === 1 ? "1 Kind" : `${n} Kinder`);
  const household: [string, string] =
    f.adults <= 1 && f.kids === 0 ? ["Ich würde allein einziehen.", tr("Я заїду сам(а).", "Я въеду один (одна).")]
    : f.adults <= 1 ? [f.kids === 1 ? "Ich würde zusammen mit meinem Kind einziehen." : `Ich würde zusammen mit meinen ${f.kids} Kindern einziehen.`,
        tr(`Я заїду разом із дітьми: ${f.kids}.`, `Я въеду вместе с детьми: ${f.kids}.`)]
    : [`Wir sind ${f.adults + f.kids} Personen: ${f.adults} Erwachsene${f.kids ? " und " + kidsDe(f.kids) : ""}.`,
        tr(`Нас ${f.adults + f.kids}: дорослих ${f.adults}${f.kids ? ", дітей " + f.kids : ""}.`, `Нас ${f.adults + f.kids}: взрослых ${f.adults}${f.kids ? ", детей " + f.kids : ""}.`)];
  const income: [string, string] | null = {
    job: [f.job ? `Ich arbeite als ${f.job}.` : "Ich bin berufstätig.", f.job ? tr(`Я працюю: ${f.job}.`, `Я работаю: ${f.job}.`) : tr("Я працюю.", "Я работаю.")] as [string, string],
    jobcenter: ["Die Kosten der Unterkunft werden voraussichtlich vom Jobcenter übernommen. Eine Bestätigung reiche ich gerne nach.",
      tr("Оренду, ймовірно, оплачуватиме Jobcenter. Підтвердження надішлю окремо.", "Аренду, вероятно, будет оплачивать Jobcenter. Подтверждение пришлю отдельно.")] as [string, string],
    sozialamt: ["Die Kosten der Unterkunft werden voraussichtlich vom Sozialamt übernommen. Eine Bestätigung reiche ich gerne nach.",
      tr("Оренду, ймовірно, оплачуватиме Sozialamt. Підтвердження надішлю окремо.", "Аренду, вероятно, будет оплачивать Sozialamt. Подтверждение пришлю отдельно.")] as [string, string],
    none: null,
  }[f.income];
  const lines: [string, string][] = [
    ["Sehr geehrte Damen und Herren,", tr("Шановні пані та панове,", "Уважаемые дамы и господа,")],
    [`mit großem Interesse habe ich Ihre Anzeige für die Wohnung ${f.object} gelesen und möchte mich hiermit um die Wohnung bewerben.`,
      tr(`Я з цікавістю прочитав(ла) ваше оголошення про квартиру ${f.object} і хочу подати заявку.`, `Я с интересом прочитал(а) ваше объявление о квартире ${f.object} и хочу подать заявку.`)],
    [`Mein Name ist ${f.name}. Ich komme aus der Ukraine${f.since ? ` und lebe seit ${f.since} in Deutschland` : ""}${f.city ? `, derzeit in ${f.city}` : ""}.`,
      tr(`Мене звати ${f.name}. Я з України${f.since ? `, живу в Німеччині з ${f.since}` : ""}${f.city ? `, зараз у місті ${f.city}` : ""}.`,
         `Меня зовут ${f.name}. Я из Украины${f.since ? `, живу в Германии с ${f.since}` : ""}${f.city ? `, сейчас в городе ${f.city}` : ""}.`)],
    household, ...(income ? [income] : []),
    ...(f.level ? [[`Ich spreche Deutsch auf dem Niveau ${f.level} und lerne weiter.`,
      tr(`Я говорю німецькою на рівні ${f.level} і продовжую вчити.`, `Я говорю по-немецки на уровне ${f.level} и продолжаю учить.`)] as [string, string]] : []),
    ...(f.moveIn ? [[`Ein Einzug wäre ab dem ${f.moveIn} möglich.`, tr(`Можу заїхати з ${f.moveIn}.`, `Могу въехать с ${f.moveIn}.`)] as [string, string]] : []),
    ["Alle nötigen Unterlagen sende ich Ihnen gerne zu. Über eine Einladung zur Besichtigung würde ich mich sehr freuen.",
      tr("Охоче надішлю всі потрібні документи. Буду радий(а) запрошенню на перегляд.", "С радостью пришлю все нужные документы. Буду рад(а) приглашению на просмотр.")],
    [`Mit freundlichen Grüßen\n${f.name}${f.contact ? "\n" + f.contact : ""}`, tr(`З повагою,\n${f.name}`, `С уважением,\n${f.name}`)],
  ];
  return { de: lines.map((l) => l[0]).join("\n\n"), tr: lines.map((l) => l[1]).join("\n\n") };
}

function Letter({ t, lang, city, level }: { t: T; lang: Lang; city: string | null; level: string | null }) {
  const [f, setF] = useState<LetterFields>({ name: "", object: "", city: city ?? "", since: "", adults: 1, kids: 0,
    income: "job", job: "", level: level && level !== "A0" ? level : "", moveIn: "", contact: "" });
  const [made, setMade] = useState(false);
  const [copied, setCopied] = useState<boolean | null>(null);
  const deRef = useRef<HTMLParagraphElement>(null);
  const outRef = useRef<HTMLDivElement>(null);
  const ok = f.name.trim().length > 1 && f.object.trim().length > 1;
  const out = useMemo(() => buildLetter({ ...f, name: f.name.trim(), object: f.object.trim() }, lang), [f, lang]);
  const make = useCallback(() => { setMade(true); haptic.success(); setTimeout(() => outRef.current?.scrollIntoView({ behavior: "smooth" }), 50); }, []);
  const copy = useCallback(async () => {
    try { await navigator.clipboard.writeText(out.de); setCopied(true); haptic.success(); }
    catch {   // clipboard blocked: select the text so a long-press copy works
      setCopied(false);
      const r = document.createRange(); if (deRef.current) { r.selectNodeContents(deRef.current); getSelection()?.removeAllRanges(); getSelection()?.addRange(r); }
    }
  }, [out.de]);
  useBottomButton(made ? t("h.copy") : t("h.make"), made ? copy : make, { active: ok });
  const inp = (k: keyof LetterFields, label: Key, max: number, ph?: Key) => (
    <Input header={t(label)} placeholder={ph ? t(ph) : undefined} maxLength={max} value={String(f[k])} onChange={(e) => { setMade(false); setCopied(null); setF({ ...f, [k]: e.target.value }); }} />
  );
  const sel = (k: "adults" | "kids", label: Key, opts: number[]) => (
    <Select header={t(label)} value={f[k]} onChange={(e) => { setMade(false); setF({ ...f, [k]: +e.target.value }); }}>
      {opts.map((n) => <option key={n} value={n}>{n}</option>)}</Select>
  );
  return (
    <><h2 className="q">{t("h.letter")}</h2><p className="lead">{t("h.letterIntro")}</p>
      <List>
        <Section footer={ok ? undefined : t("h.needFields")}>
          {inp("name", "h.name", 80, "h.namePh")}{inp("object", "h.object", 120, "h.objectPh")}{inp("city", "h.city", 80)}{inp("since", "h.since", 20, "h.sincePh")}
          {sel("adults", "h.adults", [1, 2, 3, 4, 5])}{sel("kids", "h.kids", [0, 1, 2, 3, 4, 5])}
          <Select header={t("h.income")} value={f.income} onChange={(e) => { setMade(false); setF({ ...f, income: e.target.value as LetterFields["income"] }); }}>
            {(["job", "jobcenter", "sozialamt", "none"] as const).map((k) => <option key={k} value={k}>{t(`inc.${k}` as Key)}</option>)}
          </Select>
          {f.income === "job" && inp("job", "h.jobTitle", 60, "h.jobTitlePh")}
          <Select header={t("h.level")} value={f.level} onChange={(e) => { setMade(false); setF({ ...f, level: e.target.value }); }}>
            <option value="">—</option>{["A1", "A2", "B1", "B2", "C1"].map((l) => <option key={l} value={l}>{l}</option>)}
          </Select>
          {inp("moveIn", "h.moveIn", 30, "h.moveInPh")}{inp("contact", "h.contact", 80)}
        </Section>
      </List>
      {made && (
        <div ref={outRef}>
          <List>
            <Section header={t("h.yourLetter")} footer={copied === true ? t("h.copied") : copied === false ? t("h.copyFail") : undefined}>
              <p className="message" lang="de" ref={deRef}>{out.de}</p></Section>
            <Section header={t("h.meaning")}><p className="message">{out.tr}</p></Section>
          </List>
        </div>
      )}
    </>
  );
}
