"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

/** Desktop look only: a 1995 taskbar along the bottom, with a Start button and a clock. */
export default function Taskbar() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 20_000);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="taskbar" role="navigation" aria-label="Taskbar">
      <Link href="/" className="start-btn"><span aria-hidden>🪟</span> Start</Link>
      <span className="task-sep" />
      <Link href="/" className="task-item">📈 Kalshi Desk</Link>
      <Link href="/rules" className="task-item task-extra">📜 Office Rules</Link>
      <span className="task-clock">{now ? now.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }) : ""}</span>
    </div>
  );
}
