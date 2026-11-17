import { useEffect, useRef } from "react";
import { prefersStill } from "../tg";

/** What the header scene shows. Every element is driven by the user's data:
 *  rain  — waiting (profile in review, or published without offers);
 *  train — "standing": an offer has arrived and waits for an answer (pulls in and stands at the platform);
 *          "passing": nothing for you yet, trains pass by in the distance now and then;
 *  lamp  — "signal" when the user has something to do, "dim" otherwise;
 *  bench — the user's station (their city). */
export type Scene = { rain: boolean; train: "standing" | "passing"; lamp: "signal" | "dim" };

type Props = {
  scene: Scene;
  caption: string;          // e.g. "Ваші відправлення"
  meta?: string;            // e.g. "Оновлено 21:01"; hidden when absent
  station: string;          // e.g. "Berlin Hbf"
  sub?: string;             // one quiet line under the station name
  size?: "full" | "compact";
};

const SIGNAL = "255,210,63";   // --signal #FFD23F
const DIM = "214,226,245";     // cold platform light
const INK = "#0A2152";         // silhouettes, a shade darker than --board

export function Board({ scene, caption, meta, station, sub, size = "full" }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    const still = prefersStill();
    const dpr = Math.min(devicePixelRatio || 1, 2);
    let w = 0, h = 0, raf = 0, last = 0;
    let drops: { x: number; y: number; l: number; v: number; a: number }[] = [];
    const train = { start: performance.now(), arrived: still };   // pulls in once, over ~1.2 s, then stands
    const far = { x: 0, on: false, next: performance.now() + 2500 };  // distant passing train
    const light = scene.lamp === "signal" ? SIGNAL : DIM;

    const resize = () => {
      w = c.clientWidth; h = c.clientHeight;
      c.width = w * dpr; c.height = h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      drops = Array.from({ length: Math.round(w / 7) }, () => ({
        x: Math.random() * w, y: Math.random() * h, l: 7 + Math.random() * 10, v: 4 + Math.random() * 3, a: .10 + Math.random() * .16 }));
    };
    const px = () => w - 44, hx = () => px() - 26, hy = 30;

    const lamp = () => {
      const x = px(), lx = hx(), strong = scene.lamp === "signal";
      // light cone on the platform: the only gradient, it carries the lamp state
      ctx.beginPath(); ctx.moveTo(lx - 6, hy + 10); ctx.lineTo(lx + 6, hy + 10);
      ctx.lineTo(lx + 6 + (h - hy) * .5, h); ctx.lineTo(lx - 6 - (h - hy) * .5, h); ctx.closePath();
      const g = ctx.createLinearGradient(0, hy, 0, h);
      g.addColorStop(0, `rgba(${light},${strong ? .30 : .12})`); g.addColorStop(1, `rgba(${light},${strong ? .06 : .02})`);
      ctx.fillStyle = g; ctx.fill();
      ctx.fillStyle = INK;
      ctx.fillRect(x - 2, 14, 4, h - 14);
      ctx.strokeStyle = INK; ctx.lineWidth = 3; ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(x, 18); ctx.quadraticCurveTo(x - 12, 10, lx, 18); ctx.stroke();
      ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(lx, 18); ctx.lineTo(lx, hy - 6); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(lx - 10, hy - 1); ctx.lineTo(lx + 10, hy - 1); ctx.lineTo(lx + 5, hy - 7); ctx.lineTo(lx - 5, hy - 7); ctx.closePath(); ctx.fill();
      ctx.fillStyle = strong ? "#FFD23F" : "#C9D4E8";
      ctx.beginPath(); ctx.moveTo(lx - 8, hy - 1); ctx.lineTo(lx + 8, hy - 1); ctx.lineTo(lx + 5, hy + 10); ctx.lineTo(lx - 5, hy + 10); ctx.closePath(); ctx.fill();
    };
    const bench = () => {
      const x0 = px() - 60, x1 = px() - 14, seat = h - 13;
      ctx.fillStyle = INK;
      ctx.fillRect(x0, seat, x1 - x0, 3); ctx.fillRect(x0 + 1, seat - 9, x1 - x0 - 2, 2); ctx.fillRect(x0 + 1, seat - 5, x1 - x0 - 2, 2);
      ctx.fillRect(x0 + 3, seat - 10, 2, 10); ctx.fillRect(x1 - 5, seat - 10, 2, 10);
      ctx.fillRect(x0 + 3, seat + 3, 2, 10); ctx.fillRect(x1 - 5, seat + 3, 2, 10);
    };
    const drawTrain = () => {
      if (scene.train === "passing") return drawFar();
      const len = Math.min(w * .5, 220), y = h - 30, carH = 16;
      let k = 1;
      if (!train.arrived) { k = Math.min(1, (performance.now() - train.start) / 1200); if (k === 1) train.arrived = true; }
      const x = -len * (1 - k) ** 3;   // ease-out: slows to a stop at the platform
      ctx.fillStyle = "#DDE4F0"; ctx.fillRect(x, y, len, carH);
      ctx.beginPath(); ctx.moveTo(x + len, y); ctx.quadraticCurveTo(x + len + 16, y + 2, x + len + 18, y + carH); ctx.lineTo(x + len, y + carH); ctx.closePath(); ctx.fill();
      ctx.fillStyle = `rgba(${SIGNAL},.95)`;
      for (let i = 8; i < len - 6; i += 12) { if (i % 72 > 62) continue; ctx.fillRect(x + i, y + 3, 7, 5); }
      ctx.fillStyle = INK; for (let i = 72; i < len; i += 72) ctx.fillRect(x + i - 1, y, 2, carH);
    };
    // A small regional train crossing the horizon; never on weak devices or with reduced motion.
    const drawFar = () => {
      if (still) return;
      const now = performance.now(), len = Math.min(w * .55, 230), y = h - 44, carH = 7;
      if (!far.on && now > far.next) { far.on = true; far.x = -len - 20; }
      if (!far.on) return;
      ctx.save(); ctx.globalAlpha = .6;
      ctx.fillStyle = "#DDE4F0"; ctx.fillRect(far.x, y, len, carH);
      ctx.beginPath(); ctx.moveTo(far.x + len, y); ctx.quadraticCurveTo(far.x + len + 12, y + 1, far.x + len + 14, y + carH);
      ctx.lineTo(far.x + len, y + carH); ctx.closePath(); ctx.fill();
      ctx.fillStyle = `rgba(${SIGNAL},.9)`;
      for (let i = 5; i < len - 4; i += 8) { if (i % 58 > 50) continue; ctx.fillRect(far.x + i, y + 2, 4, 2.5); }
      ctx.restore();
      far.x += 3.2;
      if (far.x > w + 20) { far.on = false; far.next = now + 9000 + Math.random() * 12000; }
    };
    const rain = () => {
      if (!scene.rain) return;
      ctx.lineWidth = 1; ctx.lineCap = "round";
      for (const d of drops) {
        ctx.strokeStyle = `rgba(255,255,255,${d.a})`;
        ctx.beginPath(); ctx.moveTo(d.x, d.y); ctx.lineTo(d.x - d.l * .18, d.y + d.l); ctx.stroke();
        if (!still) { d.y += d.v; d.x -= d.v * .18; if (d.y > h) { d.y = -d.l; d.x = Math.random() * (w + 20); } }
      }
    };
    const draw = () => { ctx.clearRect(0, 0, w, h); drawTrain(); lamp(); bench(); rain(); };

    resize(); draw();
    const onResize = () => { resize(); draw(); };
    addEventListener("resize", onResize);
    const animate = !still;
    if (animate) {
      const frame = (ts: number) => {
        raf = requestAnimationFrame(frame);
        if (document.hidden || ts - last < 33) return;
        last = ts; draw();
        if (!scene.rain && scene.train === "standing" && train.arrived) cancelAnimationFrame(raf);   // the train has stopped: nothing moves any more
      };
      raf = requestAnimationFrame(frame);
    }
    return () => { cancelAnimationFrame(raf); removeEventListener("resize", onResize); };
  }, [scene.rain, scene.train, scene.lamp]);

  return (
    <header className={`board board--${size}`}>
      <canvas ref={ref} aria-hidden="true" />
      <div className="board__row"><span>{caption}</span>{meta && <span className="board__meta">{meta}</span>}</div>
      <h1 className="board__station">{station}</h1>
      {sub && <p className="board__sub">{sub}</p>}
    </header>
  );
}
