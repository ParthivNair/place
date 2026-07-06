import styles from "./SafetyLine.module.css";

/* Card foot, per design/components/safety-line.html. The assumption-of-risk
   well renders the server's string verbatim — it exists only when the
   publication gates pass (docs/02 §5.1), so presence of the prop is the
   only condition checked here. A closure note replaces the foot entirely:
   closed places carry no permit line because they carry no actions. */
export function SafetyLine({
  assumptionOfRisk,
  permit,
  stewardship,
  closure,
}: {
  assumptionOfRisk?: string | null;
  permit?: string | null;
  stewardship?: string | null;
  closure?: string | null;
}) {
  if (closure) {
    return (
      <div className={styles.closure}>
        <span className={styles.closureGlyph} aria-hidden="true">
          ●
        </span>
        <p className={styles.closureLead}>{closure}</p>
      </div>
    );
  }

  const hasMeta = Boolean(permit) || Boolean(stewardship);
  if (!hasMeta && !assumptionOfRisk) return null;

  return (
    <div className={styles.foot}>
      {hasMeta && (
        <p className={styles.safety}>
          {permit && <span className={styles.permit}>{permit}</span>}
          {permit && stewardship && " · "}
          {stewardship}
        </p>
      )}
      {assumptionOfRisk && (
        <div className={styles.risk}>
          <p className={styles.riskText}>{assumptionOfRisk}</p>
        </div>
      )}
    </div>
  );
}
