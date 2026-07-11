import { mockFeed, mockSaves, mockSearchResults } from "@/lib/mock";
import PlaceClient from "./PlaceClient";

/* Server shell so the static export (GitHub Pages demo) can prerender the
   canon fixture places — the only ids mock mode ever links to. Build-time
   only: the fixtures never reach the client bundle (lib/api.ts keeps its
   lazy import). A future server deployment renders other ids on demand. */
export function generateStaticParams() {
  const ids = new Set<string>();
  for (const card of mockFeed.cards) ids.add(card.place_id);
  for (const result of mockSearchResults) ids.add(result.id);
  for (const save of mockSaves) ids.add(save.place_id);
  return [...ids].map((id) => ({ id }));
}

export default async function PlaceRoute({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <PlaceClient id={id} />;
}
