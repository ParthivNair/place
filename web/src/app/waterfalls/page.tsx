import type { Metadata } from "next";
import { WaterfallsTool } from "./WaterfallsTool";

/* Surface 4 — /waterfalls, the October 2026 public launch page and the
   app's only desktop surface (UI-DRAFT-BRIEF §4, decision 13). This
   server shell exists for the SEO half of the brief ("best waterfalls
   near Portland right now"); the tool itself is a client component so
   the ♥ → email-capture conversion works without a session. */

export const metadata: Metadata = {
  title: "Gorge waterfalls, ranked by current flow — Place",
  description:
    "Ten Columbia River Gorge waterfalls ranked by today's flow — 72-h NWS " +
    "rain and creek gauges, re-checked every morning. The best waterfalls " +
    "near Portland right now.",
};

export default function WaterfallsPage() {
  return <WaterfallsTool />;
}
