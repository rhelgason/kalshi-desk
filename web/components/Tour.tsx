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
  at: RegExp; go?: string; back?: number; target?: string; title: string;
  /** the words; a function reads the lit element (the estimate on "Is it working?") */
  body: string | ((el: Element | null) => string);
  /** tapping the lit thing is the step; `end`: that tap also finishes the tour (the theme picker) */
  click?: boolean; end?: boolean; wait?: string;
  /** an item in the open menu: if it isn't showing, the menu was closed, so go `back` at once */
  quick?: boolean;
};

const money = (n: string | undefined) => `$${Number(n ?? 0).toLocaleString("en-US")}`;

const STEPS: Step[] = [
  { at: /^\/$/, go: "/", target: ".money-hero", title: "This is your dashboard",
    body: "A quick look at how your office is performing. The number only moves when a bet settles, and the chart shows the story so far.",
    wait: "Your office is opening: it takes a couple of minutes after connecting Kalshi. This page refreshes itself, and the tour carries on when it's ready." },
  { at: /^\/$/, go: "/", target: ".race", title: "Bets riding now",
    body: "Bets your staff have open right now, waiting to settle (most settle within 15 minutes). It stays empty until your money is in and the first bets go on." },
  { at: /^\/$/, go: "/", target: ".team li a", click: true, title: "Meet your staff",
    body: "Each employee is a bot with one job, like bitcoin's 15-minute markets. Tap one to see their page." },
  { at: /^\/employee\//, back: 2, target: ".employee-chart", title: "An employee's page",
    body: "How they've done, the bets they have riding, and their level: Intern, Associate, Senior, VP. Every week the office reviews itself: good employees get promoted to bigger bets, and weak ones get benched. You don't have to do anything." },
  { at: /./, target: '.nav a[href="/cockpit"]', click: true, title: "The cockpit", body: "Next, tap Cockpit." },
  { at: /^\/cockpit/, go: "/cockpit", target: ".cockpit-main", title: "Every office together",
    body: "Every office's return on one chart, as a %. Yours joins it once your staff start betting." },
  { at: /^\/cockpit/, go: "/cockpit", target: ".is-working", title: "Is it working?",
    body: (el) => {
      const d = (el?.querySelector(".working-estimate") as HTMLElement | null)?.dataset ?? {};
      const est = d.has
        ? `With your ${money(d.base)} deposited, our estimate puts you at about ${money(d.later)} in 6 months.`
        : `If you put $100 in today, our estimate puts you at about ${money(d.later)} in 6 months.`;
      return `The honest answer: every office's bets added up, how often they win, and the odds it's skill rather than luck. ${est} That's a rough guess at half the pace so far, not a promise.`;
    } },
  { at: /./, target: ".menu > summary", click: true, title: "The menu", body: "Settings and Office Rules live in the menu. Tap it to open it." },
  { at: /./, back: 7, quick: true, target: '.menu-list a[href="/rules"]', click: true, title: "Office Rules", body: "Tap Office Rules." },
  { at: /^\/rules/, go: "/rules", target: '[data-tour="pause"]', title: "Pausing",
    body: "Pause my betting stops your office's new bets until you resume (bets already on finish as usual), and Stop all trading is the manager's switch that pauses every office at once." },
  { at: /./, target: ".menu > summary", click: true, title: "Last stop", body: "Open the menu again." },
  { at: /./, back: 10, quick: true, target: '.menu-list a[href="/settings"]', click: true, title: "Settings", body: "Tap Settings." },
  { at: /^\/settings/, go: "/settings", target: ".theme-tiles", click: true, end: true, title: "Pick a look",
    body: "Pick a style you like, and try a few. Tap My Office whenever you want to go back to your dashboard." },
];

const PREVIEW = "nux-preview";
const PAD = 6;
/** where the lit element is; `clip`: the bottom of the sticky header, which the outline never draws over */
type Box = { top: number; left: number; width: number; height: number; clip: number };

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
  // Done: they stay where they are (the theme picker, to try a few looks); the preview's day-one office ends too
  const finish = useCallback(() => {
    save("done"); setStep(null);
    if (preview) { document.cookie = "nux_fresh=; path=/; max-age=0"; router.refresh(); }
  }, [save, preview, router]);

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
        const bar = document.querySelector(".topbar");
        const clip = bar && !bar.contains(el) && getComputedStyle(bar).position !== "static" ? bar.getBoundingClientRect().bottom : 0;
        setBox((b) => (b && b.top === r.top && b.left === r.left && b.width === r.width && b.height === r.height && b.clip === clip ? b
          : { top: r.top, left: r.left, width: r.width, height: r.height, clip }));
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
      if (s.end) finish();
      else moveTo(step + 1);
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [s, step, moveTo, finish]);

  useLayoutEffect(() => { if (cardRef.current) setCardH(cardRef.current.offsetHeight); }, [step, box, missing]);

  if (!s || step == null) return null;
  // Next only once the lit thing is showing, so nobody skips a step while the page is still loading
  const showNext = (!s.click && (!s.target || !!box || missing)) || disabled || (s.click && missing && !s.wait);
  const W = typeof window === "undefined" ? 400 : window.innerWidth, H = typeof window === "undefined" ? 800 : window.innerHeight;

  // The hole: the lit element plus a little room. No hole (a look-only step or nothing to light): dim everything.
  // Scrolled partly under the sticky header: the hole (and its outline) starts below it; fully under: no hole
  const top = box ? Math.max(box.top - PAD, box.clip) : 0, bottom = box ? box.top + box.height + PAD : 0;
  const hole = box && bottom - top > 8 ? { top, left: box.left - PAD, width: box.width + PAD * 2, height: bottom - top } : null;
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
          <span className="muted small">Tour · {step + 1} of {STEPS.length}</span>
          {preview && <button type="button" className="link-btn small" onClick={finish}>End preview</button>}
        </div>
        <h3>{s.title}</h3>
        <p>{missing && s.wait ? s.wait
          : typeof s.body === "function" ? s.body(typeof document === "undefined" || !s.target ? null : document.querySelector(s.target)) : s.body}</p>
        {showNext && !(missing && s.wait) ? (
          <button type="button" className="btn primary" onClick={() => moveTo(step + 1)}>Next</button>
        ) : null}
      </div>
    </div>
  );
}
