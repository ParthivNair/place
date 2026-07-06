"use client";

import type { PlacePage, SaveKind } from "@/lib/types";
import styles from "./PlacePageHeader.module.css";

/* Save-triplet anatomy per the surface card: glyph over 13px label, ♡/✓/♥
   (design/surfaces/place-page-header.html). Hearts follow the glyph canon —
   hollow ♡ unsaved, filled ♥ saved; "been" keeps the card's ✓. */
const SEGMENTS: { kind: SaveKind; label: string }[] = [
  { kind: "want_to", label: "want-to" },
  { kind: "been", label: "been" },
  { kind: "loved", label: "loved" },
];

function segGlyph(kind: SaveKind, saved: boolean): string {
  if (kind === "been") return "✓";
  return saved ? "♥" : "♡";
}

// Photo-less launch variant of Surface 2's header (docs/02 §2): identity
// block plus the want-to/been/loved standing-query triplet. The owning page
// supplies the card surface and the section that follows.
export function PlacePageHeader({
  place,
  savedKinds,
  onToggleSave,
}: {
  place: PlacePage;
  savedKinds: Set<SaveKind>;
  onToggleSave: (kind: SaveKind) => void;
}) {
  return (
    <header>
      <div className={styles.identity}>
        <h1 className="place-name">{place.name}</h1>
        <p className={styles.locale}>
          {place.kind.replace(/_/g, " ")}
          {place.elev_m !== null && (
            <>
              {" · "}
              <span className="data">
                {place.elev_m.toLocaleString("en-US")} m
              </span>{" "}
              elevation
            </>
          )}
        </p>
      </div>

      <div className={styles.saveGroup} role="group" aria-label="Save this place">
        {SEGMENTS.map(({ kind, label }) => {
          const saved = savedKinds.has(kind);
          return (
            <button
              key={kind}
              type="button"
              className={saved ? `${styles.seg} ${styles.selected}` : styles.seg}
              aria-pressed={saved}
              onClick={() => onToggleSave(kind)}
            >
              <span className={styles.glyph} aria-hidden="true">
                {segGlyph(kind, saved)}
              </span>
              <span>{label}</span>
            </button>
          );
        })}
      </div>
    </header>
  );
}
