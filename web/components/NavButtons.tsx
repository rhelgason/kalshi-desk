"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { pickBook } from "@/app/actions";
import HeaderLink from "./HeaderLink";
import type { Book } from "@/lib/db";

/**
 * The main sections (11-16). The manager: My office (the real book, where the app always opens), Cockpit (every
 * office side by side) and Training (pretend money). A friend: their office and the cockpit's light version.
 */
export default function NavButtons({ book, hasLive, manager, inOffice = false }: {
  book: Book; hasLive: boolean; manager: boolean;
  /** the manager is looking at a friend's office: Cockpit goes back to their own view too */
  inOffice?: boolean;
}) {
  const path = usePathname();
  const router = useRouter();
  const [picked, setPicked] = useState(book);
  const [pending, start] = useTransition();
  useEffect(() => setPicked(book), [book]);
  // The loading bar across the top (NavProgress) while the office switches
  useEffect(() => {
    if (pending) document.documentElement.dataset.navigating = "";
    else delete document.documentElement.dataset.navigating;
  }, [pending]);

  const choose = (b: Book) => {
    setPicked(b);
    start(async () => {
      await pickBook(b);
      if (path === "/") router.refresh();
      else router.push("/");
    });
  };
  const onCockpit = path.startsWith("/cockpit");
  const lit = (b: Book) => (!onCockpit && path === "/" && picked === b ? "page" : undefined);
  return (
    <span className="views" data-pending={pending || undefined}>
      {manager ? (
        <>
          {hasLive && <button className="nav-btn" aria-current={lit("real")} onClick={() => choose("real")}>My office</button>}
          <HeaderLink className="nav-btn" href="/cockpit" leave={inOffice} aria-current={onCockpit ? "page" : undefined}>Cockpit</HeaderLink>
          <button className="nav-btn" aria-current={lit("pretend")} onClick={() => choose("pretend")}>Training</button>
        </>
      ) : (
        <>
          <Link className="nav-btn" href="/" aria-current={!onCockpit && path === "/" ? "page" : undefined}>My office</Link>
          <Link className="nav-btn" href="/cockpit" aria-current={onCockpit ? "page" : undefined}>Cockpit</Link>
        </>
      )}
    </span>
  );
}
