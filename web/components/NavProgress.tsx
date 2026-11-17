"use client";

import { useEffect } from "react";

/**
 * A thin bar across the top while the next page loads (11-16), so every link and button that changes page shows
 * its click was taken. It starts on a click of a link to another page of the site or on a form sent, and stops
 * when the server's next render arrives: the layout hands over a new `stamp` each time it renders.
 */
export default function NavProgress({ stamp }: { stamp: number }) {
  useEffect(() => {
    delete document.documentElement.dataset.navigating;
  }, [stamp]);
  useEffect(() => {
    const html = document.documentElement;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const start = () => {
      html.dataset.navigating = "";
      clearTimeout(timer);
      timer = setTimeout(() => delete html.dataset.navigating, 15_000); // never spin forever
    };
    const click = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as Element).closest?.("a[href]") as HTMLAnchorElement | null;
      if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
      const to = new URL(a.href, location.href);
      if (to.origin !== location.origin || (to.pathname === location.pathname && to.search === location.search)) return;
      start();
    };
    const submit = () => start();
    document.addEventListener("click", click);
    document.addEventListener("submit", submit);
    return () => { document.removeEventListener("click", click); document.removeEventListener("submit", submit); clearTimeout(timer); };
  }, []);
  return <div className="nav-progress" aria-hidden />;
}
