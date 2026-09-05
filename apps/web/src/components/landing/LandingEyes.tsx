'use client';

/**
 * LIA's eyes on the public landing — the same widget as the chat, on its
 * own surface.
 *
 * The visitor may have no account: the widget needs none. Its three chat
 * signals sit at rest here, the psyche store defaults to disabled (ADR-240's
 * graceful degradation) and everything the face does on its own — breath,
 * idle gestures, mimics, sketches — plays on a resting expression. The
 * position dragged here is the landing's own (`EyesSurface`), so it never
 * lands on the chat's Delete button; size and visibility are shared, and the
 * look is FORCED to the capsules here (owner choice, 2026-09-05): the visitor
 * has no preference yet, and the chat keeps the user's own.
 *
 * Loaded lazily: the landing is the first page a visitor sees, and the rig
 * with its tables must not be on its critical path (bundle discipline).
 * Client-only, because the widget positions itself from the viewport.
 */

import dynamic from 'next/dynamic';

const EyesWidget = dynamic(
  () => import('@/components/eyes/EyesWidget').then(module => module.EyesWidget),
  { ssr: false }
);

export function LandingEyes() {
  return (
    <EyesWidget
      surface="landing"
      styleId="capsules"
      chatStatus="idle"
      streamPhase="answer"
      hitlAwaiting={false}
    />
  );
}
