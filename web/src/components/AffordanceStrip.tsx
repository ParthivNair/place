import { Fragment, type ReactNode } from "react";
import { fmtDurationMin } from "@/lib/format";
import styles from "./AffordanceStrip.module.css";

/* The reified Affordance node, rendered (docs/00 §7 · docs/02 §3):
   verb · difficulty · typical duration · dog/kid flags. Sits below the
   provenance line; drive time is NOT here — it lives in the card header. */

/* Difficulty is a claim attribute → plain UI word, never the raw number:
   1–2 easy · 3 moderate · 4–5 hard. */
function difficultyWord(difficulty: number): "easy" | "moderate" | "hard" {
  if (difficulty <= 2) return "easy";
  if (difficulty <= 3) return "moderate";
  return "hard";
}

/* "·" glued to the prior term (nbsp inside the sep span), breakable
   space before the next — matches the spec DOM exactly. */
function DotSeparated({ terms }: { terms: ReactNode[] }) {
  return (
    <>
      {terms.map((term, i) => (
        <Fragment key={i}>
          {i > 0 && (
            <>
              <span className={styles.sep}>&nbsp;·</span>{" "}
            </>
          )}
          {term}
        </Fragment>
      ))}
    </>
  );
}

export function AffordanceStrip({
  activityName,
  difficulty,
  typicalDurationMin,
  dogOk,
  kidOk,
}: {
  activityName: string;
  difficulty?: number | null;
  typicalDurationMin?: number | null;
  dogOk?: boolean | null;
  kidOk?: boolean | null;
}) {
  const terms: ReactNode[] = [
    <span key="verb" className={styles.verb}>
      {activityName}
    </span>,
  ];
  if (difficulty != null) terms.push(difficultyWord(difficulty));
  if (typicalDurationMin != null) {
    terms.push(
      <span key="duration" className="data">
        {fmtDurationMin(typicalDurationMin)}
      </span>,
    );
  }

  /* null = unknown = omitted entirely; false is a known fact and renders. */
  const flags: ReactNode[] = [];
  if (dogOk != null) flags.push(dogOk ? "dogs ok" : "no dogs");
  if (kidOk != null) flags.push(kidOk ? "kids ok" : "no kids");

  return (
    <>
      <p className={styles.strip}>
        <DotSeparated terms={terms} />
      </p>
      {flags.length > 0 && (
        <p className={`${styles.strip} ${styles.flags}`}>
          <DotSeparated terms={flags} />
        </p>
      )}
    </>
  );
}
