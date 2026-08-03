'use client';

/**
 * Brief haptic feedback, opt-out, capability-detected.
 *
 * The product is full of visual micro-interactions and had no tactile one.
 * These are deliberately short — a buzz longer than a few tens of
 * milliseconds reads as an alarm, not as an acknowledgement.
 *
 * **A sensory preference of its own.** `prefers-reduced-motion` says the
 * reader wants fewer ANIMATIONS; it says nothing about touch, and someone may
 * well want a still interface with tactile confirmation (or the reverse).
 * Conflating the two would decide for them, so this has its own switch.
 *
 * **Device-scoped, not account-scoped.** The same account on a desktop has no
 * vibration motor at all, so the preference lives in `localStorage` next to
 * the theme and the font — never in the database, which would propagate a
 * phone's choice to a laptop.
 *
 * **Silent everywhere it is unavailable.** iOS Safari does not implement
 * `navigator.vibrate`; a call there is a no-op, never an error and never a
 * message. Browsers also ignore vibrations outside a user gesture — which is
 * why every call site here sits inside a real interaction handler.
 */

/** Preference key — device-scoped, alongside the theme and font ones. */
export const HAPTICS_ENABLED_KEY = 'lia.haptics';

/**
 * What a buzz means. Durations in milliseconds; a pattern with gaps is an
 * array, as `navigator.vibrate` accepts.
 */
const PATTERNS = {
  /** Push-to-talk started — the shortest possible "I am listening". */
  start: 10,
  /** An action succeeded. */
  success: 18,
  /** Something failed: two very short pulses, never a long one. */
  error: [12, 40, 12],
  /** A commitment was closed — a deliberate, slightly fuller acknowledgement. */
  confirm: [14, 30, 14],
} as const satisfies Record<string, number | readonly number[]>;

export type HapticPattern = keyof typeof PATTERNS;

/**
 * Whether this device can vibrate at all.
 *
 * Feature detection, never user-agent sniffing: the API's presence is the
 * only honest signal, and it is exactly what decides whether the setting is
 * worth offering.
 */
export function isHapticsSupported(): boolean {
  return typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function';
}

/**
 * Whether haptics are switched on.
 *
 * Defaults to ON where the capability exists: the feedback is brief and
 * expected on touch devices, and the reader can turn it off. Storage can throw
 * (private mode, disabled cookies), and a preference that cannot be read is
 * not a reason to break a click.
 */
export function areHapticsEnabled(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(HAPTICS_ENABLED_KEY) !== 'off';
  } catch {
    return true;
  }
}

/**
 * Record the preference.
 *
 * @param enabled - True to allow haptic feedback on this device.
 */
export function setHapticsEnabled(enabled: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(HAPTICS_ENABLED_KEY, enabled ? 'on' : 'off');
  } catch {
    // Private mode: the preference simply does not persist. Refusing the
    // toggle would be worse than forgetting it.
  }
  // Notified even when storage refused: the switch must still reflect the
  // choice for this session rather than snapping back under the finger.
  for (const listener of listeners) listener();
}

/** Subscribers to the preference — `useSyncExternalStore`'s half. */
const listeners = new Set<() => void>();

/**
 * Watch the preference.
 *
 * Exists so the settings switch can read this device-scoped state through
 * `useSyncExternalStore` rather than copying it into React state from an
 * effect: `navigator` and `localStorage` do not exist during SSR, and
 * `setState`-in-an-effect is exactly the pattern the hooks ratchet forbids.
 *
 * @param onChange - Called whenever the preference changes.
 * @returns The unsubscribe function.
 */
export function subscribeHaptics(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

/**
 * Fire one brief haptic pulse, if everything allows it.
 *
 * Never throws: some browsers reject `vibrate` outside a gesture or under a
 * permissions policy, and a decorative confirmation must not break the action
 * it was confirming.
 *
 * @param pattern - Which acknowledgement this is.
 */
export function haptic(pattern: HapticPattern): void {
  if (!isHapticsSupported() || !areHapticsEnabled()) return;
  try {
    const shape = PATTERNS[pattern];
    navigator.vibrate(typeof shape === 'number' ? shape : [...shape]);
  } catch {
    // Ignored on purpose: a refused buzz is not a failure of the action.
  }
}
