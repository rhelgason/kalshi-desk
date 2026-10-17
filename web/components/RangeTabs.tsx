"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { type RangeKey } from "@/lib/portfolio";

const SHORT: Record<RangeKey, string> = { day: "Day", week: "Week", month: "Month", quarter: "3 Mo", season: "All" };

/**
 * Day / Week / Month / 3 months / All (since the fresh start). Links, so the choice survives refreshes and can be shared.
 * The tapped tab lights up straight away and the chart dims while the new range loads.
 */
export default function RangeTabs({ value, path, params = {} }: { value: RangeKey; path: string; params?: Record<string, string> }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [picked, setPicked] = useState(value);
  useEffect(() => setPicked(value), [value]);
  return (
    <nav className="seg" aria-label="Time range" data-pending={pending || undefined}>
      {(Object.keys(SHORT) as RangeKey[]).map((k) => {
        const href = `${path}?${new URLSearchParams({ ...params, range: k })}`;
        return (
          <Link key={k} href={href} aria-current={k === picked ? "true" : undefined} scroll={false} replace
            onClick={(ev) => {
              if (ev.metaKey || ev.ctrlKey || ev.shiftKey) return; // new tab: let the browser handle it
              ev.preventDefault();
              setPicked(k);
              start(() => router.replace(href, { scroll: false }));
            }}>
            {SHORT[k]}
          </Link>
        );
      })}
    </nav>
  );
}
