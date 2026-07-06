"use client";

import { useEffect } from "react";

/* Registers the service worker after mount. Feature-detected and silent on
   failure — the app is fully usable without offline shell or push. */
export default function SwRegister() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // PWA extras degrade silently
    });
  }, []);
  return null;
}
