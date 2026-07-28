/**
 * Motion preference helper shared by components that arm one-shot animations
 * from JavaScript (avatar emotion bursts, send-button takeoff, celebration
 * particles). The CSS kill-switch in `globals.css` silences the keyframes, but
 * a component that WAITS on `onAnimationEnd` must not arm an animation that
 * will never run — it would wait forever.
 */

/** True when the user asked the OS to minimize non-essential motion. */
export function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}
