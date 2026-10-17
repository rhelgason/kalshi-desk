"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { pickBook } from "@/app/actions";
import type { Book } from "@/lib/db";

/** Real (or Practice, while it's on Kalshi's demo) / Pretend: which money every page shows. */
export default function BookTabs({ value, realName }: { value: Book; realName: string }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [picked, setPicked] = useState(value);
  const choose = (b: Book) => {
    if (b === picked) return;
    setPicked(b);
    start(async () => {
      await pickBook(b);
      router.refresh();
    });
  };
  return (
    <div className="seg seg-mini book-tabs" role="tablist" aria-label="Which money" data-pending={pending || undefined}>
      {(["real", "pretend"] as Book[]).map((b) => (
        <button key={b} role="tab" aria-selected={b === picked} aria-current={b === picked ? "true" : undefined}
          className={`book-${b}`} onClick={() => choose(b)}>
          {b === "real" ? realName : "Pretend"}
        </button>
      ))}
    </div>
  );
}
