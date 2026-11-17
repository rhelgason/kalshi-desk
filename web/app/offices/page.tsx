import { redirect } from "next/navigation";

/** Invites moved to the cockpit (11-17); old links land there. */
export default function OfficesPage() {
  redirect("/cockpit");
}
