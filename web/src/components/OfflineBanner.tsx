"use client";

import { usePathname } from "next/navigation";
import { useOnline } from "@/lib/online";
import styles from "./OfflineBanner.module.css";

/* Offline shell banner (design/UI-DRAFT-BRIEF.md §9 state a) — designed
   once, mounted once in the root layout so every route degrades the same
   way. The page below keeps rendering whatever was last cached (sw.js
   replays the shell; ProvenanceLine stamps every reading "as of <time>"
   while offline) and this banner owns saying so. Canon copy on the feed;
   other routes carry the same honesty without claiming to be the feed.
   navigator.onLine is the only dependency — no service worker, no cache,
   still this banner, still a usable app (graceful-failure rule). */
export default function OfflineBanner() {
  const online = useOnline();
  const pathname = usePathname();
  if (online) return null;
  return (
    <p className={styles.banner} role="status">
      {pathname === "/"
        ? "You’re offline — showing Thursday’s feed"
        : "You’re offline — showing what we last checked"}
    </p>
  );
}
