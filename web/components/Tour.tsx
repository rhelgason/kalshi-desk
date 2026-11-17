"use client";

import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { savePrefs } from "@/app/account";

/**
 * The new-user experience, part two (11-17): a guided tour of the app right after Kalshi is connected. One thing at
 * a time is lit and outlined, the rest of the screen dimmed and unclickable; the person taps the lit thing (or Next,
 * for a look-only step). Where they are is saved with their login (prefs.nux), so leaving the app mid-tour picks up
 * at the same step on any device until they finish. `preview`: the manager's run-through, kept on this device only.
 *
 * Steps that want a page (`at`) send the person there if they come back somewhere else; steps that need the step
 * before them (the open menu, the employee they tapped) go `back` to it instead.
 */
type Step = {
  at: RegExp; go?: string; back?: number; target?: string; title: string; body: string;
  /** tapping the lit thing is the step; `fake`: the tap is shown, not done (the pause button) */
  click?: boolean; fake?: boolean; wait?: string;
  /** an item in the open menu: if it isn't showing, the menu was closed, so go `back` at once */
  quick?: boolean;
};

const STEPS: Step[] = [
  { at: /^\/$/, go: "/", target: ".money-hero", title: "This is your money",
    body: "Everything in your office: cash on Kalshi plus the bets riding right now. The number only moves when a bet settles, and the chart shows the story so far.",
    wait: "Your office is opening: it takes a couple of minutes after connecting Kalshi. This page refreshes itself, and the tour carries on when it's ready." },
  { at: /^\/$/, go: "/", target: ".team li a", click: true, title: "Meet your staff",
    body: "Each employee is a bot with one job, like bitcoin's 15-minute markets. Tap one to see their page." },
  { at: /^\/employee\//, back: 1, target: ".employee-chart", title: "An employee's page",
    body: "How they've done, the bets they have riding, and their level: Intern, Associate, Senior, VP. Every week the office reviews itself: good employees get promoted to bigger bets, and weak ones get benched. You don't have to do anything." },
  { at: /./, target: '.nav a[href="/cockpit"]', click: true, title: "The cockpit", body: "Next, tap Cockpit." },
  { at: /^\/cockpit/, go: "/cockpit", target: ".cockpit-main", title: "Every office together",
    body: "Everyone's offices on one chart, as a % return. Below it, \"Is it working?\" adds up every office's bets: the honest answer, since one office can be lucky for a few days but all of them over weeks can't." },
  { at: /./, target: ".menu > summary", click: true, title: "The menu", body: "Settings and Office Rules live in the menu. Tap it to open it." },
  { at: /./, back: 5, quick: true, target: '.menu-list a[href="/rules"]', click: true, title: "Office Rules", body: "Tap Office Rules." },
  { at: /^\/rules/, go: "/rules", target: '[data-tour="pause"]', click: true, fake: true, title: "Your pause button",
    body: "This button pauses your betting (while betting is paused, it says Resume instead). Tap it to see what it does." },
  { at: /^\/rules/, go: "/rules", target: '[data-tour="pause"]', title: "That's how you pause",
    body: "For real, it stops new bets within 2 minutes; bets already on finish as usual, and the button turns into Resume. We didn't pause anything just now. Want to stop for good? Delete the key on Kalshi." },
  { at: /./, target: ".menu > summary", click: true, title: "Last stop", body: "Open the menu again." },
  { at: /./, back: 9, quick: true, target: '.menu-list a[href="/settings"]', click: true, title: "Settings", body: "Tap Settings." },
  { at: /^\/settings/, go: "/settings", target: ".theme-tiles", click: true, title: "Pick a look",
    body: "Four styles, each in dark or light. Tap one you like; you can change it any time." },
  { at: /./, title: "You're all set! 🎉",
    body: "That's the whole office, and it runs itself. Haven't put money in yet? Deposit on Kalshi whenever you like: the office notices within about 10 minutes and the staff start betting. Small bets, many times a day." },
];

const PREVIEW = "nux-preview";
const PAD = 6;
type Box = { top: number; left: number; width: number; height: number };

const visible = (el: Element | null): el is HTMLElement => {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};

