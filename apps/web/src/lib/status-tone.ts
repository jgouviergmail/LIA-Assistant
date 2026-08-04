/**
 * Which badge tone a status deserves — decided once, for the whole app.
 *
 * Three components used to carry their own `Record<string, string>` of Tailwind
 * classes for the same job. Hand-written classes bypass the design-system
 * contrast guard (which covers `Badge`'s variants across five themes × light
 * and dark), and they drifted: `high` and `medium` both rendered as a
 * 10 %-opacity tint of two tokens only 23° apart in OKLCH hue
 * (`--color-destructive` at 27°, `--color-warning` at 50°). Measured on real
 * data — 89 `high` rows and 113 `medium` rows that the reader could not tell
 * apart.
 *
 * So these functions name a TONE and `Badge` renders it. **Density, not hue
 * alone, carries the hierarchy**: `alert` is a SOLID fill, `warning` a tint,
 * `secondary` neutral — a distinction that survives two hues the eye reads as
 * one, and one that still works in monochrome. The first attempt used
 * `destructive`, whose badge ground is itself a pale tint, and the two levels
 * still looked alike on a real screen.
 *
 * Every unknown value returns the NEUTRAL tone. A status the backend adds
 * later must not arrive shouting: rendering an unrecognised level in red would
 * be a claim about urgency nobody made.
 */

/** The `Badge` variants this module is allowed to return. */
export type BadgeTone =
  | 'default'
  | 'alert'
  | 'secondary'
  | 'success'
  | 'destructive'
  | 'warning'
  | 'info'
  | 'outline';

const NEUTRAL: BadgeTone = 'secondary';

/** Heartbeat notification priority: `low` | `medium` | `high`. */
const PRIORITY: Record<string, BadgeTone> = {
  // SOLID, not the pale `destructive`: measured on screen, a red-100 ground and
  // a warning/10 ground are the same level to the eye.
  high: 'alert',
  medium: 'warning',
  low: NEUTRAL,
};

/** Provenance outcome: what a signal did to a belief. */
const OUTCOME: Record<string, BadgeTone> = {
  origin: 'info',
  evidence: 'success',
  contradiction: 'warning',
};

/** Which way an exchanged message or email travelled. */
const DIRECTION: Record<string, BadgeTone> = {
  sent: 'info',
  received: 'success',
};

/**
 * Tone for a notification priority.
 *
 * Args:
 *   priority: The raw value, as the backend published it.
 *
 * Returns:
 *   The badge variant; neutral for anything this build does not know.
 */
export function priorityTone(priority: string): BadgeTone {
  return PRIORITY[priority] ?? NEUTRAL;
}

/**
 * Tone for a provenance outcome.
 *
 * Args:
 *   outcome: `origin`, `evidence` or `contradiction`.
 *
 * Returns:
 *   The badge variant; neutral for anything this build does not know.
 */
export function outcomeTone(outcome: string): BadgeTone {
  return OUTCOME[outcome] ?? NEUTRAL;
}

/**
 * Tone for the direction of an exchange.
 *
 * Args:
 *   direction: `sent` or `received`.
 *
 * Returns:
 *   The badge variant; neutral for anything this build does not know.
 */
export function directionTone(direction: string): BadgeTone {
  return DIRECTION[direction] ?? NEUTRAL;
}
