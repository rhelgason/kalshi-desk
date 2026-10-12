"use client";

import { useState, useTransition } from "react";
import { requestRetune, startNewSeason, updatePolicy } from "@/app/actions";
import type { Policy } from "@/lib/types";

type Field = { key: string; label: string; help: string; kind: "number" | "percent" | "bool"; group?: "autotune" };

const FIELDS: Field[] = [
  { key: "review_days", label: "Review every (days)", help: "7 = Employee of the Week, 28+ = of the Month", kind: "number" },
  { key: "min_settled", label: "Bets needed to be reviewed", help: "Settled bets in the period", kind: "number" },
  { key: "promote_roi", label: "Promote at", help: "Period return on bankroll", kind: "percent" },
  { key: "promote_min_confidence", label: "Promotion needs skill confidence", help: "Season-to-date 'skill or luck?' score", kind: "percent" },
  { key: "demote_roi", label: "Demote at", help: "Period return on bankroll", kind: "percent" },
  { key: "strikes_to_suspend", label: "Strikes before suspension", help: "Bad periods while already an Intern", kind: "number" },
  { key: "suspend_days", label: "Suspension length (days)", help: "", kind: "number" },
  { key: "max_drawdown_suspend", label: "Suspend if bankroll drops", help: "Worst drop within one period", kind: "percent" },
  { key: "auto_fire", label: "Auto-fire repeat offenders", help: "Otherwise only you can fire", kind: "bool" },
  { key: "strikes_to_fire", label: "Strikes before auto-firing", help: "", kind: "number" },
  { key: "award_bonus", label: "Award bonus ($)", help: "Paid from the reserve", kind: "number" },
  { key: "reserve", label: "Bonus reserve ($)", help: "Paper money available for bonuses", kind: "number" },
  { key: "enabled", label: "Autotune enabled", help: "Daily retuning of eligible employees", kind: "bool", group: "autotune" },
  { key: "every_hours", label: "Retune every (hours)", help: "Checked by the background job every 3h", kind: "number", group: "autotune" },
  { key: "lookback_days", label: "History to tune on (days)", help: "First 2/3 picks, last 1/3 checks", kind: "number", group: "autotune" },
  { key: "min_test_bets", label: "Minimum test bets", help: "Evidence needed before switching", kind: "number", group: "autotune" },
  { key: "min_improvement", label: "Minimum improvement ($)", help: "Test-period gain needed to switch", kind: "number", group: "autotune" },
  { key: "min_confidence", label: "Minimum test confidence", help: "'Skill or luck?' score on unseen data", kind: "percent", group: "autotune" },
];

/** The desk's rules. Everyone can read them; only the manager can edit. */
export default function PolicyForm({ policy, admin }: { policy: Policy; admin: boolean }) {
  const [draft, setDraft] = useState<Record<string, string | boolean>>({});
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);

  const value = (f: Field): number | boolean => {
    const src = f.group ? (policy.autotune as any)[f.key] : (policy as any)[f.key];
    return src;
  };
  const shown = (f: Field) => {
    if (f.key in draft) return draft[f.key];
    const v = value(f);
    return f.kind === "percent" ? String(Math.round((v as number) * 1000) / 10) : f.kind === "bool" ? v : String(v);
  };

  const save = () => {
    const top: Record<string, unknown> = {};
    const at: Record<string, unknown> = {};
    for (const f of FIELDS) {
      if (!(f.key in draft)) continue;
      const raw = draft[f.key];
      const v = f.kind === "bool" ? raw : f.kind === "percent" ? Number(raw) / 100 : Number(raw);
      if (typeof v === "number" && !Number.isFinite(v)) continue;
      (f.group ? at : top)[f.key] = v;
    }
    start(async () => {
      await updatePolicy({ ...top, ...(Object.keys(at).length ? { autotune: at } : {}) } as any);
      setDraft({});
      setMsg("✓ Rules saved. The desk uses them from its next run.");
    });
  };

  return (
    <div className="form">
      {(["", "autotune"] as const).map((group) => (
        <div key={group}>
          <div className="section-title">{group ? "Autotuning" : "Performance reviews & bonuses"}</div>
          <div className="params">
            {FIELDS.filter((f) => (f.group ?? "") === group).map((f) => (
              <label key={f.key}>
                <span>{f.label}{f.kind === "percent" ? " (%)" : ""}</span>
                {f.kind === "bool" ? (
                  <input type="checkbox" disabled={!admin} checked={shown(f) as boolean}
                    onChange={(e) => setDraft({ ...draft, [f.key]: e.target.checked })} />
                ) : (
                  <input type="number" step="any" disabled={!admin} value={shown(f) as string}
                    onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })} />
                )}
                {f.help && <small>{f.help}</small>}
              </label>
            ))}
          </div>
        </div>
      ))}
      {admin && (
        <>
          <div className="row-btns">
            <button className="btn primary" disabled={pending || !Object.keys(draft).length} onClick={save}>Save rules</button>
            <button className="btn" disabled={pending} onClick={() => start(async () => { await requestRetune(); setMsg("✓ Retune requested. The background job picks it up within ~3 hours."); })}>🔧 Retune everyone now</button>
            <button className="btn danger" disabled={pending}
              onClick={() => {
                const r = prompt(`Start fresh? Every employee restarts at their starting money (old results stay in the records). Bonus reserve from now on:`, String(policy.reserve));
                if (r !== null) start(async () => { await startNewSeason(Number(r)); setMsg("✓ Fresh start on the desk's next run."); });
              }}>🎉 Fresh start (reset everyone)</button>
          </div>
        </>
      )}
      {msg && <p className="notice">{msg}</p>}
    </div>
  );
}
