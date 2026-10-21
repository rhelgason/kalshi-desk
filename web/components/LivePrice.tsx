"use client";

import { useEffect, useRef, useState } from "react";
import type { RidingBet } from "@/lib/bets";
import { dollars, shortName } from "@/lib/format";
import { niceTicks } from "./useWidth";

/**
 * The coin's live price as a smooth, always-moving line (like Kalshi's own
 * chart), with every open bet's target drawn across it: at a glance, what's
 * riding on the line right now and which side of it the price is on.
 *
 * Prices stream straight from Coinbase's free public feed in the browser (no
 * key, nothing through our server). Kalshi settles on the CF Benchmarks index,
 * which Coinbase is the biggest part of, so this is close but not exact.
 */

type Coin = "BTC" | "ETH";
type Tick = { t: number; p: number };

const PRODUCT: Record<Coin, string> = { BTC: "BTC-USD", ETH: "ETH-USD" };
const NAME: Record<Coin, string> = { BTC: "Bitcoin", ETH: "Ether" };
const PAST = 12 * 60_000; // how much history the line shows
const MAX_AHEAD = 8 * 60_000; // room to the right for the next bet's finish line
const HEIGHT = 230;
const PAD = { l: 8, r: 70, t: 14, b: 24 };

const clock = (t: number) => new Date(t).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
const left = (ms: number) => {
  const s = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
const price = (p: number, step = 1) =>
  `$${p.toLocaleString("en-US", { minimumFractionDigits: step < 1 ? 2 : 0, maximumFractionDigits: step < 1 ? 2 : 0 })}`;
const names = (who: string[]) => (who.length > 2 ? `${who.slice(0, -1).join(", ")} & ${who.at(-1)}` : who.join(" & "));
const winning = (b: RidingBet, p: number) => (b.side === "yes" ? p >= b.strike : p < b.strike);

/** Coinbase's feed for one coin: a minute-by-minute start, then every trade as it happens. */
function useFeed(coin: Coin) {
  const ticks = useRef<Tick[]>([]);
  const [status, setStatus] = useState<"connecting" | "live" | "down">("connecting");
  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let quiet: ReturnType<typeof setInterval> | undefined;
    let wait = 1000;
    let heard = Date.now();
    ticks.current = [];
    setStatus("connecting");

    const add = (t: number, p: number) => {
      const a = ticks.current;
      // Several trades in a blink are one point (keeps the line light to draw)
      if (a.length && t - a[a.length - 1].t < 200) a[a.length - 1] = { t: a[a.length - 1].t, p };
      else a.push({ t, p });
      const cut = Date.now() - PAST - 60_000;
      if (a[0]?.t < cut) ticks.current = a.filter((x) => x.t >= cut);
    };

    const seed = async () => {
      try {
        const r = await fetch(`https://api.exchange.coinbase.com/products/${PRODUCT[coin]}/candles?granularity=60`);
        const rows: number[][] = await r.json();
        const now = Date.now();
        // [start, low, high, open, close, volume], newest first; a candle's close is its price at the minute's end
        const past = rows
          .map(([t, , , , close]) => ({ t: Math.min(t * 1000 + 60_000, now - 1000), p: close }))
          .filter((x) => x.t >= now - PAST - 60_000)
          .sort((a, b) => a.t - b.t);
        if (!closed) ticks.current = [...past, ...ticks.current.filter((x) => x.t > (past.at(-1)?.t ?? 0))];
      } catch {
        /* the stream still fills the line in */
      }
    };

    const connect = () => {
      if (closed) return;
      ws = new WebSocket("wss://ws-feed.exchange.coinbase.com");
      ws.onopen = () => {
        wait = 1000;
        ws?.send(JSON.stringify({ type: "subscribe", product_ids: [PRODUCT[coin]], channels: ["ticker"] }));
      };
      ws.onmessage = (m) => {
        const d = JSON.parse(m.data);
        if (d.type !== "ticker" || d.product_id !== PRODUCT[coin]) return;
        heard = Date.now();
        add(heard, Number(d.price));
        setStatus("live");
      };
      ws.onclose = () => {
        if (closed) return;
        setStatus("down");
        retry = setTimeout(connect, wait);
        wait = Math.min(wait * 2, 30_000);
      };
      ws.onerror = () => ws?.close();
    };

    seed();
    connect();
    // A phone that slept: the socket can look open but be dead. Start over.
    quiet = setInterval(() => {
      if (Date.now() - heard > 20_000 && ws?.readyState === WebSocket.OPEN) {
        setStatus("down");
        ws.close();
        seed();
      }
    }, 5000);
    return () => {
      closed = true;
      clearTimeout(retry);
      clearInterval(quiet);
      ws?.close();
    };
  }, [coin]);
  return { ticks, status };
}

