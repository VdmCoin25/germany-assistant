// Thin layer over the official telegram-web-app.js (window.Telegram.WebApp).
// No SDK: the object is documented at core.telegram.org/bots/webapps and is all we need.
import { useEffect, useState } from "react";

type Btn = {
  setParams(p: Record<string, unknown>): void;
  show(): void; hide(): void;
  onClick(cb: () => void): void; offClick(cb: () => void): void;
  showProgress?(leaveActive?: boolean): void; hideProgress?(): void;
};
type WebApp = {
  initData: string;
  initDataUnsafe: { user?: { id: number; language_code?: string } };
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  version: string;
  ready(): void; expand(): void; close?(): void;
  onEvent(e: string, cb: (arg?: unknown) => void): void;
  offEvent(e: string, cb: (arg?: unknown) => void): void;
  isVersionAtLeast(v: string): boolean;
  MainButton: Btn; SecondaryButton?: Btn;
  BackButton: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
  SettingsButton?: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
  HapticFeedback?: { selectionChanged(): void; notificationOccurred(t: "success" | "error" | "warning"): void; impactOccurred(s: string): void };
  CloudStorage?: { getItem(k: string, cb: (e: unknown, v?: string) => void): void; setItem(k: string, v: string, cb?: (e: unknown) => void): void };
  setHeaderColor?(c: string): void; setBackgroundColor?(c: string): void; setBottomBarColor?(c: string): void;
};

export const tg: WebApp | undefined = (window as unknown as { Telegram?: { WebApp?: WebApp } }).Telegram?.WebApp;

/** Telegram's colour scheme; follows day/night switching without a reload. */
export function useColorScheme(): "light" | "dark" {
  const [scheme, setScheme] = useState(tg?.colorScheme ?? "light");
  useEffect(() => {
    if (!tg) return;
    const on = () => setScheme(tg.colorScheme);
    tg.onEvent("themeChanged", on);
    return () => tg.offEvent("themeChanged", on);
  }, []);
  return scheme;
}

/** One main action per screen, rendered by Telegram itself at the bottom. */
export function useBottomButton(text: string | null, onClick: () => void, opts: { active?: boolean; loading?: boolean } = {}) {
  const { active = true, loading = false } = opts;
  useEffect(() => {
    const b = tg?.MainButton;
    if (!b) return;
    if (!text) { b.hide(); return; }
    b.setParams({ text, is_active: active, is_visible: true });
    if (loading) b.showProgress?.(false); else b.hideProgress?.();
    b.onClick(onClick);
    return () => { b.offClick(onClick); b.hide(); };
  }, [text, onClick, active, loading]);
}

export function useSecondaryButton(text: string | null, onClick: () => void) {
  useEffect(() => {
    const b = tg?.SecondaryButton;
    if (!b) return;
    if (!text) { b.hide(); return; }
    b.setParams({ text, is_visible: true, position: "left" });
    b.onClick(onClick);
    return () => { b.offClick(onClick); b.hide(); };
  }, [text, onClick]);
}

export function useBackButton(onBack: (() => void) | null) {
  useEffect(() => {
    const b = tg?.BackButton;
    if (!b) return;
    if (!onBack) { b.hide(); return; }
    b.show(); b.onClick(onBack);
    return () => { b.offClick(onBack); b.hide(); };
  }, [onBack]);
}

export const haptic = {
  select: () => tg?.HapticFeedback?.selectionChanged(),
  success: () => tg?.HapticFeedback?.notificationOccurred("success"),
};

/** Android puts the device class in the User-Agent (Bot API 8.0): animations off on LOW. */
export function isLowEnd(): boolean {
  return /Telegram-Android\/.*\bLOW\)?$/i.test(navigator.userAgent) || /;\s*LOW\)/.test(navigator.userAgent);
}

export function prefersStill(): boolean {
  return isLowEnd() || matchMedia("(prefers-reduced-motion: reduce)").matches;
}
