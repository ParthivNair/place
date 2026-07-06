/* beforeinstallprompt stash. Chromium fires the event once per document
   load — usually while the user is still on the feed — so if /welcome is
   reached by client-side navigation the event is long gone and the install
   ask degrades to menu-hunting copy. InstallPromptCapture (mounted in the
   root layout) parks the event here; /welcome consumes it. */

/* Not in lib.dom — typed by hand (welcome/page.tsx precedent). */
export interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

let stashed: BeforeInstallPromptEvent | null = null;
let listening = false;

export function captureInstallPrompt(): void {
  if (listening || typeof window === "undefined") return;
  listening = true;
  window.addEventListener("beforeinstallprompt", (e: Event) => {
    e.preventDefault(); // hold the browser's own banner; the ask is placed
    stashed = e as BeforeInstallPromptEvent;
  });
}

/* Peek, don't pop: a BeforeInstallPromptEvent invalidates itself after
   prompt(), so the consumer clears it explicitly once used. */
export function peekInstallPrompt(): BeforeInstallPromptEvent | null {
  return stashed;
}

export function clearInstallPrompt(): void {
  stashed = null;
}
