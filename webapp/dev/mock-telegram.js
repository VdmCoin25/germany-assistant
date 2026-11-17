// Development / screenshot stand-in for telegram-web-app.js. Never shipped.
// Theme values approximate Telegram for iOS defaults; initData is a fake test string.
(() => {
  const scheme = new URLSearchParams(location.search).get("scheme") === "dark" ? "dark" : "light";
  const themes = {
    light: { bg_color: "#ffffff", secondary_bg_color: "#efeff4", section_bg_color: "#ffffff", text_color: "#000000",
      hint_color: "#8e8e93", subtitle_text_color: "#8e8e93", section_header_text_color: "#6d6d72", link_color: "#007aff",
      accent_text_color: "#007aff", button_color: "#007aff", button_text_color: "#ffffff", destructive_text_color: "#ff3b30",
      section_separator_color: "#c8c7cc", header_bg_color: "#f8f8f8", bottom_bar_bg_color: "#f8f8f8" },
    dark: { bg_color: "#000000", secondary_bg_color: "#000000", section_bg_color: "#1c1c1d", text_color: "#ffffff",
      hint_color: "#98989e", subtitle_text_color: "#98989e", section_header_text_color: "#8d8e93", link_color: "#3e88f7",
      accent_text_color: "#3e88f7", button_color: "#3e88f7", button_text_color: "#ffffff", destructive_text_color: "#eb5545",
      section_separator_color: "#545458", header_bg_color: "#1a1a1a", bottom_bar_bg_color: "#1d1d1d" },
  };
  const tp = themes[scheme];
  // Init scripts run before <html> exists: apply the CSS variables as soon as it does.
  const applyVars = () => {
    const root = document.documentElement && document.documentElement.style;
    if (!root) return requestAnimationFrame(applyVars);
    for (const [k, v] of Object.entries(tp)) root.setProperty(`--tg-theme-${k.replace(/_/g, "-")}`, v);
    root.setProperty("--tg-viewport-stable-height", innerHeight + "px");
  };
  if (document.documentElement) applyVars(); else document.addEventListener("readystatechange", applyVars, { once: true });

  function makeButton(kind) {
    const s = { text: "", is_visible: false, is_active: true, cbs: new Set() };
    const render = () => {
      let bar = document.getElementById("tg-bottom-bar");
      if (!bar) {
        bar = document.createElement("div"); bar.id = "tg-bottom-bar";
        bar.style.cssText = `position:fixed;left:0;right:0;bottom:0;display:flex;gap:8px;padding:8px 12px 20px;z-index:99;background:${tp.bottom_bar_bg_color};font:600 16px system-ui,-apple-system,Roboto,sans-serif`;
        document.body.appendChild(bar);
      }
      let el = document.getElementById("tg-" + kind);
      if (!el) { el = document.createElement("button"); el.id = "tg-" + kind; el.onclick = () => s.cbs.forEach((f) => f()); bar[kind === "secondary" ? "prepend" : "append"](el); }
      el.textContent = s.text;
      el.style.cssText = `flex:1;border:0;border-radius:10px;padding:14px;font:inherit;display:${s.is_visible ? "block" : "none"};` +
        (kind === "main" ? `background:${tp.button_color};color:${tp.button_text_color};opacity:${s.is_active ? 1 : .5}` : `background:transparent;color:${tp.button_color}`);
      el.dataset.visible = s.is_visible ? "1" : "";
      bar.style.display = bar.querySelector("button[data-visible='1']") ? "flex" : "none";
      document.body.style.paddingBottom = bar.style.display === "flex" ? "76px" : "0";
    };
    return {
      setParams(p) { Object.assign(s, p); render(); }, show() { s.is_visible = true; render(); }, hide() { s.is_visible = false; render(); },
      onClick(f) { s.cbs.add(f); }, offClick(f) { s.cbs.delete(f); }, showProgress() {}, hideProgress() {},
    };
  }
  const noop = () => {};
  window.Telegram = { WebApp: {
    initData: window.__TG_INIT_DATA__ ?? "query_id=TEST&user=%7B%22id%22%3A2001%7D&auth_date=0&hash=test", version: "9.5",
    initDataUnsafe: { user: { id: window.__TG_USER__ ?? 2001, language_code: window.__TG_LANG__ ?? "uk" } }, colorScheme: scheme, themeParams: tp,
    ready: noop, expand: noop, onEvent: noop, offEvent: noop, isVersionAtLeast: () => true,
    MainButton: makeButton("main"), SecondaryButton: makeButton("secondary"),
    BackButton: { show: noop, hide: noop, onClick: noop, offClick: noop },
    SettingsButton: { show: noop, hide: noop, onClick: noop, offClick: noop },
    HapticFeedback: { selectionChanged: noop, notificationOccurred: noop, impactOccurred: noop },
    CloudStorage: (() => { const store = window.__TG_CLOUD__ || (window.__TG_CLOUD__ = {});
      return { getItem: (k, cb) => cb(null, store[k] || ""), setItem: (k, v, cb) => { store[k] = v; cb && cb(null); } }; })(),
  } };
})();
