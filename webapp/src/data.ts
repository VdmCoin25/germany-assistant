import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { HomeData, JobsState } from "./screens/Home";

type Me = { language: string | null; city: string | null };
type Request = { kind: "offer" | "apply"; status: string };
type JobsMe = {
  seeker: { status: "pending" | "approved" | "rejected"; is_active: boolean; position: string; city: string | null } | null;
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
  const [res, setRes] = useState<Load<HomeData & { language: string | null }>>({ state: "loading" });
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
        city: me.city ?? jobs.seeker?.city ?? null,
        position: jobs.seeker?.position ?? null,
        updated: `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`,
        jobs: jobsState(jobs),
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
