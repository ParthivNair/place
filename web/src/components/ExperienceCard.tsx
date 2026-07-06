"use client";

import type { FeedCard } from "@/lib/types";
import { fmtDriveMinutes } from "@/lib/format";
import { AffordanceStrip } from "./AffordanceStrip";
import { PrimaryButton, SaveHeart, TertiaryButton } from "./Buttons";
import { ConditionBadge } from "./ConditionBadge";
import { ProvenanceLine } from "./ProvenanceLine";
import { SafetyLine } from "./SafetyLine";
import styles from "./ExperienceCard.module.css";

/* Leave No Trace rides every card foot (docs/02 §5.4 — never behind a tap).
   Per-place permit notes are data the feed API does not serve yet
   (UI-DRAFT-BRIEF cheat sheet); SafetyLine's `permit` slot stays empty
   until it does. */
const STEWARDSHIP = "pack it out";

/* The atomic unit of the feed (docs/02 §3). Variants come from the data,
   never from props: a fresh live reason renders condition-magic, empty
   reasons render everyday, assumption_of_risk renders the hazard well,
   live_unavailable renders the degraded "live … unavailable" rows — all
   decided inside the leaves. */
export function ExperienceCard({
  card,
  saved,
  onSave,
  onGoing,
  onMore,
}: {
  card: FeedCard;
  saved: boolean;
  onSave: () => void;
  onGoing: () => void;
  onMore: () => void;
}) {
  // "41 min drive" — the minutes are measured (.data); the word is not.
  const drive = fmtDriveMinutes(card.distance_km);
  const driveValue = drive.replace(/ drive$/, "");

  return (
    <article className={styles.card}>
      <header className={styles.identity}>
        <div className={styles.idMain}>
          <h2 className="place-name">{card.place_name}</h2>
          {/* place_kind is a snake_case enum ("swimming_hole") */}
          <p className={styles.context}>{card.place_kind.replace(/_/g, " ")}</p>
        </div>
        <div className={styles.aside}>
          <span className={styles.drive}>
            <span className="data">{driveValue}</span>
            {drive.slice(driveValue.length)}
          </span>
          <SaveHeart saved={saved} onToggle={onSave} />
        </div>
      </header>

      <div className={styles.prov}>
        <ProvenanceLine
          reasons={card.reasons}
          liveUnavailable={card.live_unavailable}
          lastVerifiedAt={card.last_verified_at}
          verifiedBy={card.verified_by}
        />
      </div>

      {card.hazard_class && (
        <div className={styles.hazardChip}>
          <ConditionBadge state="hazard" label="hazard-gated" />
        </div>
      )}

      <div className={styles.strip}>
        <AffordanceStrip
          activityName={card.activity_name}
          difficulty={card.difficulty}
          typicalDurationMin={card.typical_duration_min}
          dogOk={card.dog_ok}
          kidOk={card.kid_ok}
        />
      </div>

      <div className={styles.foot}>
        <SafetyLine
          assumptionOfRisk={card.assumption_of_risk}
          stewardship={STEWARDSHIP}
        />
      </div>

      <div className={styles.actions}>
        <div className={styles.primarySlot}>
          <PrimaryButton onClick={onGoing}>I’m going</PrimaryButton>
        </div>
        <TertiaryButton onClick={onMore}>more conditions →</TertiaryButton>
      </div>
    </article>
  );
}
