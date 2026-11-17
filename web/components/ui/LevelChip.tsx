import { levelTitle } from "@/lib/hr";

/** An employee's level as a coloured chip (11-16), the same everywhere: grey-green Intern up to gold Partner. */
export default function LevelChip({ level, control, benched }: { level?: number; control?: boolean; benched?: boolean }) {
  if (control) return <span className="lvl lvl-yard" title="Control group: bets at random, so the others have something to beat">Yardstick</span>;
  if (benched) return <span className="lvl lvl-benched">Benched</span>;
  const l = level ?? 1;
  return <span className={`lvl lvl-${l}`} title="Level: higher levels bet more of the pool">{levelTitle(l)}</span>;
}
