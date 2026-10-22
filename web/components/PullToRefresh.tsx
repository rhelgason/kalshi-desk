"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

const PULL = 80; // px of pull that counts as "refresh"
const AWAY_MS = 30_000; // back after this long: the numbers are stale, fetch new ones

/**
 * The home-screen app has no Safari reload button, so:
 *  - pull down from the top of the page to refresh, and
 *  - coming back to the app (it stays asleep in the background) refreshes by itself.
 */
export default function PullToRefresh() {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [pull, setPull] = useState(0);
  const from = useRef<number | null>(null);
  const pullRef = useRef(0);

  useEffect(() => {
    let hiddenAt = 0;
    const onVisible = () => {
      if (document.visibilityState === "hidden") hiddenAt = Date.now();
      else if (hiddenAt && Date.now() - hiddenAt > AWAY_MS) start(() => router.refresh());
    };
    document.addEventListener("visibilitychange", onVisible);

    // Safari has its own pull-to-refresh; only the home-screen app needs ours
    const app = window.matchMedia("(display-mode: standalone)").matches || (navigator as { standalone?: boolean }).standalone;
    const down = (e: TouchEvent) => { from.current = window.scrollY <= 0 ? e.touches[0].clientY : null; };
    const move = (e: TouchEvent) => {
      if (from.current == null) return;
      pullRef.current = Math.max(0, Math.min(e.touches[0].clientY - from.current, PULL * 1.5));
      setPull(pullRef.current);
    };
    const up = () => {
      if (from.current != null && pullRef.current >= PULL) start(() => router.refresh());
      from.current = null;
      pullRef.current = 0;
      setPull(0);
    };
    if (app) {
      window.addEventListener("touchstart", down, { passive: true });
      window.addEventListener("touchmove", move, { passive: true });
      window.addEventListener("touchend", up);
      window.addEventListener("touchcancel", up);
    }
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("touchstart", down);
      window.removeEventListener("touchmove", move);
      window.removeEventListener("touchend", up);
      window.removeEventListener("touchcancel", up);
    };
  }, [router]);

  const shown = pending || pull > 10;
  const offset = pending ? 0 : Math.min(pull, PULL) - PULL;
  return (
    <div className="ptr" aria-live="polite" style={{ transform: `translate(-50%, ${shown ? offset * 0.6 : -60}px)` }}>
      {pending ? "REFRESHING…" : pull >= PULL ? "LET GO TO REFRESH" : "PULL TO REFRESH"}
    </div>
  );
}
