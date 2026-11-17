"use client";

import { useState, useTransition } from "react";
import { createInvite, setOfficePaused } from "@/app/account";
import type { Book } from "@/lib/db";

/** The owner's invite maker (the cockpit's Invite a Friend card): a first name in, a link out (good for a week, for one person). */
export function InviteForm({ forUser, name: fixed }: { forUser?: number; name?: string }) {
  const [name, setName] = useState(fixed ?? "");
  const [link, setLink] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const make = () => start(async () => {
    const r = await createInvite(name, forUser);
    if (!r.ok) return setMsg(r.error);
    setLink(r.link);
    setMsg(null);
    try { await navigator.clipboard.writeText(r.link); setMsg("✓ Copied: send it to them"); } catch { /* shown below */ }
  });
  return (
    <div className="stack-tight">
      {!fixed && <label className="form">Their first name <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} /></label>}
      <button className="btn" disabled={pending || !name.trim()} onClick={make}>
        {fixed ? `🔗 New sign-in link for ${fixed}` : "✉️ Make an invite link"}
      </button>
      {link && <input readOnly value={link} onFocus={(e) => e.currentTarget.select()} />}
      {msg && <div className={msg.startsWith("✓") ? "up" : "down"}>{msg}</div>}
    </div>
  );
}

/** A fresh sign-in link for one of the friends (picked from a list): for a new phone without their passkey. */
export function SignInLink({ friends }: { friends: { id: number; name: string }[] }) {
  const [who, setWho] = useState(friends[0]?.id ?? 0);
  const name = friends.find((f) => f.id === who)?.name ?? "";
  return (
    <div className="stack-tight">
      <label className="form">Friend
        <select value={who} onChange={(e) => setWho(Number(e.target.value))}>
          {friends.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
      </label>
      <InviteForm key={who} forUser={who} name={name} />
    </div>
  );
}

/** Pause or resume an office's betting: the friend's own button (and the owner's, on a friend's page). */
export function OfficePause({ halted, mine }: { halted: boolean; mine: boolean }) {
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);
  const flip = () => {
    const ask = halted ? "Start betting again?" : mine ? "Pause your office? Nothing new gets bet until you resume (bets already on finish as usual)."
      : "Pause this friend's office?";
    if (!confirm(ask)) return;
    start(async () => {
      const r = await setOfficePaused(!halted);
      setMsg(r.ok ? (halted ? "✓ Back on from the next run (within 2 minutes)" : "✓ Paused from the next run (within 2 minutes)") : r.error);
    });
  };
  return (
    <div className="row-btns">
      <button className="btn" disabled={pending} onClick={flip}>{halted ? "▶️ Resume betting" : "⏸ Pause betting"}</button>
      {msg && <span className={msg.startsWith("✓") ? "up small" : "down small"}>{msg}</span>}
    </div>
  );
}
