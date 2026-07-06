"use client";

/* Cross-cutting offline awareness (design/UI-DRAFT-BRIEF.md §9 state a):
   one subscription to the browser's connectivity, shared by the layout
   banner and every reading that must stamp itself "as of <time>" while
   offline. useSyncExternalStore so the server render assumes online (the
   banner is a client judgment) and the client corrects on hydration. */

import { useSyncExternalStore } from "react";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("online", onChange);
  window.addEventListener("offline", onChange);
  return () => {
    window.removeEventListener("online", onChange);
    window.removeEventListener("offline", onChange);
  };
}

const getSnapshot = () => navigator.onLine;
const getServerSnapshot = () => true;

export function useOnline(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
