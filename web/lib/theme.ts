/**
 * The site's looks. Every theme shows the same pages and components; a theme only changes how they feel
 * (colours, type, shapes, a few decorations). The pick lives in a cookie so the server renders it straight
 * away (no flash of the wrong look) and each phone or laptop keeps its own.
 */
export const THEMES = {
  studio: { label: "Studio", icon: "◐", blurb: "The default: plain and clear, light or dark with your phone", color: "#f4f5f8" },
  office: { label: "Office", icon: "🕹️", blurb: "The pixel office: arcade fonts and 8-bit staff", color: "#0f0d1f" },
  clean: { label: "Clean", icon: "✨", blurb: "A calm money app: big numbers, soft cards", color: "#f6f7f9" },
  broadcast: { label: "Broadcast", icon: "📺", blurb: "Sports TV: scoreboard, ticker, play-by-play", color: "#070b18" },
  desktop: { label: "Desktop", icon: "💾", blurb: "A 1995 desktop: windows, bevels, a taskbar", color: "#008080" },
} as const;
export type ThemeKey = keyof typeof THEMES;
// "look", not "theme" (11-16): everyone starts on the redesign; old picks don't carry over
export const THEME_COOKIE = "look";
export const THEME_PREF = "look";
export const DEFAULT_THEME: ThemeKey = "studio";
export const parseTheme = (v: string | undefined | null): ThemeKey =>
  v && v in THEMES ? (v as ThemeKey) : DEFAULT_THEME;
