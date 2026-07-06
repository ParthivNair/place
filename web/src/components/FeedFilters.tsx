"use client";

import { useId } from "react";
import styles from "./FeedFilters.module.css";

export interface FeedFilterState {
  verb: string;
  driveMin: 30 | 60 | 90;
  dogOk: boolean;
  kidOk: boolean;
}

// ≤90 min is the polygon — the whole universe (docs/02 §2 Surface 1).
const DRIVE_OPTIONS = [30, 60, 90] as const;

// Verb chips are shortcuts into the same value the browse field edits —
// a feed filter, not a search engine (docs/07 §1); NL search is deferred.
const VERB_CHIPS = ["trail", "swim", "waterfall", "walk", "viewpoint"] as const;

export function FeedFilters({
  value,
  onChange,
}: {
  value: FeedFilterState;
  onChange: (v: FeedFilterState) => void;
}) {
  const baseId = useId();
  const activeVerb = value.verb.trim().toLowerCase();

  const chipClass = (on: boolean) =>
    on ? `${styles.chip} ${styles.isOn}` : styles.chip;

  return (
    <div>
      <input
        type="text"
        className={styles.browse}
        value={value.verb}
        onChange={(e) => onChange({ ...value, verb: e.target.value })}
        placeholder="Try &ldquo;trail&rdquo;, &ldquo;swim&rdquo;, &ldquo;walk&rdquo;&hellip;"
        aria-label="Filter by activity"
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="none"
        spellCheck={false}
      />

      <div className={styles.filter}>
        <div className={styles.filterLabel} id={`${baseId}-drive`}>
          drive time
        </div>
        <div
          className={styles.chips}
          role="group"
          aria-labelledby={`${baseId}-drive`}
        >
          {DRIVE_OPTIONS.map((min) => (
            <button
              key={min}
              type="button"
              className={chipClass(value.driveMin === min)}
              aria-pressed={value.driveMin === min}
              onClick={() => onChange({ ...value, driveMin: min })}
            >
              <span className="data">&le;{min} min</span>
            </button>
          ))}
        </div>
      </div>

      <div className={styles.filter}>
        <div className={styles.filterLabel} id={`${baseId}-verb`}>
          activity
        </div>
        <div
          className={styles.chips}
          role="group"
          aria-labelledby={`${baseId}-verb`}
        >
          {VERB_CHIPS.map((verb) => (
            <button
              key={verb}
              type="button"
              className={chipClass(activeVerb === verb)}
              aria-pressed={activeVerb === verb}
              onClick={() =>
                onChange({ ...value, verb: activeVerb === verb ? "" : verb })
              }
            >
              {verb}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.filter}>
        <div className={styles.filterLabel} id={`${baseId}-with`}>
          with
        </div>
        <div
          className={styles.chips}
          role="group"
          aria-labelledby={`${baseId}-with`}
        >
          <button
            type="button"
            className={chipClass(value.dogOk)}
            aria-pressed={value.dogOk}
            onClick={() => onChange({ ...value, dogOk: !value.dogOk })}
          >
            dogs
          </button>
          <button
            type="button"
            className={chipClass(value.kidOk)}
            aria-pressed={value.kidOk}
            onClick={() => onChange({ ...value, kidOk: !value.kidOk })}
          >
            kids
          </button>
        </div>
      </div>
    </div>
  );
}
