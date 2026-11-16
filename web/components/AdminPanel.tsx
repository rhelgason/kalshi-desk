"use client";

import { useState, useTransition } from "react";
import {
  fireEmployee, grantBonus, rehireEmployee, reinstateEmployee, saveSettings, setAutotune, setLevel, setNote,
  suspendEmployee,
} from "@/app/actions";
import { LEVELS, poolShare } from "@/lib/hr";
import type { Employee, RosterRow } from "@/lib/types";

type Params = NonNullable<Employee["params"]>;

/** Manager controls for one employee. Only rendered for the logged-in admin. */
export default function AdminPanel({ e, roster, reserve }: { e: Employee; roster: RosterRow | null; reserve: number }) {
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);
  const status = roster?.status ?? e.status ?? "active";
  const level = roster?.level ?? e.level ?? 1;
  const autotune = roster?.autotune ?? e.autotune ?? true;

  const run = (fn: () => Promise<unknown>, ok: string) =>
    start(async () => {
      try {
        const r = (await fn()) as { error?: string } | undefined;
        setMsg(r?.error ? `⚠ ${r.error}` : `✓ ${ok}. The desk picks this up on its next run (~2 min).`);
      } catch (err) {
        setMsg(`⚠ ${String(err)}`);
      }
    });

  return (
    <section className="card">
      <h2>Manager Controls</h2>
      <p className="sub">Only you can see this. Changes are logged in the office news.</p>

      <div className="section-title">Employment</div>
      <div className="row-btns">
        {status === "fired" ? (
          <button className="btn" disabled={pending} onClick={() => run(() => rehireEmployee(e.key), "Rehired as an Intern")}>🔄 Rehire as Intern</button>
        ) : (
          <>
            {status === "suspended" ? (
              <button className="btn" disabled={pending} onClick={() => run(() => reinstateEmployee(e.key), "Reinstated")}>▶️ Reinstate now</button>
            ) : (
              [1, 3, 7].map((d) => (
                <button key={d} className="btn" disabled={pending}
                  onClick={() => run(() => suspendEmployee(e.key, d, ""), `Suspended for ${d} day${d > 1 ? "s" : ""}`)}>
                  ⏸ Suspend {d}d
                </button>
              ))
            )}
            {status !== "suspended" && (
              <button className="btn" disabled={pending} onClick={() => run(() => suspendEmployee(e.key, null, ""), "Suspended indefinitely")}>⏸ Until further notice</button>
            )}
            <button className="btn danger" disabled={pending}
              onClick={() => {
                const why = prompt(`Fire ${e.name}? They'll stop trading for good (you can rehire later). Reason:`);
                if (why !== null) run(() => fireEmployee(e.key, why), "Fired");
              }}>🚪 Fire</button>
          </>
        )}
      </div>

      <div className="section-title">Level (bet size)</div>
      <div className="row-btns">
        {LEVELS.map((l, i) => (
          <button key={l.title} className={`btn ${i === level ? "on" : ""}`} disabled={pending || i === level}
            onClick={() => run(() => setLevel(e.key, i), `Now ${l.title}`)}>
            {l.title} <span className="muted">{poolShare(l.multiplier)}</span>
          </button>
        ))}
      </div>

      <div className="section-title">Bonus from the reserve <span className="muted">(${reserve.toFixed(0)} left)</span></div>
      <BonusForm onGrant={(amt, why) => run(() => grantBonus(e.key, amt, why), amt > 0 ? `Gave $${amt}` : `Took $${-amt}`)} pending={pending} />

      <div className="section-title">Autotune</div>
      <label className="row-btns">
        <input type="checkbox" checked={autotune} disabled={pending || e.backtestable === false}
          onChange={(ev) => run(() => setAutotune(e.key, ev.target.checked), ev.target.checked ? "Autotune on" : "Autotune off")} />
        {e.backtestable === false
          ? "This employee can't be replayed from price history, so reviews (not autotune) judge them."
          : "Let the daily job adjust these settings when a tested improvement is found."}
      </label>

      <div className="section-title">Settings</div>
      <SettingsEditor params={e.params ?? {}} overrides={(roster?.params ?? e.overrides ?? {}) as Params} pending={pending}
        onSave={(changes, reset) => run(() => saveSettings(e.key, changes, reset), reset ? "Settings reset" : "Settings saved")} />

      <div className="section-title">Manager&apos;s note</div>
      <NoteForm note={roster?.note ?? e.note ?? ""} pending={pending} onSave={(n) => run(() => setNote(e.key, n), "Note saved")} />

      {msg && <p className="notice" style={{ marginTop: 12 }}>{msg}</p>}
    </section>
  );
}

