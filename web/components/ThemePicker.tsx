"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { savePrefs } from "@/app/account";
import { MODE_COOKIE, MODE_PREF, THEMES, THEME_COOKIE, THEME_PREF, barColor, type Mode, type ThemeKey } from "@/lib/theme";

type Swatch = { page: string; bar: string; card: string; accent: string; line: string };
/** A tiny drawing of each theme in dark and light (page, top bar, a card, the accent), to see it before picking. */
const PREVIEW: Record<ThemeKey, Record<Mode, Swatch>> = {
  studio: {
    dark: { page: "#0b0d12", bar: "#15181f", card: "#15181f", accent: "#2fd39a", line: "#252a36" },
    light: { page: "#f4f5f8", bar: "#ffffff", card: "#ffffff", accent: "#0b9e6f", line: "#e5e8ee" },
  },
  office: {
    dark: { page: "#0f0d1f", bar: "#1b1733", card: "#1b1733", accent: "#4cc9f0", line: "#3a3263" },
    light: { page: "#f4f0ff", bar: "#ffffff", card: "#ffffff", accent: "#0b8fc2", line: "#c7bcef" },
  },
  desktop: {
    dark: { page: "#0b2238", bar: "#000080", card: "#2b2d31", accent: "#6ea8ff", line: "#5c6068" },
    light: { page: "#008080", bar: "#000080", card: "#c0c0c0", accent: "#000080", line: "#808080" },
  },
  terminal: {
    dark: { page: "#050505", bar: "#0d0d0c", card: "#0d0d0c", accent: "#ffb000", line: "#2a2925" },
    light: { page: "#f7f5ef", bar: "#fffefa", card: "#fffefa", accent: "#b36b00", line: "#d8d2c3" },
  },
};

/**
 * The theme picker on Settings (11-17): a tile per theme with a little preview, and dark or light for any of them. It
 * switches at once, this device remembers it for a year, and someone signed in has it saved with their login,
 * so every device of theirs follows.
 */
export default function ThemePicker({ current, mode }: { current: ThemeKey; mode: Mode }) {
  const [picked, setPicked] = useState(current);
  const [shade, setShade] = useState(mode);
  const router = useRouter();
  const remember = (cookie: string, pref: string, v: string, t: ThemeKey, m: Mode) => {
    document.cookie = `${cookie}=${v}; path=/; max-age=${365 * 86_400}; samesite=lax`;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", barColor(t, m));
    // Saved with their login first, then the page redrawn (a redraw before the save would bring the old theme back)
    savePrefs({ [pref]: v }).catch(() => null).finally(() => router.refresh());
  };
  const pick = (k: ThemeKey) => {
    setPicked(k);
    document.documentElement.dataset.theme = k;
    remember(THEME_COOKIE, THEME_PREF, k, k, shade);
  };
  const pickMode = (m: Mode) => {
    setShade(m);
    document.documentElement.dataset.mode = m;
    remember(MODE_COOKIE, MODE_PREF, m, picked, m);
  };
  return (
    <div className="theme-picker">
      <div className="theme-tiles" role="radiogroup" aria-label="Theme">
        {(Object.keys(THEMES) as ThemeKey[]).map((k) => {
          const p = PREVIEW[k][shade];
          return (
            <button key={k} type="button" role="radio" aria-checked={picked === k} className="theme-tile" onClick={() => pick(k)}>
              <span className="theme-preview" aria-hidden style={{ background: p.page }}>
                <span className="tp-bar" style={{ background: p.bar }} />
                <span className="tp-card" style={{ background: p.card, borderColor: p.line }}>
                  <span className="tp-line" style={{ background: p.accent }} />
                  <span className="tp-line short" style={{ background: p.line }} />
                </span>
              </span>
              <span className="theme-name">{THEMES[k].label}{picked === k && <span className="theme-check" aria-hidden>✓</span>}</span>
              <span className="theme-blurb">{THEMES[k].blurb}</span>
            </button>
          );
        })}
      </div>
      {(
        <div className="segmented" role="radiogroup" aria-label="Dark or light">
          {(["dark", "light"] as Mode[]).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={shade === m} onClick={() => pickMode(m)}>
              {m === "dark" ? "🌙 Dark" : "☀️ Light"}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
