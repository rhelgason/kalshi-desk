"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { THEMES, THEME_COOKIE, type ThemeKey } from "@/lib/theme";

/** The look picker in the ☰ menu: switches at once, remembered on this device for a year. */
export default function ThemePicker({ current }: { current: ThemeKey }) {
  const [picked, setPicked] = useState(current);
  const router = useRouter();
  const pick = (k: ThemeKey) => {
    setPicked(k);
    document.documentElement.dataset.theme = k;
    document.cookie = `${THEME_COOKIE}=${k}; path=/; max-age=${365 * 86_400}; samesite=lax`;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEMES[k].color);
    router.refresh(); // server-drawn bits (e.g. the taskbar clock's label) follow
  };
  return (
    <div className="theme-picker" role="group" aria-label="Look">
      <div className="theme-picker-label">🎨 Look</div>
      <div className="theme-picker-grid">
        {(Object.keys(THEMES) as ThemeKey[]).map((k) => (
          <button key={k} type="button" className={`theme-opt theme-opt-${k}`} aria-pressed={picked === k}
                  onClick={() => pick(k)} title={THEMES[k].blurb}>
            <span aria-hidden>{THEMES[k].icon}</span> {THEMES[k].label}
          </button>
        ))}
      </div>
    </div>
  );
}
