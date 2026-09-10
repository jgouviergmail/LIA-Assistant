'use client';

/**
 * useEyesDrag — the eyes widget's drag, on the shared floating-drag machine.
 *
 * Only the persisted SLOT is the eyes' own: each surface keeps its spot (see
 * `EyesSurface`), and everything about moving — the pointer threshold, the
 * arrow keys, the re-clamp on resize — is `useFloatingDrag`, which the
 * shortcuts dock rides too (ADR-277).
 */

import type { RefObject } from 'react';

import { useFloatingDrag, type FloatingDrag } from '@/hooks/useFloatingDrag';
import { useEyesWidgetStore, type EyesSurface } from '@/stores/eyesWidgetStore';

export type EyesDrag = FloatingDrag<HTMLDivElement>;

/** Generic over the surface: the widget is a `div`, its restore dot a `button`. */
export function useEyesDrag<T extends HTMLElement = HTMLDivElement>(
  rootRef: RefObject<T | null>,
  surface: EyesSurface = 'chat'
): FloatingDrag<T> {
  const position = useEyesWidgetStore(s =>
    surface === 'landing' ? s.landingPosition : s.position
  );
  const setPosition = useEyesWidgetStore(s =>
    surface === 'landing' ? s.setLandingPosition : s.setPosition
  );
  return useFloatingDrag(rootRef, position, setPosition);
}
