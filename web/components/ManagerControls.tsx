"use client";

import { useState, useTransition } from "react";
import { requestRetune, startNewSeason } from "@/app/actions";
import Card from "./ui/Card";

/**
 * The only two desk-wide buttons the manager presses themselves (11-17; every other rule goes through Claude):
 * retune everyone now, and a fresh start for dire cases. They act on the office being viewed (real or Training).
 * Stopping real trading is on the Real Money card above.
 */
export default function ManagerControls({ training }: { training: boolean }) {
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);
  const where = training ? "Training" : "your real-money office";
  return (
    <Card title="Manager Controls">
      <div className="controls">
        <div className="control">
          <div>
            <strong>🔧 Retune everyone now</strong>
            <p className="muted small">Each employee&apos;s settings are re-tested against recent markets and better ones adopted. Nothing is reset. Picked up within about 3 hours.</p>
          </div>
          <button className="btn" disabled={pending}
            onClick={() => start(async () => { await requestRetune(); setMsg("✓ Retune requested."); })}>Retune</button>
        </div>
        <div className="control control-danger">
          <div>
            <strong>🧨 Fresh start</strong>
            <p className="muted small">For dire cases: starts a new season in {where}. The pool and its charts begin again from its starting money; the old results stay in the records.</p>
          </div>
          <button className="btn danger" disabled={pending}
            onClick={() => {
              if (!confirm(`Start a new season in ${where}? Charts and totals begin again from zero.`)) return;
              if (prompt('Type "fresh start" to confirm') !== "fresh start") return;
              start(async () => { await startNewSeason(0); setMsg("✓ Fresh start on the desk's next run."); });
            }}>Fresh start</button>
        </div>
      </div>
      {msg && <p className="muted small">{msg}</p>}
    </Card>
  );
}