function BonusForm({ onGrant, pending }: { onGrant: (amount: number, why: string) => void; pending: boolean }) {
  const [amount, setAmount] = useState("100");
  const [why, setWhy] = useState("");
  return (
    <div className="row-btns">
      <input type="number" step="10" value={amount} onChange={(e) => setAmount(e.target.value)} style={{ width: 110 }} />
      <input type="text" placeholder="reason (optional)" value={why} onChange={(e) => setWhy(e.target.value)} style={{ width: 220 }} />
      <button className="btn" disabled={pending} onClick={() => onGrant(Number(amount), why)}>💰 Give</button>
      <span className="muted" style={{ fontSize: 12 }}>Negative takes money back into the reserve.</span>
    </div>
  );
}

function SettingsEditor({ params, overrides, onSave, pending }: {
  params: Params; overrides: Params; pending: boolean; onSave: (changes: Params, reset: boolean) => void;
}) {
  const [draft, setDraft] = useState<Record<string, string | boolean>>({});
  const entries = Object.entries(params).filter(([, v]) => v === null || ["number", "boolean", "string"].includes(typeof v));
  if (!entries.length) return <div className="muted">No adjustable settings.</div>;

  const changes = (): Params => {
    const out: Params = {};
    for (const [k, raw] of Object.entries(draft)) {
      const orig = params[k];
      if (typeof orig === "number") {
        const n = Number(raw);
        if (Number.isFinite(n) && n !== orig) out[k] = n;
      } else if (typeof orig === "boolean") {
        if (raw !== orig) out[k] = raw as boolean;
      } else if (raw !== String(orig ?? "")) {
        out[k] = raw === "" ? null : (raw as string);
      }
    }
    return out;
  };

  return (
    <div className="form">
      <div className="params">
        {entries.map(([k, v]) => (
          <label key={k}>
            <span>{k}{k in overrides ? <small> · custom</small> : null}</span>
            {typeof v === "boolean" ? (
              <input type="checkbox" checked={(draft[k] as boolean) ?? v} onChange={(e) => setDraft({ ...draft, [k]: e.target.checked })} />
            ) : (
              <input type={typeof v === "number" ? "number" : "text"} step="any" value={(draft[k] as string) ?? String(v ?? "")}
                onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
            )}
          </label>
        ))}
      </div>
      <div className="row-btns">
        <button className="btn primary" disabled={pending || !Object.keys(changes()).length}
          onClick={() => { onSave(changes(), false); setDraft({}); }}>Save changes</button>
        <button className="btn" disabled={pending || !Object.keys(overrides).length}
          onClick={() => { if (confirm("Drop all custom settings and go back to desk.yaml defaults?")) onSave({}, true); }}>
          Reset to defaults
        </button>
      </div>
    </div>
  );
}

function NoteForm({ note, onSave, pending }: { note: string; onSave: (n: string) => void; pending: boolean }) {
  const [text, setText] = useState(note);
  return (
    <div className="row-btns">
      <input type="text" value={text} onChange={(e) => setText(e.target.value)} placeholder="Shown on the employee's page" style={{ flex: 1, minWidth: 200 }} />
      <button className="btn" disabled={pending || text === note} onClick={() => onSave(text)}>Save note</button>
    </div>
  );
}
