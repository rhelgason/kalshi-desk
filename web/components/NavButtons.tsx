"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { pickBook } from "@/app/actions";
import type { Book } from "@/lib/db";

/**
 * The two books: Live (the Kalshi account) and Training (pretend money).
 * Live only appears once the live book has reported; the current view lights up.
 */
export default function NavButtons({ book, hasLive }: { book: Book; hasLive: boolean }) {
  const path = usePathname();
  const router = useRouter();
  const [picked, setPicked] = useState(book);
  const [pending, start] = useTransition();
  useEffect(() => setPicked(book), [book]);

  const choose = (b: Book) => {
    setPicked(b);
    start(async () => {
      await pickBook(b);
      if (path.startsWith("/settings") || path.startsWith("/backtests") || path.startsWith("/admin")) router.push("/");
      else router.refresh();
    });
  };
  const lit = (b: Book) => (picked === b ? "page" : undefined);
  return (
    <span className="views" data-pending={pending || undefined}>
      {hasLive && (
        <button className="nav-btn view-live" aria-current={lit("real")} onClick={() => choose("real")}>Live</button>
      )}
      <button className="nav-btn" aria-current={lit("pretend")} onClick={() => choose("pretend")}>Training</button>
    </span>
  );
}