export default function Tour({ start }: { start: number | null }) {
  const router = useRouter();
  const path = usePathname();
  const [step, setStep] = useState<number | null>(start);
  const [preview, setPreview] = useState(false);
  const [box, setBox] = useState<Box | null>(null);
  const [missing, setMissing] = useState(false);
  const [disabled, setDisabled] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const [cardH, setCardH] = useState(180);

  // The manager's preview lives on this device only (looked for again on each page: it starts from /welcome)
  useEffect(() => {
    if (start != null || preview) return;
    try {
      const v = localStorage.getItem(PREVIEW);
      if (v != null && /^\d+$/.test(v)) { setPreview(true); setStep(Number(v)); }
    } catch {}
  }, [start, preview, path]);

  const save = useCallback((n: number | "done") => {
    if (preview) {
      try { if (n === "done") localStorage.removeItem(PREVIEW); else localStorage.setItem(PREVIEW, String(n)); } catch {}
    } else {
      savePrefs({ nux: String(n) }).catch(() => {});
    }
  }, [preview]);

  const moveTo = useCallback((n: number) => { setStep(n); setBox(null); save(n); }, [save]);
  const finish = useCallback(() => { save("done"); setStep(null); if (path !== "/") router.push("/"); }, [save, path, router]);

  const s = step != null ? STEPS[Math.min(step, STEPS.length - 1)] : null;

  // On the wrong page: after a moment (navigations take one), go there, or back to the step that leads there
  useEffect(() => {
    if (!s || s.at.test(path)) return;
    const t = setTimeout(() => {
      if (s.back != null) moveTo(s.back);
      else if (s.go) router.push(s.go);
    }, 1500);
    return () => clearTimeout(t);
  }, [s, path, router, moveTo]);

  // Follow the lit element as the page scrolls, resizes and loads
  useLayoutEffect(() => {
    if (!s?.target || !s.at.test(path)) { setBox(null); setMissing(false); return; }
    let raf = 0, since = performance.now(), scrolled = false;
    const tick = () => {
      const el = document.querySelector(s.target!);
      if (visible(el)) {
        if (!scrolled) { el.scrollIntoView({ block: "center", behavior: "smooth" }); scrolled = true; }
        const r = el.getBoundingClientRect();
        setBox((b) => (b && b.top === r.top && b.left === r.left && b.width === r.width && b.height === r.height ? b
          : { top: r.top, left: r.left, width: r.width, height: r.height }));
        setMissing(false);
        setDisabled((el as HTMLButtonElement).disabled === true);
        since = performance.now();
      } else {
        setBox(null);
        const waited = performance.now() - since;
        if (waited > 1200) {
          // a slow page gets time to load before going back a step; a closed menu doesn't
          if (s.back != null && (s.quick || waited > 10_000)) { moveTo(s.back); return; }
          setMissing(true);
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [s, path, moveTo]);

  // Taps on the lit element: the step's action. Everything else is behind the dimmed panels.
  useEffect(() => {
    if (!s?.click || step == null) return;
    const onClick = (e: MouseEvent) => {
      const el = document.querySelector(s.target!);
      if (!el || !el.contains(e.target as Node)) return;
      if (s.fake) { e.preventDefault(); e.stopPropagation(); }
      moveTo(step + 1);
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [s, step, moveTo]);

  useLayoutEffect(() => { if (cardRef.current) setCardH(cardRef.current.offsetHeight); }, [step, box, missing]);

  if (!s || step == null) return null;
  const last = step >= STEPS.length - 1;
  // Next only once the lit thing is showing, so nobody skips a step while the page is still loading
  const showNext = (!s.click && (!s.target || !!box || missing)) || disabled || (s.click && missing && !s.wait);
  const W = typeof window === "undefined" ? 400 : window.innerWidth, H = typeof window === "undefined" ? 800 : window.innerHeight;

  // The hole: the lit element plus a little room. No hole (a look-only step or nothing to light): dim everything.
  const hole = box ? { top: box.top - PAD, left: box.left - PAD, width: box.width + PAD * 2, height: box.height + PAD * 2 } : null;
  const card: React.CSSProperties = { left: 16, right: 16 };
  if (!hole) Object.assign(card, { top: Math.max(16, (H - cardH) / 2) });
  else {
    const width = Math.min(360, W - 32);
    card.left = Math.min(Math.max(16, hole.left), W - 16 - width);
    card.right = "auto";
    card.width = width;
    if (hole.top + hole.height + 12 + cardH < H - 8) card.top = hole.top + hole.height + 12;
    else if (hole.top - 12 - cardH > 8) card.top = hole.top - 12 - cardH;
    else card.bottom = 16;
  }
  // A look-only step's hole is still covered (nothing to tap but Next)
  const covered = !s.click || !hole;

  return (
    <div className="tour" role="dialog" aria-modal="true" aria-label={s.title}>
      {hole ? (
        <>
          <div className="tour-dim" style={{ top: 0, left: 0, right: 0, height: Math.max(0, hole.top) }} />
          <div className="tour-dim" style={{ top: hole.top + hole.height, left: 0, right: 0, bottom: 0 }} />
          <div className="tour-dim" style={{ top: hole.top, left: 0, width: Math.max(0, hole.left), height: hole.height }} />
          <div className="tour-dim" style={{ top: hole.top, left: hole.left + hole.width, right: 0, height: hole.height }} />
          {covered && <div className="tour-block" style={hole} />}
          <div className="tour-ring" style={hole} data-tap={s.click ? "" : undefined} />
        </>
      ) : (
        <div className="tour-dim" style={{ inset: 0 }} />
      )}
      <div className="tour-card" ref={cardRef} style={card}>
        <div className="tour-top">
          <span className="muted small">{last ? "Tour done" : `Tour · ${step + 1} of ${STEPS.length - 1}`}</span>
          {preview && <button type="button" className="link-btn small" onClick={finish}>End preview</button>}
        </div>
        <h3>{s.title}</h3>
        <p>{missing && s.wait ? s.wait : s.body}</p>
        {s.click && hole && !disabled && <p className="tour-tap small">👆 Tap the highlighted {s.target === ".theme-tiles" ? "style" : "spot"}</p>}
        {last ? (
          <button type="button" className="btn primary" onClick={finish}>Go to my office</button>
        ) : showNext && !(missing && s.wait) ? (
          <button type="button" className="btn primary" onClick={() => moveTo(step + 1)}>Next</button>
        ) : null}
      </div>
    </div>
  );
}
