"use client";

import { useEffect } from "react";
import { captureInstallPrompt } from "@/lib/installPrompt";

/* Parks the once-per-document beforeinstallprompt event for /welcome
   (lib/installPrompt.ts). Mounted in the root layout beside SwRegister so
   the event is caught no matter which route loaded the document. */
export default function InstallPromptCapture() {
  useEffect(() => {
    captureInstallPrompt();
  }, []);
  return null;
}
