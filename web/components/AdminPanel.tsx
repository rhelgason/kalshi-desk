"use client";

import { useState, useTransition } from "react";
import {
  fireEmployee, grantBonus, hireOnReal, rehireEmployee, reinstateEmployee, saveSettings, setAutotune, setLevel, setNote,
  suspendEmployee,
} from "@/app/actions";
import { LEVELS, poolShare } from "@/lib/hr";
import type { Employee, RosterRow } from "@/lib/types";
import Card from "./ui/Card";

type Params = NonNullable<Employee["params"]>;
type Status = "keep" | "bench1" | "bench3" | "bench7" | "bench" | "reinstate" | "fire" | "rehire";

const BENCH: Record<string, number | null> = { bench1: 1, bench3: 3, bench7: 7, bench: null };

/**
 * Manager controls for one employee (11-16): every change is a draft until Save, which lists what it will do and
 * applies it all at once (Discard drops it). Only the logged-in manager sees this, at the bottom of the page.
 */
export default function AdminPanel({ e, roster, reserve, betPct, movable = false }: {
  e: Employee; roster: RosterRow | null; reserve: number; betPct: number; movable?: boolean;
}) {
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);
  const status = roster?.status ?? e.status ?? "active";
  const level0 = roster?.level ?? e.level ?? 1;
  const auto0 = roster?.autotune ?? e.autotune ?? true;
  const note0 = roster?.note ?? e.note ?? "";
  const params = e.params ?? {};
  const overrides = (roster?.params ?? e.overrides ?? {}) as Params;

  const [employ, setEmploy] = useState<Status>("keep");
  const [why, setWhy] = useState("");
  const [level, setLvl] = useState(level0);
  const [auto, setAuto] = useState(auto0);
  const [note, setNoteText] = useState(note0);
  const [bonus, setBonus] = useState("");
  const [bonusWhy, setBonusWhy] = useState("");
  const [draft, setDraft] = useState<Record<string, string | boolean>>({});
  const [resetSettings, setResetSettings] = useState(false);
  const [move, setMove] = useState(false);

  const entries = Object.entries(params).filter(([, v]) => v === null || ["number", "boolean", "string"].includes(typeof v));
  const changedParams = (): Params => {
    const out: Params = {};
    for (const [k, raw] of Object.entries(draft)) {
      const orig = params[k];
      if (typeof orig === "number") { const x = Number(raw); if (Number.isFinite(x) && x !== orig) out[k] = x; }
      else if (typeof orig === "boolean") { if (raw !== orig) out[k] = raw as boolean; }
      else if (raw !== String(orig ?? "")) out[k] = raw === "" ? null : (raw as string);
    }
    return out;
  };

  // What Save will do, in words, in the order it does it
  const plan: { say: string; act: () => Promise<unknown> }[] = [];
  if (employ === "fire") plan.push({ say: "Fire", act: () => fireEmployee(e.key, why) });
  else if (employ === "rehire") plan.push({ say: "Rehire as an Intern", act: () => rehireEmployee(e.key) });
  else if (employ === "reinstate") plan.push({ say: "Bring back from the bench", act: () => reinstateEmployee(e.key) });
  else if (employ in BENCH) {
    const d = BENCH[employ];
    plan.push({ say: d ? `Bench for ${d} day${d > 1 ? "s" : ""}` : "Bench until you bring them back", act: () => suspendEmployee(e.key, d, why) });
  }
  if (level !== level0) plan.push({ say: `Level → ${LEVELS[level].title}`, act: () => setLevel(e.key, level) });
  if (auto !== auto0) plan.push({ say: auto ? "Autotune on" : "Autotune off", act: () => setAutotune(e.key, auto) });
  const pc = changedParams();
  if (resetSettings) plan.push({ say: "Settings back to defaults", act: () => saveSettings(e.key, {}, true) });
  else if (Object.keys(pc).length) plan.push({ say: `Settings: ${Object.keys(pc).join(", ")}`, act: () => saveSettings(e.key, pc, false) });
  if (note !== note0) plan.push({ say: note ? "New note" : "Clear the note", act: () => setNote(e.key, note) });
  const amt = Number(bonus);
  if (bonus && Number.isFinite(amt) && amt !== 0)
    plan.push({ say: amt > 0 ? `Give $${amt} from the reserve` : `Take $${-amt} back`, act: () => grantBonus(e.key, amt, bonusWhy) });
  if (move) plan.push({ say: "Move to real money as an Intern", act: () => hireOnReal(e.key) });

  const discard = () => {
    setEmploy("keep"); setWhy(""); setLvl(level0); setAuto(auto0); setNoteText(note0); setBonus(""); setBonusWhy("");
    setDraft({}); setResetSettings(false); setMove(false);
  };
  const save = () => {
    if (!plan.length) return;
    if ((employ === "fire" || move) && !confirm(`Save these changes for ${e.name}?\n\n${plan.map((p) => `• ${p.say}`).join("\n")}`)) return;
    start(async () => {
      try {
        for (const p of plan) {
          const r = (await p.act()) as { error?: string } | undefined;
          if (r?.error) { setMsg(`⚠ ${p.say}: ${r.error}`); return; }
        }
        setMsg(`Saved: ${plan.map((p) => p.say).join(" · ")}. The desk picks it up on its next run (~2 min).`);
        discard();
      } catch (err) {
        setMsg(`⚠ ${String(err)}`);
      }
    });
  };

  const options: [Status, string][] = status === "fired" ? [["keep", "Fired"], ["rehire", "Rehire"]]
    : status === "suspended" ? [["keep", "Benched"], ["reinstate", "Bring back"], ["fire", "Fire"]]
    : [["keep", "Working"], ["bench1", "Bench 1d"], ["bench3", "Bench 3d"], ["bench7", "Bench 7d"], ["bench", "Bench ∞"], ["fire", "Fire"]];

  return (
    <Card title="Manager Controls" aside="Only you see this" className="manager-panel">
      <div className="mp-grid">
        <div className="mp-field mp-wide">
          <span className="mp-label">Status</span>
          <div className="seg mp-seg">
            {options.map(([k, label]) => (
              <button key={k} type="button" aria-pressed={employ === k} className={k === "fire" ? "danger" : undefined}
                      onClick={() => setEmploy(k)} disabled={pending}>{label}</button>
            ))}
          </div>
          {(employ === "fire" || employ in BENCH) && (
            <input type="text" placeholder={employ === "fire" ? "Why? (shown in the office news)" : "Why? (optional)"}
                   value={why} onChange={(ev) => setWhy(ev.target.value)} />
          )}
        </div>

        {status !== "fired" && (
          <div className="mp-field mp-wide">
            <span className="mp-label">Level <span className="muted">· each bet</span></span>
            <div className="mp-levels">
              {LEVELS.map((l, i) => (
                <button key={l.title} type="button" className={`lvl lvl-${i} mp-level`} aria-pressed={level === i}
                        onClick={() => setLvl(i)} disabled={pending}>
                  {l.title} <small>{poolShare(l.multiplier, betPct)}</small>
                </button>
              ))}
            </div>
          </div>
        )}

        <label className="mp-field mp-toggle">
          <span className="mp-label">Autotune</span>
          <span className="mp-switch-row">
            <input type="checkbox" role="switch" checked={auto} disabled={pending || e.backtestable === false}
                   onChange={(ev) => setAuto(ev.target.checked)} />
            <span className="muted small">{e.backtestable === false ? "Can't be replayed, so reviews judge them" : "Retune when a tested improvement turns up"}</span>
          </span>
        </label>

        {reserve > 0 && (
        <div className="mp-field">
          <span className="mp-label">Bonus <span className="muted">· ${reserve.toFixed(0)} in the reserve</span></span>
          <div className="mp-inline">
            <input type="text" inputMode="decimal" placeholder="$0" value={bonus} onChange={(ev) => setBonus(ev.target.value.replace(/[^\d.-]/g, ""))} />
            <input type="text" placeholder="reason" value={bonusWhy} onChange={(ev) => setBonusWhy(ev.target.value)} />
          </div>
        </div>
        )}

        <label className="mp-field mp-wide">
          <span className="mp-label">Note on their page</span>
          <input type="text" value={note} onChange={(ev) => setNoteText(ev.target.value)} placeholder="Nothing yet" />
        </label>

        {movable && (
          <label className="mp-field mp-wide mp-toggle">
            <span className="mp-label">Real money</span>
            <span className="mp-switch-row">
              <input type="checkbox" role="switch" checked={move} onChange={(ev) => setMove(ev.target.checked)} />
              <span className="muted small">Move them to the real book as an Intern (half-size bets), no new season</span>
            </span>
          </label>
        )}
      </div>

      {entries.length > 0 && (
        <details className="mp-settings">
          <summary>Strategy settings <span className="muted">({entries.length}{Object.keys(overrides).length ? `, ${Object.keys(overrides).length} custom` : ""})</span></summary>
          <div className="params">
            {entries.map(([k, v]) => (
              <label key={k}>
                <span>{k}{k in overrides ? <small> · custom</small> : null}</span>
                {typeof v === "boolean" ? (
                  <input type="checkbox" checked={(draft[k] as boolean) ?? v} disabled={resetSettings}
                         onChange={(ev) => setDraft({ ...draft, [k]: ev.target.checked })} />
                ) : (
                  <input type="text" inputMode={typeof v === "number" ? "decimal" : undefined} value={(draft[k] as string) ?? String(v ?? "")}
                         disabled={resetSettings} onChange={(ev) => setDraft({ ...draft, [k]: ev.target.value })} />
                )}
              </label>
            ))}
          </div>
          {Object.keys(overrides).length > 0 && (
            <label className="mp-switch-row small">
              <input type="checkbox" checked={resetSettings} onChange={(ev) => { setResetSettings(ev.target.checked); setDraft({}); }} />
              Put every setting back to the desk&apos;s defaults
            </label>
          )}
        </details>
      )}

      <div className={`mp-bar ${plan.length ? "dirty" : ""}`}>
        <span className="small">
          {plan.length ? <><strong>{plan.length} unsaved:</strong> {plan.map((p) => p.say).join(" · ")}</> : <span className="muted">No changes</span>}
        </span>
        <span className="row-btns">
          <button type="button" className="btn small ghost" disabled={pending || !plan.length} onClick={discard}>Discard</button>
          <button type="button" className="btn small primary" disabled={pending || !plan.length || (employ === "fire" && !why.trim())} onClick={save}>
            {pending ? "Saving…" : "Save"}
          </button>
        </span>
      </div>
      {msg && <p className="mp-msg small">{msg}</p>}
    </Card>
  );
}
