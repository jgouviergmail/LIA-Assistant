/**
 * Eye-style registry — single source of truth for the selectable looks of the
 * expressive-eyes widget (settings › preferences › personalization).
 *
 * Adding a style costs exactly three things, each enforced by the sibling
 * completeness test (`eye-styles.test.ts` — red until all three exist):
 *   1. its id in EYE_STYLE_IDS below;
 *   2. a scoped recipe block in `styles/eyes.css` (`[data-style='<id>'] …`);
 *   3. `eyes.styles.<id>.{name,description}` in the six locale files.
 * Everything else — expressions, idle life, gestures, emotes, blink, gaze,
 * anchoring — is style-agnostic and comes for free.
 */

export const EYE_STYLE_IDS = [
  'cozmo',
  'capsules',
  'billes',
  'amande',
  'traits',
  'anneaux',
] as const;

export type EyeStyleId = (typeof EYE_STYLE_IDS)[number];

/** The base sheet IS this style — it needs no scoped CSS block. */
export const DEFAULT_EYE_STYLE: EyeStyleId = 'cozmo';

/** Strict runtime guard (persisted values, future deep links). */
export function isValidEyeStyle(value: unknown): value is EyeStyleId {
  return typeof value === 'string' && (EYE_STYLE_IDS as readonly string[]).includes(value);
}
