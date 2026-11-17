import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { HomeData, JobsState } from "./screens/Home";

type Me = { language: string | null; city: string | null; land: string | null; german_level: string | null };
export type SeekerFields = { position: string; city: string | null; land: string | null; german_level: string | null;
  employment: "full" | "part" | "mini" | "any"; shifts_ok: boolean; experience: string; about: string | null };
/** What the form starts from: the existing profile, otherwise what the user told the bot at /start. */
export type FormSeed = Partial<{ position: string; city: string; land: string | null; german_level: string | null;
  employment: SeekerFields["employment"]; shifts_ok: boolean; experience: string; about: string }>;
type Request = { kind: "offer" | "apply"; status: string };
type JobsMe = {
  seeker: ({ status: "pending" | "approved" | "rejected"; is_active: boolean } & SeekerFields) | null;
  inbox: Request[];
};

/** Maps API statuses onto the five stops of the job route (docs/redesign/J1-ux.md). */
export function jobsState(j: JobsMe): JobsState {
  if (!j.seeker) return { step: "new" };
  if (j.seeker.status === "rejected") return { step: "rejected" };
  if (j.seeker.status === "pending") return { step: "review" };
  if (!j.seeker.is_active) return { step: "paused" };          // hidden by the owner: employers cannot see or invite
  const offers = j.inbox.filter((c) => c.kind === "offer");
  const waiting = offers.filter((c) => c.status === "sent").length;
  if (waiting) return { step: "offers", waiting };
  if (offers.some((c) => c.status === "accepted")) return { step: "contact" };
  return { step: "published" };
}

export type Load<T> = { state: "loading" } | { state: "error"; status: number; code: string } | { state: "ok"; data: T };

export function useHomeData() {
  const [res, setRes] = useState<Load<HomeData & { language: string | null; seed: FormSeed }>>({ state: "loading" });
  const seq = useRef(0);   // only the latest request may update the screen
  const load = useCallback(async () => {
    const my = ++seq.current;
    setRes({ state: "loading" });
    try {
      const [me, jobs] = await Promise.all([api<Me>("/api/me"), api<JobsMe>("/api/jobs/me")]);
      if (my !== seq.current) return;
      const now = new Date();
      setRes({ state: "ok", data: {
        language: me.language,
        city: jobs.seeker?.city ?? me.city ?? null,
        land: jobs.seeker?.land ?? me.land ?? null,
        position: jobs.seeker?.position ?? null,
        updated: `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`,
        jobs: jobsState(jobs),
        seed: jobs.seeker
          ? { ...jobs.seeker, city: jobs.seeker.city ?? "", about: jobs.seeker.about ?? "" }
          : { city: me.city ?? "", land: me.land, german_level: me.german_level },
      } });
    } catch (e) {
      if (my !== seq.current) return;
      const err = e as { status?: number; code?: string };
      setRes({ state: "error", status: err.status ?? 0, code: err.code ?? "network" });
    }
  }, []);
  useEffect(() => { load(); return () => { seq.current++; }; }, [load]);
  return { res, reload: load };
}

export function useOnline() {
  const [on, setOn] = useState(navigator.onLine);
  useEffect(() => {
    const up = () => setOn(true), down = () => setOn(false);
    addEventListener("online", up); addEventListener("offline", down);
    return () => { removeEventListener("online", up); removeEventListener("offline", down); };
  }, []);
  return on;
}
