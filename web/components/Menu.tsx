"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

/**
 * The header's dropdown (11-17): a hamburger button with the list attached under it (one shape when open); closes
 * the moment you click or tap anywhere else, press Escape, pick an item, or the page changes. `label` is for screen
 * readers and the tooltip (who's signed in).
 */
export default function Menu({ label, children }: { label: string; children: React.ReactNode }) {
  const ref = useRef<HTMLDetailsElement>(null);
  const path = usePathname();
  useEffect(() => { if (ref.current) ref.current.open = false; }, [path]);
  useEffect(() => {
    const away = (e: PointerEvent) => {
      const d = ref.current;
      if (d?.open && !d.contains(e.target as Node)) d.open = false;
    };
    const esc = (e: KeyboardEvent) => {
      const d = ref.current;
      if (e.key === "Escape" && d?.open) { d.open = false; d.querySelector("summary")?.focus(); }
    };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", esc); };
  }, []);
  return (
    <details className="menu" ref={ref}
             onClick={(e) => { if ((e.target as HTMLElement).closest(".menu-list a, .menu-list button") && ref.current) ref.current.open = false; }}>
      <summary aria-label={label} title={label}>
        <svg className="menu-icon" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
          <path d="M3 5h12M3 9h12M3 13h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </summary>
      <div className="menu-list">{children}</div>
    </details>
  );
}
