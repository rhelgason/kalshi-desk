"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { savePrefs } from "@/app/account";
import { MODE_COOKIE, MODE_PREF, THEMES, THEME_COOKIE, THEME_PREF, barColor, type Mode, type ThemeKey } from "@/lib/theme";

/** A tiny drawing of each theme (page, top bar, a card, the accent), so you can see it before you pick it. */
const PREVIEW: Record<ThemeKey, { page: string; bar: string; card: string; accent: string; line: string }> = {
  studio: { page: "#0b0d12", bar: "#151821", card: "#171a22", accent: "#3dd68c", line: "#2a2f3a" },
  office: { page: "#0f0d1f", bar: "#1d1838", card: "#221c42", accent: "#ffcc33", line: "#3a3170" },
  broadcast: { page: "#070b18", bar: "#c8102e", card: "#0f1730", accent: "#ffd23f", line: "#1d2a50" },
  desktop: { page: "#008080", bar: "#c0c0c0", card: "#c0c0c0", accent: "#000080", line: "#808080" },
};

/**
 * The theme picker on Settings (11-17): a tile per theme with a little preview, and dark or light for Studio. It
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
          const p = PREVIEW[k];
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
      {picked === "studio" && (
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
