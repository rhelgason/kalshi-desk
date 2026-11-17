"use client";

import { useEffect, useState } from "react";

/** Desktop look only: a 1995 taskbar along the bottom, just for the look: a clock, no buttons (11-17, owner). */
export default function Taskbar() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 20_000);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="taskbar" aria-hidden>
      <span className="task-clock">{now ? now.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }) : ""}</span>
    </div>
  );
}
