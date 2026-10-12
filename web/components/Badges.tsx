import type { Employee } from "@/lib/types";

const LEVEL_ICON = ["🎒", "💼", "📊", "🏅", "👑"];

export function LevelBadge({ level, title }: { level?: number; title?: string }) {
  const l = level ?? 1;
  return (
    <span className="badge" title={`Level ${l}: ${title}`}>
      <span aria-hidden>{LEVEL_ICON[l] ?? "💼"}</span> {title ?? "Associate"}
    </span>
  );
}

export function StatusBadge({ e }: { e: Pick<Employee, "status" | "suspended_until"> }) {
  if (e.status === "fired") return <span className="badge down">✗ Fired</span>;
  if (e.status === "suspended") {
    const until = e.suspended_until && !e.suspended_until.startsWith("9999")
      ? new Date(e.suspended_until).toLocaleDateString("en-US", { month: "short", day: "numeric" })
      : null;
    return <span className="badge warn">⏸ Suspended{until ? ` until ${until}` : ""}</span>;
  }
  return null;
}

export function Trophies({ n }: { n?: number }) {
  if (!n) return null;
  return <span title={`${n} award${n > 1 ? "s" : ""}`} aria-label={`${n} awards`}>{"🏆".repeat(Math.min(n, 5))}{n > 5 ? `×${n}` : ""}</span>;
}
