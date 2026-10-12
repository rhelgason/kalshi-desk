"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/** The two big arcade buttons; the current page lights up. */
export default function NavButtons() {
  const path = usePathname();
  const here = (p: string) => (p === "/" ? path === "/" : path.startsWith(p)) ? "page" : undefined;
  return (
    <>
      <Link href="/" className="nav-btn" aria-current={here("/")}>Money</Link>
      <Link href="/office" className="nav-btn" aria-current={here("/office")}>Office</Link>
    </>
  );
}
