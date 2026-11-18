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
  // Only a pull shows the pill; the quiet refresh on coming back to the app doesn't (11-18)
  const [pulled, setPulled] = useState(false);
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
      if (from.current != null && pullRef.current >= PULL) { setPulled(true); start(() => router.refresh()); }
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
  useEffect(() => { if (!pending) setPulled(false); }, [pending]);

  const busy = pending && pulled;
  const shown = busy || pull > 10;
  const offset = busy ? 0 : Math.min(pull, PULL) - PULL;
  // Hidden: fully above the screen, past the notch too (11-18: a fixed -60px left it peeking out under the status
  // bar on notched iPhones, where the top inset is ~50-60px)
  return (
    <div className="ptr" aria-live="polite" aria-hidden={!shown} style={shown
      ? { transform: `translate(-50%, ${offset * 0.6}px)` }
      : { transform: "translate(-50%, calc(-100% - env(safe-area-inset-top, 0px) - 24px))", visibility: "hidden" }}>
      {busy ? "REFRESHING…" : pull >= PULL ? "LET GO TO REFRESH" : "PULL TO REFRESH"}
    </div>
  );
}
