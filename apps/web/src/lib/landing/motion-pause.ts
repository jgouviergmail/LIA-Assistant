/**
 * The public cosmos pages' « pause the animations » choice.
 *
 * WCAG 2.2.2 (Pause, Stop, Hide, level A): the nebula's drift, the planet's
 * clouds and the landing's attention canvas start on their own and last longer
 * than five seconds, so the page carries a mechanism to stop them — decorative
 * motion is not exempt, only essential motion is, and `prefers-reduced-motion`
 * is an operating-system preference, not a page control (the /more scenes'
 * toggle answers the same rule).
 *
 * The whole state is ONE attribute on `<html>`, `data-motion="paused"`: the
 * cosmos stylesheet pauses its animations on it, the attention canvas reads it
 * at every frame, and the /more scenes join it. The choice itself is a
 * per-viewer convenience kept in localStorage — every access wrapped, so a
 * private window or blocked storage simply starts animated.
 */

const STORAGE_KEY = 'lia_cosmos_motion_paused';
const PAUSED = 'paused';
/** Dispatched on `window` after every change, for `useSyncExternalStore`. */
export const MOTION_EVENT = 'lia:motion';

/** Whether the cosmos animations are paused right now. */
export function isMotionPaused(): boolean {
  return document.documentElement.dataset.motion === PAUSED;
}

/** The viewer's stored choice; false when nothing is stored or storage is unavailable. */
export function readStoredMotionPaused(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function applyMotionPaused(paused: boolean): void {
  const root = document.documentElement;
  if (paused) root.dataset.motion = PAUSED;
  else delete root.dataset.motion;
  window.dispatchEvent(new Event(MOTION_EVENT));
}

/** Applies the stored choice to the page (a page load starts from it). */
export function restoreMotionPreference(): void {
  if (readStoredMotionPaused() !== isMotionPaused()) applyMotionPaused(readStoredMotionPaused());
}

/** Pauses or resumes the cosmos animations, and remembers the choice. */
export function setMotionPaused(paused: boolean): void {
  applyMotionPaused(paused);
  try {
    if (paused) window.localStorage.setItem(STORAGE_KEY, '1');
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable (private window, blocked site data): the choice
    // still holds for this page, it is just not remembered.
  }
}

/** `useSyncExternalStore` subscription to the paused state. */
export function subscribeMotion(onChange: () => void): () => void {
  window.addEventListener(MOTION_EVENT, onChange);
  return () => window.removeEventListener(MOTION_EVENT, onChange);
}
