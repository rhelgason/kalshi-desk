import Link from "next/link";
import { RANGES, type RangeKey } from "@/lib/portfolio";

/** Day / Week / Month / 3 months / Season. Links, so the choice survives refreshes and can be shared. */
export default function RangeTabs({ value, path, params = {} }: { value: RangeKey; path: string; params?: Record<string, string> }) {
  return (
    <nav className="seg" aria-label="Time range">
      {(Object.keys(RANGES) as RangeKey[]).map((k) => {
        const q = new URLSearchParams({ ...params, range: k });
        return (
          <Link key={k} href={`${path}?${q}`} aria-current={k === value ? "true" : undefined} scroll={false} replace>
            {RANGES[k].label}
          </Link>
        );
      })}
    </nav>
  );
}
