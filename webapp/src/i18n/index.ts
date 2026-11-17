import ru from "./ru.json";
import uk from "./uk.json";

export type Lang = "uk" | "ru";
export type Key = keyof typeof uk;
const dict: Record<Lang, Record<Key, string>> = { uk, ru };

export function makeT(lang: Lang) {
  const plural = new Intl.PluralRules(lang);
  const fill = (s: string, vars: Record<string, string | number>) => s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ""));
  const t = (key: Key, vars: Record<string, string | number> = {}) => fill(dict[lang][key], vars);
  /** Keys with .one / .few / .many forms (Slavic plurals). */
  t.n = (base: string, n: number) => {
    const form = plural.select(n);
    const k = `${base}.${form === "one" ? "one" : form === "few" ? "few" : "many"}` as Key;
    return fill(dict[lang][k], { n });
  };
  return t;
}
export type T = ReturnType<typeof makeT>;
