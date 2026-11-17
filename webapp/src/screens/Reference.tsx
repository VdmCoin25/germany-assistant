import { Cell, List, Section } from "@telegram-apps/telegram-ui";
import { Input } from "../components/Fields";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type ApiError } from "../api";
import { HomeSkeleton, LoadError } from "../components/States";
import type { Lang, T } from "../i18n";
import { openLink, useBackButton } from "../tg";

type Source = { topic: string; title_uk: string; title_ru: string; url: string; checked_at: string | null };
type Meta = { topics: Record<string, { uk: string; ru: string }> };

const fmtDate = (iso: string) => { const [y, m, d] = iso.split("-"); return `${d}.${m}.${y}`; };
const host = (u: string) => { try { return new URL(u).host.replace(/^www\./, ""); } catch { return u; } };

/** Official links only, grouped by topic, with a search first: people come with one word (Anmeldung, Kindergeld). */
export function Reference({ t, lang, exit }: { t: T; lang: Lang; exit: () => void }) {
  const [data, setData] = useState<{ meta: Meta; sources: Source[] } | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const load = useCallback(async () => {
    setErr(null);
    try {
      const [meta, sources] = await Promise.all([api<Meta>("/api/meta"), api<Source[]>("/api/sources")]);
      setData({ meta, sources });
    } catch (e) { setErr(e as ApiError); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useBackButton(useCallback(() => (open ? setOpen(null) : exit()), [open, exit]));

  const title = (s: Source) => (lang === "ru" ? s.title_ru : s.title_uk);
  const hits = useMemo(() => {
    if (!data || q.trim().length < 2) return null;
    const f = q.trim().toLowerCase();
    return data.sources.filter((s) =>
      [title(s), s.url, data.meta.topics[s.topic]?.[lang] ?? ""].some((x) => x.toLowerCase().includes(f)));
  }, [q, data, lang]);   // eslint-disable-line react-hooks/exhaustive-deps

  if (err) return <LoadError t={t} status={err.status} retry={load} />;
  if (!data) return <HomeSkeleton t={t} />;
  const link = (s: Source) => (
    <Cell key={s.url} multiline onClick={() => openLink(s.url)}
          subtitle={[host(s.url), s.checked_at ? t("ref.checked", { date: fmtDate(s.checked_at) }) : null].filter(Boolean).join(" · ")}>
      {title(s)}
    </Cell>
  );

  if (open) return (
    <><h1 className="q">{data.meta.topics[open]?.[lang] ?? open}</h1>
      <List><Section footer={t("ref.note")}>{data.sources.filter((s) => s.topic === open).map(link)}</Section></List></>
  );
  return (
    <><h1 className="q">{t("ref.title")}</h1>
      <List>
        <Section>
          <Input aria-label={t("ref.title")} placeholder={t("ref.search")} value={q} type="search" onChange={(e) => setQ(e.target.value)} />
        </Section>
        {hits ? (hits.length ? <Section>{hits.map(link)}</Section> : <p className="lead">{t("ref.nothing")}</p>)
          : <Section footer={t("ref.note")}>
              {Object.entries(data.meta.topics).map(([k, v]) => (
                <Cell key={k} multiline onClick={() => setOpen(k)}
                      after={<span className="num quiet-count">{data.sources.filter((s) => s.topic === k).length}</span>}>
                  {v[lang] ?? v.uk}
                </Cell>
              ))}
            </Section>}
      </List></>
  );
}
