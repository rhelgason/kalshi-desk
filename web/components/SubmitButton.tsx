"use client";

import { useEffect, useState } from "react";

/**
 * A form's button that shows it was heard (11-16): a spinner and no second press while the server works (most of
 * these then move to another page, which replaces the button).
 */
export default function SubmitButton({ children, className }: { children: React.ReactNode; className?: string }) {
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!busy) return;
    const t = setTimeout(() => setBusy(false), 15_000); // the page didn't change: let them try again
    return () => clearTimeout(t);
  }, [busy]);
  return (
    // Disabled only after the click has sent the form (disabling during the click would cancel it)
    <button className={className} aria-busy={busy || undefined} onClick={(e) => { if (busy) e.preventDefault(); else setTimeout(() => setBusy(true)); }}>
      {busy && <span className="spinner" aria-hidden />}{children}
    </button>
  );
}
