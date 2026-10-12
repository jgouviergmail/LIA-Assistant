'use client';

/**
 * LIA's eyes on the public landing — the same widget as the chat, on its
 * own surface.
 *
 * The visitor may have no account: the widget needs none. Its three chat
 * signals sit at rest here, the psyche store defaults to disabled (ADR-240's
 * graceful degradation) and everything the face does on its own — breath,
 * idle gestures, mimics, sketches — plays on a resting expression. The
 * position dragged here is the landing's own (`EyesSurface`). The public
 * presentation is BIP masculine, always awake, at the largest size on desktop. Narrow
 * screens omit the floating widget so it cannot cover the proof or actions.
 * It is independent
 * of the visitor's saved application style, size and gender.
 *
 * Loaded lazily: the landing is the first page a visitor sees, and the rig
 * with its tables must not be on its critical path (bundle discipline).
 * Client-only, because the widget positions itself from the viewport.
 */

import dynamic from 'next/dynamic';
import { useMediaQuery } from '@/hooks/useMediaQuery';

const EyesWidget = dynamic(
  () => import('@/components/eyes/EyesWidget').then(module => module.EyesWidget),
  { ssr: false }
);

export function LandingEyes() {
  const narrow = useMediaQuery('(max-width: 639px)');
  if (narrow) return null;
  return (
    <EyesWidget
      surface="landing"
      styleId="bip"
      size="xl"
      variant="male"
      chatStatus="idle"
      streamPhase="answer"
      hitlAwaiting={false}
    />
  );
}
