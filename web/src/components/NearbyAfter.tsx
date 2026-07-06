"use client";

import styles from "./NearbyAfter.module.css";

// The après pairing module (docs/07 §4, docs/02 §2) — the only commercial
// surface. Pairing suggestions, never destinations: a commercial POI is an
// edge in the outdoor graph, or it is Google's turf. Each tap writes a
// PAIRS_WITH observation; the noted row is the receipt.
// NOTE: data source is mock-only until a PAIRS_WITH endpoint exists
// (UI-DRAFT-BRIEF gap 16) — the parent page supplies canon fixture items.
export interface NearbyItem {
  name: string;
  type: string;
  minutes: number;
}

export function NearbyAfter({
  items,
  noted,
  onNote,
}: {
  items: NearbyItem[];
  noted: Set<string>;
  onNote: (name: string) => void;
}) {
  if (items.length === 0) return null;

  return (
    <section className={styles.module}>
      <header className={styles.head}>
        <h2 className={styles.title}>Nearby after</h2>
      </header>
      <ul className={styles.list}>
        {items.map((item) => (
          <li key={item.name}>
            {noted.has(item.name) ? (
              <div className={styles.rowNoted}>
                <span className={styles.name}>{item.name}</span>
                <span className={styles.notedMark}>✓ noted</span>
              </div>
            ) : (
              <button
                type="button"
                className={styles.row}
                onClick={() => onNote(item.name)}
              >
                <span className={styles.name}>{item.name}</span>
                <span className={styles.meta}>
                  {item.type} · <span className="data">{item.minutes} min</span>
                </span>
                <span className={styles.chev} aria-hidden="true">
                  →
                </span>
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
