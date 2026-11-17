"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { savePrefs } from "@/app/account";
import { MODE_COOKIE, MODE_PREF, THEMES, THEME_COOKIE, THEME_PREF, barColor, type Mode, type ThemeKey } from "@/lib/theme";

/** The look picker on the settings page: switches at once, remembered on this device for a year (and with their login). */
export default function ThemePicker({ current, mode }: { current: ThemeKey; mode: Mode }) {
  const [picked, setPicked] = useState(current);
  const [shade, setShade] = useState(mode);
  const router = useRouter();
  const remember = (cookie: string, pref: string, v: string, t: ThemeKey, m: Mode) => {
    document.cookie = `${cookie}=${v}; path=/; max-age=${365 * 86_400}; samesite=lax`;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", barColor(t, m));
    savePrefs({ [pref]: v }).catch(() => null); // signed in: their other devices get it too
    router.refresh(); // server-drawn bits (e.g. the taskbar clock's label) follow
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
    <div className="theme-picker" role="group" aria-label="Look">
      <div className="theme-picker-label">Look</div>
      <div className="theme-picker-grid">
        {(Object.keys(THEMES) as ThemeKey[]).map((k) => (
          <button key={k} type="button" className={`theme-opt theme-opt-${k}`} aria-pressed={picked === k}
                  onClick={() => pick(k)} title={THEMES[k].blurb}>
            <span aria-hidden>{THEMES[k].icon}</span> {THEMES[k].label}
          </button>
        ))}
      </div>
      {picked === "studio" && (
        <>
          <div className="theme-picker-label">Colours</div>
          <div className="theme-picker-grid">
            {(["dark", "light"] as Mode[]).map((m) => (
              <button key={m} type="button" className="theme-opt" aria-pressed={shade === m} onClick={() => pickMode(m)}>
                <span aria-hidden>{m === "dark" ? "🌙" : "☀️"}</span> {m === "dark" ? "Dark" : "Light"}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
