import { ago } from "@/lib/format";

/** Bot heartbeat: Live / Stale / Offline, always with a text label, not color alone. */
export default function StatusPill({ updatedAt }: { updatedAt?: string | null }) {
  const age = updatedAt ? (Date.now() - Date.parse(updatedAt)) / 1000 : Infinity;
  const [label, color, icon] =
    age < 180 ? ["Live", "var(--good)", "●"] : age < 1800 ? ["Stale", "var(--warning)", "▲"] : ["Offline", "var(--critical)", "■"];
  return (
    <span className="pill" title={updatedAt ?? "no data"}>
      <span aria-hidden style={{ color, fontSize: 10 }}>{icon}</span>
      <strong style={{ color: "var(--text-primary)", fontWeight: 600 }}>{label}</strong>
      <span>updated {ago(updatedAt)}</span>
    </span>
  );
}
