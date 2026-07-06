/* Question copy + selection for the Sunday verdict sheet (docs/02 §2
   Surface 4, rendered as design/surfaces/sunday-push.html). The API serves
   no claim question text — ClaimOut carries class and provenance only, the
   same gap ClaimRow leads with a class label to cover — so the canon
   questions live client-side, keyed by the shared canon claim ids
   (lib/claimIds.ts — the same constants the fixtures use, so a rename
   breaks the compile instead of orphaning a question).

   A claim with no entry is never asked: a one-tap favor needs a precisely
   phrased question, and one good question beats two mushy ones. Flagged API
   gap — the server should serve question_text alongside allowed_verdicts. */

import { CLAIM_HR_JUMP_DEPTH, CLAIM_HR_ROPE_SWING } from "@/lib/claimIds";
import type { ClaimOut } from "@/lib/types";

// Verbatim question copy from design/surfaces/sunday-push.html — about
// claims, never experience; no "How was it?" exists in this product.
const QUESTIONS: Record<string, string> = {
  [CLAIM_HR_JUMP_DEPTH]: "Was it swimmable?",
  [CLAIM_HR_ROPE_SWING]: "Is the rope swing still up?",
};

/* Selection rule from the sunday-push card header: at most two questions,
   drawn from the visited place's claims by (1 − confidence) × decay_rate.
   The rates restate ClaimRow's docs/01 §5 half-lives as re-check
   frequencies per year: hazard calibration decays in weeks, access in
   months, seasonal timing in years, geomorphic features in decades. */
const DECAY_PER_YEAR: Record<string, number> = {
  hazard_calibration: 26,
  access: 12,
  seasonal_bio: 1,
  geomorphic: 0.1,
};

export const MAX_QUESTIONS = 2;

export interface SundayQuestion {
  claim: ClaimOut;
  text: string;
}

export function selectQuestions(claims: ClaimOut[]): SundayQuestion[] {
  return claims
    .filter((c) => QUESTIONS[c.id] !== undefined && c.allowed_verdicts.length > 0)
    .map((claim) => ({
      claim,
      text: QUESTIONS[claim.id],
      score: (1 - claim.confidence) * (DECAY_PER_YEAR[claim.cclass] ?? 12),
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, MAX_QUESTIONS)
    .map(({ claim, text }) => ({ claim, text }));
}

/* Eyebrow noun for "1 of 2 · wild-swim claim". Hazard calibration is about
   the activity itself, so it wears the activity name (sunday-push.html q1);
   other classes use ClaimRow's plain-language class words. */
const CCLASS_WORDS: Record<string, string> = {
  geomorphic: "feature",
  seasonal_bio: "seasonal",
  access: "access",
  hazard_calibration: "hazard",
};

export function eyebrowWord(claim: ClaimOut, activityName: string | null): string {
  if (claim.cclass === "hazard_calibration" && activityName) {
    return activityName.trim().toLowerCase().replace(/\s+/g, "-");
  }
  return CCLASS_WORDS[claim.cclass] ?? claim.cclass.replace(/_/g, " ");
}
