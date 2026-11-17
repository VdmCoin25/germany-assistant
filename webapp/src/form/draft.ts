import { tg } from "../tg";

export type Draft = {
  position: string; city: string; land: string | null; employment: "full" | "part" | "mini" | "any";
  shifts_ok: boolean; german_level: string | null; experience: string; about: string; step: number;
};
export const EMPTY: Draft = { position: "", city: "", land: null, employment: "any", shifts_ok: false,
  german_level: null, experience: "", about: "", step: 1 };

const KEY = "seeker_draft_v1";   // CloudStorage: up to 4096 chars per value; the draft is well below that

/** The draft lives in Telegram CloudStorage (per user, per bot), so it survives closing the app or changing phones. */
export function loadDraft(): Promise<Draft | null> {
  return new Promise((resolve) => {
    const cs = tg?.CloudStorage;
    if (!cs) return resolve(null);
    const timer = setTimeout(() => resolve(null), 3000);
    cs.getItem(KEY, (err, v) => {
      clearTimeout(timer);
      if (err || !v) return resolve(null);
      try { resolve({ ...EMPTY, ...JSON.parse(v) }); } catch { resolve(null); }
    });
  });
}
export function saveDraft(d: Draft) { tg?.CloudStorage?.setItem(KEY, JSON.stringify(d)); }
export function clearDraft() { const cs = tg?.CloudStorage; if (cs?.removeItem) cs.removeItem(KEY); else cs?.setItem(KEY, ""); }
