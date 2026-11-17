"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { leaveOffice } from "@/app/account";

/**
 * A link in the header (11-16). While the manager is looking at a friend's office, any of them goes back to the
 * manager's own view on the way: the office is for looking around in, not somewhere the header stays.
 */
export default function HeaderLink({ href, leave, className, children, ...rest }: {
  href: string; leave: boolean; className?: string; children: React.ReactNode; "aria-current"?: "page";
}) {
  const router = useRouter();
  const path = usePathname();
  if (!leave) return <Link href={href} className={className} {...rest}>{children}</Link>;
  return (
    <a href={href} className={className} {...rest} onClick={async (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
      e.preventDefault();
      document.documentElement.dataset.navigating = "";
      await leaveOffice();
      if (path === href) router.refresh();
      else router.push(href);
    }}>{children}</a>
  );
}
