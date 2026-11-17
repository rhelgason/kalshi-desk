/**
 * The site's looks. Every theme shows the same pages and components; a theme only changes how they feel
 * (colours, type, shapes, a few decorations). The pick lives in a cookie so the server renders it straight
 * away (no flash of the wrong look) and each phone or laptop keeps its own.
 */
export const THEMES = {
  studio: { label: "Studio", icon: "◐", blurb: "Plain and clear: the default", bar: { dark: "#0b0d12", light: "#f4f5f8" } },
  office: { label: "Office", icon: "🕹️", blurb: "The pixel office: arcade type and 8-bit staff", bar: { dark: "#0f0d1f", light: "#f4f0ff" } },
  desktop: { label: "Desktop", icon: "💾", blurb: "A 1995 PC: windows, bevels, a taskbar", bar: { dark: "#0b2238", light: "#008080" } },
  terminal: { label: "Terminal", icon: "⌨️", blurb: "A trading screen: mono type, amber on black", bar: { dark: "#050505", light: "#f7f5ef" } },
} as const;
export type ThemeKey = keyof typeof THEMES;
// New names on each redesign so everyone starts on dark Studio and old picks don't carry over ("look" 11-16,
// "skin" 11-17 with the four themes); anything picked after that is remembered as usual
export const THEME_COOKIE = "skin";
export const THEME_PREF = "skin";
export const DEFAULT_THEME: ThemeKey = "studio";
export const parseTheme = (v: string | undefined | null): ThemeKey =>
  v && v in THEMES ? (v as ThemeKey) : DEFAULT_THEME;

// Light or dark (every theme since 11-17): dark unless they pick light; a phone in light mode doesn't switch it
export type Mode = "dark" | "light";
export const MODE_COOKIE = "shade";
export const MODE_PREF = "shade";
export const parseMode = (v: string | undefined | null): Mode => (v === "light" ? "light" : "dark");
/** The browser bar's colour for a look. */
export const barColor = (t: ThemeKey, m: Mode) => THEMES[t].bar[m];
