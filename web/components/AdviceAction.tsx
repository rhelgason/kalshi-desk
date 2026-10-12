"use client";

import { useState, useTransition } from "react";
import { reinstateEmployee, suspendEmployee } from "@/app/actions";
import type { Advice } from "@/lib/advice";

/** The one-tap button for an advice item (manager only). */
export default function AdviceAction({ k, name, advice }: { k: string; name: string; advice: Advice }) {
  const [pending, start] = useTransition();
  const [done, setDone] = useState<string | null>(null);
  const a = advice.action;
  if (!a) return null;
  if (done) return <span className="muted">✓ {done}</span>;
  if (a.kind === "suspend") {
    return (
      <button className="btn primary" disabled={pending}
        onClick={() => start(async () => {
          await suspendEmployee(k, a.days, advice.why);
          setDone(`${name} is benched for ${a.days} days`);
        })}>
        ⏸️ Bench for {a.days} days
      </button>
    );
  }
  return (
    <button className="btn" disabled={pending}
      onClick={() => start(async () => { await reinstateEmployee(k); setDone(`${name} is back at work`); })}>
      ▶️ Bring back now
    </button>
  );
}
