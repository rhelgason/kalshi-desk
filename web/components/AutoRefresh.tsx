"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Re-fetch server data every `seconds` so the dashboard stays live. */
export default function AutoRefresh({ seconds = 60 }: { seconds?: number }) {
  const router = useRouter();
  useEffect(() => {
    const id = setInterval(() => router.refresh(), seconds * 1000);
    return () => clearInterval(id);
  }, [router, seconds]);
  return null;
}
