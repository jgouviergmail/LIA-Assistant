/**
 * Which authorships a register reading holds — the frontend half of
 * `domains/agents/effects/origin.py`.
 *
 * Both journals read the same vocabulary. Two copies of "what counts as mine"
 * is how the Actions tab and the Consultations tab come to disagree about the
 * same row, which is exactly what the backend module refuses on its side.
 *
 * Declared as a RUNTIME list rather than a bare union, for the same reason
 * `EFFECT_SOURCES` is: a union exists only at compile time, so no guard can
 * compare it to the enum the API actually emits. `EffectSource` gained a
 * fourth value while this side still listed three, and nothing could see it.
 */

/** `mine` = everything the person set in motion; `initiative` = LIA's own. */
export const REGISTER_ORIGINS = ['mine', 'initiative', 'all'] as const;

export type RegisterOrigin = (typeof REGISTER_ORIGINS)[number];
