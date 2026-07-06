import styles from "./ConditionBadge.module.css";

export type ConditionState = "live" | "fading" | "unknown" | "hazard" | "verified";

/* Marker follows the glyph canon: solid dot for live/fading/hazard, hollow
   ring (○) for unknown — signal absent — and ✓ for verified only. `sublabel`
   is the measured-value slot and always wears the .data signature; claim
   words belong in `label`, in the UI font. */
export function ConditionBadge({
  state,
  label,
  sublabel,
}: {
  state: ConditionState;
  label: string;
  sublabel?: string;
}) {
  return (
    <span className={`${styles.badge} ${styles[state]}`}>
      {state === "verified" ? (
        <span className={styles.glyph} aria-hidden="true">
          ✓
        </span>
      ) : (
        <span
          className={
            state === "unknown" ? `${styles.dot} ${styles.dotHollow}` : styles.dot
          }
          aria-hidden="true"
        />
      )}
      {label}
      {sublabel !== undefined && (
        <>
          {/* U+00A0 around the dot, per the spec's &nbsp;·&nbsp; — plain
              spaces collapse at the flex-item boundary and render tighter
              than the mock */}
          {" · "}
          <span className="data">{sublabel}</span>
        </>
      )}
    </span>
  );
}