export default function LivePrice({ bets, coins, start }: { bets: RidingBet[]; coins: Coin[]; start: Coin }) {
  const [coin, setCoin] = useState<Coin>(start);
  const { ticks, status } = useFeed(coin);
  const canvas = useRef<HTMLCanvasElement>(null);
  const mine = bets.filter((b) => b.coin === coin);
  const betsRef = useRef(mine);
  betsRef.current = mine;
  const hover = useRef<number | null>(null);
  // The words around the chart update a few times a second; the line itself every frame
  const [now, setNow] = useState({ p: null as number | null, t: 0, from: null as number | null });

  useEffect(() => {
    const id = setInterval(() => {
      const a = ticks.current;
      const from = a.find((x) => x.t >= Date.now() - PAST)?.p ?? null;
      setNow({ p: a.at(-1)?.p ?? null, t: Date.now(), from });
    }, 250);
    return () => clearInterval(id);
  }, [ticks]);

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const ctx = el.getContext("2d");
    if (!ctx) return;
    const css = getComputedStyle(document.documentElement);
    const v = (n: string) => css.getPropertyValue(n).trim();
    const C = {
      line: v("--series-1"), up: v("--up"), down: v("--down"), grid: v("--grid"), muted: v("--text-muted"),
      text: v("--text-primary"), surface: v("--surface-1"), page: v("--page"),
    };
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let shown: number | null = null;
    let lo = 0, hi = 0, ahead = 60_000;
    let last = performance.now();
    let frame = 0;

    const draw = (ts: number) => {
      frame = requestAnimationFrame(draw);
      const dt = Math.min(ts - last, 200);
      last = ts;
      const ease = (tau: number) => (still ? 1 : 1 - Math.exp(-dt / tau));
      const dpr = window.devicePixelRatio || 1;
      const W = el.clientWidth, H = HEIGHT;
      if (el.width !== Math.round(W * dpr)) { el.width = Math.round(W * dpr); el.height = Math.round(H * dpr); }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);

      const a = ticks.current;
      const now = Date.now();
      if (!a.length) {
        ctx.fillStyle = C.muted;
        ctx.font = "12px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("Connecting to the price feed…", W / 2, H / 2);
        return;
      }
      const latest = a[a.length - 1].p;
      shown = shown == null ? latest : shown + (latest - shown) * ease(140);

      // Leave room for the nearest finish line, so you can watch it come
      const bs = betsRef.current;
      const next = bs.map((b) => b.closes - now).filter((ms) => ms > 0).sort((x, y) => x - y)[0];
      ahead += (Math.min(Math.max(next ?? 0, 60_000) + 20_000, MAX_AHEAD) - ahead) * ease(600);

      const w = W - PAD.l - PAD.r, h = H - PAD.t - PAD.b;
      const t0 = now - PAST, t1 = now + ahead;
      const x = (t: number) => PAD.l + ((t - t0) / (t1 - t0)) * w;

      // The vertical range follows the price and always keeps every target in view
      const seen = a.filter((p) => p.t >= t0 - 60_000);
      let tlo = Math.min(shown, ...seen.map((p) => p.p), ...bs.map((b) => b.strike));
      let thi = Math.max(shown, ...seen.map((p) => p.p), ...bs.map((b) => b.strike));
      const minSpan = shown * 0.0006;
      if (thi - tlo < minSpan) { const m = (thi + tlo) / 2; tlo = m - minSpan / 2; thi = m + minSpan / 2; }
      const pad = (thi - tlo) * 0.14;
      tlo -= pad; thi += pad;
      if (hi === 0) { lo = tlo; hi = thi; }
      lo += (tlo - lo) * ease(450);
      hi += (thi - hi) * ease(450);
      const y = (p: number) => PAD.t + h - ((p - lo) / (hi - lo)) * h;

      // Grid and price axis (right side, like Kalshi)
      const yt = niceTicks(lo, hi, 4).filter((p) => p >= lo && p <= hi);
      const step = yt.length > 1 ? yt[1] - yt[0] : 1;
      ctx.font = "11px system-ui, sans-serif";
      ctx.textBaseline = "middle";
      ctx.textAlign = "left";
      ctx.lineWidth = 1;
      // (a grid price hides when a price tag sits on top of it)
      const tags = [shown, ...bs.map((b) => b.strike)].map(y);
      for (const p of yt) {
        ctx.strokeStyle = C.grid;
        ctx.beginPath(); ctx.moveTo(PAD.l, Math.round(y(p)) + 0.5); ctx.lineTo(PAD.l + w, Math.round(y(p)) + 0.5); ctx.stroke();
        if (tags.some((ty) => Math.abs(ty - y(p)) < 16)) continue;
        ctx.fillStyle = C.muted;
        ctx.fillText(price(p, step), PAD.l + w + 8, y(p));
      }
      // Time axis on round minutes, spaced so the labels never touch
      ctx.textAlign = "center";
      ctx.textBaseline = "alphabetic";
      const every = [60_000, 120_000, 180_000, 300_000, 600_000].find((m) => (m / (t1 - t0)) * w >= 52) ?? 600_000;
      for (let t = Math.ceil(t0 / every) * every; t <= t1; t += every) {
        if (x(t) < PAD.l + 16 || x(t) > PAD.l + w - 16) continue;
        ctx.fillStyle = C.muted;
        ctx.fillText(clock(t).replace(/ [AP]M$/, ""), x(t), H - 6);
      }

      // The line: thinned to one point every couple of pixels, drawn as a smooth curve
      const pts: [number, number][] = [];
      let lastX = -Infinity;
      for (const p of seen) {
        const px = x(p.t);
        if (px - lastX < 2 && pts.length) pts[pts.length - 1] = [pts[pts.length - 1][0], y(p.p)];
        else { pts.push([px, y(p.p)]); lastX = px; }
      }
      const head: [number, number] = [x(now), y(shown)];
      pts.push(head);
      const trace = () => {
        ctx.moveTo(pts[0][0], pts[0][1]);
        for (let i = 1; i < pts.length - 1; i++) {
          const mx = (pts[i][0] + pts[i + 1][0]) / 2, my = (pts[i][1] + pts[i + 1][1]) / 2;
          ctx.quadraticCurveTo(pts[i][0], pts[i][1], mx, my);
        }
        ctx.lineTo(head[0], head[1]);
      };
      ctx.save();
      ctx.beginPath(); ctx.rect(PAD.l, 0, w, H); ctx.clip();
      const fill = ctx.createLinearGradient(0, PAD.t, 0, PAD.t + h);
      fill.addColorStop(0, `${C.line}40`);
      fill.addColorStop(1, `${C.line}00`);
      ctx.beginPath(); trace();
      ctx.lineTo(head[0], PAD.t + h); ctx.lineTo(pts[0][0], PAD.t + h); ctx.closePath();
      ctx.fillStyle = fill; ctx.fill();
      ctx.beginPath(); trace();
      ctx.strokeStyle = C.line; ctx.lineWidth = 2; ctx.lineJoin = "round"; ctx.lineCap = "round"; ctx.stroke();
      ctx.restore();

      // Each bet: its target across the chart, green while winning and red while losing, plus its finish line
      ctx.font = "600 11px system-ui, sans-serif";
      ctx.textBaseline = "middle";
      const used: number[] = [];
      for (const b of [...bs].sort((p, q) => q.strike - p.strike)) {
        const col = winning(b, shown) ? C.up : C.down;
        const by = y(b.strike);
        ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.setLineDash([5, 4]);
        ctx.beginPath(); ctx.moveTo(PAD.l, by); ctx.lineTo(PAD.l + w, by); ctx.stroke();
        const cx = x(b.closes);
        if (cx > PAD.l && cx <= PAD.l + w) {
          ctx.setLineDash([2, 3]); ctx.strokeStyle = C.muted; ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(cx, PAD.t); ctx.lineTo(cx, PAD.t + h); ctx.stroke();
          ctx.fillStyle = C.muted; ctx.textAlign = "center"; ctx.font = "11px system-ui, sans-serif";
          ctx.fillText(`🏁 ${clock(b.closes)}`, cx, PAD.t - 4);
          ctx.font = "600 11px system-ui, sans-serif";
        }
        ctx.setLineDash([]);
        // Label chip on the left, nudged so stacked targets don't overprint
        let ly = by - 10;
        while (used.some((u) => Math.abs(u - ly) < 17)) ly += 17;
        used.push(ly);
        const text = `${b.side === "yes" ? "▲" : "▼"} ${names(b.who.map(shortName))}`;
        const tw = ctx.measureText(text).width;
        ctx.fillStyle = C.surface; ctx.globalAlpha = 0.85;
        ctx.fillRect(PAD.l + 4, ly - 8, tw + 12, 16);
        ctx.globalAlpha = 1;
        ctx.fillStyle = col; ctx.textAlign = "left";
        ctx.fillText(text, PAD.l + 10, ly);
        // Target tag on the price axis
        ctx.fillStyle = col;
        ctx.fillRect(PAD.l + w + 2, by - 9, PAD.r - 4, 18);
        ctx.fillStyle = C.page;
        ctx.fillText(price(b.strike, step), PAD.l + w + 7, by);
      }

      // Hover / touch: the price at that moment
      const hx = hover.current;
      if (hx != null && hx >= PAD.l && hx <= head[0]) {
        const t = t0 + ((hx - PAD.l) / w) * (t1 - t0);
        let near = seen[0];
        for (const p of seen) if (Math.abs(p.t - t) < Math.abs(near.t - t)) near = p;
        if (near) {
          const px = x(near.t), py = y(near.p);
          ctx.strokeStyle = C.muted; ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(px, PAD.t); ctx.lineTo(px, PAD.t + h); ctx.stroke();
          ctx.fillStyle = C.line; ctx.beginPath(); ctx.arc(px, py, 4, 0, Math.PI * 2); ctx.fill();
          const label = `${price(near.p, step < 1 ? 0.5 : 1)} · ${new Date(near.t).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" })}`;
          ctx.font = "12px system-ui, sans-serif";
          const lw = ctx.measureText(label).width + 14;
          const lx = Math.min(Math.max(px - lw / 2, PAD.l), PAD.l + w - lw);
          ctx.fillStyle = C.surface; ctx.strokeStyle = C.grid;
          ctx.fillRect(lx, PAD.t, lw, 20); ctx.strokeRect(lx + 0.5, PAD.t + 0.5, lw - 1, 19);
          ctx.fillStyle = C.text; ctx.textAlign = "left";
          ctx.fillText(label, lx + 7, PAD.t + 10);
        }
      }

      // The live head: a dot with a slow pulse, and the price tag on the axis
      const pulse = still ? 0 : (ts % 1600) / 1600;
      ctx.fillStyle = C.line;
      ctx.globalAlpha = 0.5 * (1 - pulse);
      ctx.beginPath(); ctx.arc(head[0], head[1], 4 + pulse * 10, 0, Math.PI * 2); ctx.fill();
      ctx.globalAlpha = 1;
      ctx.beginPath(); ctx.arc(head[0], head[1], 4, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = C.line; ctx.lineWidth = 1; ctx.setLineDash([1, 3]);
      ctx.beginPath(); ctx.moveTo(head[0] + 6, head[1]); ctx.lineTo(PAD.l + w, head[1]); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillRect(PAD.l + w + 2, head[1] - 9, PAD.r - 4, 18);
      ctx.fillStyle = C.page; ctx.font = "600 11px system-ui, sans-serif"; ctx.textAlign = "left";
      ctx.fillText(price(shown, step), PAD.l + w + 7, head[1]);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [ticks]);

  const move = (e: React.PointerEvent<HTMLCanvasElement>) => {
    hover.current = e.clientX - e.currentTarget.getBoundingClientRect().left;
  };
  const change = now.p != null && now.from != null ? now.p - now.from : null;
  const riding = mine.reduce((s, b) => s + b.cost, 0);
  const counts = (c: Coin) => bets.filter((b) => b.coin === c).length;

  return (
    <section className="card live-price">
      <div className="lp-head">
        <div>
          <div className="row-btns" style={{ gap: 8 }}>
            <h2 style={{ margin: 0 }}>{NAME[coin]} right now</h2>
            <span className={`lp-status lp-${status}`}>
              {status === "live" ? "● LIVE" : status === "connecting" ? "connecting…" : "reconnecting…"}
            </span>
          </div>
          <div className="lp-price">
            {now.p != null ? dollars(now.p) : "–"}
            {change != null && (
              <span className={change >= 0 ? "up" : "down"}>
                {change >= 0 ? "▲" : "▼"} {dollars(Math.abs(change))} <span className="muted">in 12 min</span>
              </span>
            )}
          </div>
        </div>
        {coins.length > 1 && (
          <div className="lp-tabs" role="tablist">
            {coins.map((c) => (
              <button key={c} role="tab" aria-selected={c === coin} onClick={() => setCoin(c)}>
                {c}{counts(c) ? ` (${counts(c)})` : ""}
              </button>
            ))}
          </div>
        )}
      </div>

      <canvas
        ref={canvas}
        style={{ width: "100%", height: HEIGHT, display: "block", touchAction: "pan-y" }}
        aria-label={`${NAME[coin]} price over the last 12 minutes${mine.length ? `, with ${mine.length} open bet${mine.length > 1 ? "s" : ""}` : ""}`}
        onPointerMove={move} onPointerDown={move}
        onPointerLeave={() => (hover.current = null)} onPointerUp={(e) => e.pointerType !== "mouse" && (hover.current = null)}
      />

      {mine.length ? (
        <>
          <p className="sub" style={{ margin: "10px 0 6px" }}>
            {dollars(riding)} riding on {NAME[coin].toLowerCase()} right now:
          </p>
          <ul className="lp-bets">
            {mine.map((b) => {
              const p = now.p;
              const win = p != null && winning(b, p);
              const gap = p != null ? Math.abs(p - b.strike) : null;
              const ms = b.closes - now.t;
              return (
                <li key={`${b.ticker}:${b.side}`}>
                  <span className={`lp-dot ${p == null ? "" : win ? "up" : "down"}`}>{p == null ? "•" : win ? "▲" : "▼"}</span>
                  <div>
                    <div>
                      <strong>{names(b.who)}</strong> bet it ends <strong>{b.side === "yes" ? "at or above" : "below"} {dollars(b.strike)}</strong> at {clock(b.closes)}
                    </div>
                    <div className="muted small">
                      Put in {dollars(b.cost)}, gets {dollars(b.payout)} if right
                      {gap != null && (
                        <> · <span className={win ? "up" : "down"}>{win ? "winning" : "losing"} by {dollars(gap)}</span></>
                      )}
                      {now.t > 0 && <>{" · "}{ms > 0 ? `${left(ms)} left` : "waiting for Kalshi to settle"}</>}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      ) : (
        <p className="sub" style={{ margin: "10px 0 0" }}>
          Nothing riding on {NAME[coin].toLowerCase()} right now. When someone bets, their target shows up on the line.
        </p>
      )}
    </section>
  );
}
