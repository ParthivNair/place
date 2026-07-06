/* Canon claim ids (44… block — see lib/mock.ts id scheme). Split out of
   mock.ts so client copy keyed by claim id (the Sunday question text in
   app/sunday/sunday-questions.ts) shares one constant with the fixtures:
   a rename here breaks the compile instead of silently orphaning the
   question. mock.ts imports these; importing THIS file never bundles the
   fixtures into a real build (api.ts loads mock.ts lazily on purpose). */

export const CLAIM_TAMANAWAS_FLOW = "44444444-0000-4000-8000-000000000001";
export const CLAIM_HR_JUMP_DEPTH = "44444444-0000-4000-8000-000000000002";
export const CLAIM_HR_ACCESS = "44444444-0000-4000-8000-000000000003";
export const CLAIM_HR_ROPE_SWING = "44444444-0000-4000-8000-000000000004";
export const CLAIM_HR_WALK_PATH = "44444444-0000-4000-8000-000000000005";
export const CLAIM_DOG_BALSAMROOT = "44444444-0000-4000-8000-000000000006";
export const CLAIM_SPRINGVILLE_GATE = "44444444-0000-4000-8000-000000000007";
export const CLAIM_SPRINGVILLE_SHADE = "44444444-0000-4000-8000-000000000008";
export const CLAIM_MULTNOMAH_PERMIT = "44444444-0000-4000-8000-000000000009";
export const CLAIM_PITTOCK_PARKING = "44444444-0000-4000-8000-000000000010";
export const CLAIM_WILDWOOD_MUD = "44444444-0000-4000-8000-000000000011";
