import type { Evidence, Realism } from "@/lib/types";
import { money } from "@/lib/format";

const TONE: Record<Evidence["verdict_key"], { icon: string; short: string; cls: string }> = {
  too_early: { icon: "⏳", short: "Too early", cls: "muted" },
  luck: { icon: "🎲", short: "Could be luck", cls: "muted" },
  probably_not: { icon: "🤔", short: "Probably no edge", cls: "down" },
  losing: { icon: "📉", short: "Reliably losing", cls: "down" },
  promising: { icon: "🌱", short: "Promising", cls: "up" },
  fragile: { icon: "🧊", short: "Real but thin", cls: "up" },
  strong: { icon: "💪", short: "Real skill", cls: "up" },
};

/** One-glance "is this skill or luck?" label for the leaderboard. */
export function SkillBadge({ e }: { e?: Evidence }) {
  if (!e) return <span className="badge muted">⏳ No bets yet</span>;
  const t = TONE[e.verdict_key];
  return (
    <span className={`badge ${t.cls}`} title={`${e.verdict}: ${(e.confidence * 100).toFixed(0)}% sure the edge is real`}>
      {t.icon} {t.short}
    </span>
  );
}

/** A 0-100% bar of how sure we are the edge is real, with the 50% (coin flip) and 95% (strong) marks. */
function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="meter" role="img" aria-label={`${pct}% confident the edge is real`}>
      <div className="meter-fill" style={{ width: `${pct}%` }} />
      <div className="meter-mark" style={{ left: "50%" }} title="50%: coin flip" />
      <div className="meter-mark" style={{ left: "95%" }} title="95%: strong evidence" />
    </div>
  );
}

export function SkillCheck({ e }: { e?: Evidence }) {
  if (!e) {
    return <div className="empty">No settled bets this season yet. Check back once some markets settle.</div>;
  }
  const t = TONE[e.verdict_key];
  return (
    <div>
      <p className="verdict"><span aria-hidden>{t.icon}</span> <strong>{e.verdict}</strong></p>
      <div className="row-btns" style={{ justifyContent: "space-between", fontSize: 12.5 }}>
        <span className="muted">just luck</span>
        <strong>{(e.confidence * 100).toFixed(0)}% sure it&apos;s real skill</strong>
        <span className="muted">definitely skill</span>
      </div>
      <ConfidenceBar value={e.confidence} />
      <dl className="kv" style={{ marginTop: 12 }}>
        <dt>Settled bets</dt>
        <dd>
          {e.bets}
          {e.bets_needed && e.bets_needed > e.bets && e.edge > 0
            ? ` · about ${e.bets_needed.toLocaleString()} needed to be sure at this pace`
            : ""}
        </dd>
        <dt>Average result per contract</dt>
        <dd className={e.edge > 0 ? "up" : e.edge < 0 ? "down" : ""}>{e.edge >= 0 ? "+" : "−"}{Math.abs(e.edge * 100).toFixed(1)}¢ after fees</dd>
        <dt>Profit on settled bets</dt><dd>{money(e.pnl)}</dd>
        <dt>…if every trade cost 1¢ more</dt><dd className={e.pnl_1c >= 0 ? "up" : "down"}>{money(e.pnl_1c)}</dd>
        <dt>…if every trade cost 2¢ more</dt><dd className={e.pnl_2c >= 0 ? "up" : "down"}>{money(e.pnl_2c)}</dd>
      </dl>
    </div>
  );
}

const REAL_ICON: Record<Realism["verdict_key"], string> = {
  none: "⏳", maker: "⚠️", too_big: "⚠️", slippy: "⚠️", realistic: "✅",
};

export function RealityCheck({ r }: { r?: Realism }) {
  if (!r || r.verdict_key === "none") return <div className="empty">No trades measured yet this season.</div>;
  return (
    <div>
      <p className="verdict"><span aria-hidden>{REAL_ICON[r.verdict_key]}</span> <strong>{r.verdict}</strong></p>
      <dl className="kv">
        <dt>Trades measured</dt><dd>{r.taker_fills} bought at the asking price{r.maker_fills ? ` · ${r.maker_fills} waiting-order fills` : ""}</dd>
        {r.slippage != null && (<><dt>Price moved before filling</dt><dd>{r.slippage > 0 ? "+" : ""}{(r.slippage * 100).toFixed(2)}¢ per contract on average</dd></>)}
        {r.depth_share != null && (<><dt>Share of what was for sale</dt><dd>{(r.depth_share * 100).toFixed(0)}% on average</dd></>)}
        {r.median_depth != null && (<><dt>Typical contracts for sale</dt><dd>{r.median_depth.toLocaleString()}</dd></>)}
        {r.latency_s != null && (<><dt>Time from decision to fill</dt><dd>{r.latency_s.toFixed(1)}s</dd></>)}
      </dl>
    </div>
  );
}
