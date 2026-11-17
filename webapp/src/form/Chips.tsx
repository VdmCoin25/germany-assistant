import type { KeyboardEvent } from "react";
import { haptic } from "../tg";

type Props<V extends string> = {
  label: string;
  options: { value: V; text: string }[];
  value: V | null;
  onChange: (v: V) => void;
};

/** Large single-choice options instead of a dropdown: one tap, readable, 48 px tall. ARIA radio group. */
export function Chips<V extends string>({ label, options, value, onChange }: Props<V>) {
  const sel = Math.max(0, options.findIndex((o) => o.value === value));
  // Radio-group keyboard pattern: one tab stop, arrows move and select.
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const i = (sel + step + options.length) % options.length;
    onChange(options[i].value);
    (e.currentTarget.children[i] as HTMLElement | undefined)?.focus();
  };
  return (
    <div className="chips" role="radiogroup" aria-label={label} onKeyDown={onKey}>
      {options.map((o, i) => (
        <button key={o.value} type="button" role="radio" aria-checked={o.value === value} tabIndex={i === sel ? 0 : -1}
                className={o.value === value ? "chip chip--on" : "chip"}
                onClick={() => { haptic.select(); onChange(o.value); }}>
          {o.text}
        </button>
      ))}
    </div>
  );
}
