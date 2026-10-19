import { SPRITES, spriteRects } from "@/lib/sprites";

/** An employee's 8-bit portrait; falls back to their emoji if they don't have one yet. */
export default function Avatar({ k, emoji, size = 32, className }: { k: string; emoji?: string; size?: number; className?: string }) {
  const s = SPRITES[k];
  if (!s) return <span className={className} style={{ fontSize: size * 0.8, lineHeight: 1 }} aria-hidden>{emoji ?? "🙂"}</span>;
  return (
    <svg className={`avatar ${className ?? ""}`} width={size} height={size} viewBox={`0 0 ${s.rows[0].length} ${s.rows.length}`} shapeRendering="crispEdges" aria-hidden>
      {spriteRects(s).map((r, i) => <rect key={i} x={r.x} y={r.y} width={r.w} height={1} fill={r.fill} />)}
    </svg>
  );
}
