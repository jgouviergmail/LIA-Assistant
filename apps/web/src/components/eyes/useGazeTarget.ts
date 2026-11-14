'use client';

/**
 * useGazeTarget — the direction of the thing the face looks at, on this
 * screen, from where the face is right now.
 *
 * Re-read on a slow beat while the look is held (`GAZE_TARGET_REFRESH_MS`):
 * the answer grows, the thread scrolls, the person drags the face. No observer
 * and no listener — two rectangles a few times a second, and nothing at all
 * when the frame names no target.
 */

import { useEffect, useState, type RefObject } from 'react';

import type { Gaze } from '@/components/eyes/expression-engine';
import {
  GAZE_TARGET_REFRESH_MS,
  gazeToward,
  locateGazeTarget,
  type GazeTarget,
} from '@/components/eyes/gaze-target';

interface Look {
  target: GazeTarget;
  gaze: Gaze;
}

export function useGazeTarget(
  rootRef: RefObject<HTMLElement | null>,
  target: GazeTarget | null
): Gaze | null {
  const [look, setLook] = useState<Look | null>(null);

  useEffect(() => {
    if (!target) return;
    const measure = () => {
      const face = rootRef.current?.getBoundingClientRect();
      const viewport = { width: window.innerWidth, height: window.innerHeight };
      const point = face ? locateGazeTarget(target, viewport) : null;
      const gaze = face && point ? gazeToward(face, point, viewport) : null;
      setLook(previous => {
        if (!gaze) return null;
        const unchanged =
          previous?.target === target && previous.gaze.x === gaze.x && previous.gaze.y === gaze.y;
        return unchanged ? previous : { target, gaze };
      });
    };
    // Scheduled, never called in the effect body: a synchronous setState there
    // trips the shrink-only react-hooks ratchet.
    const first = setTimeout(measure, 0);
    const beat = setInterval(measure, GAZE_TARGET_REFRESH_MS);
    return () => {
      clearTimeout(first);
      clearInterval(beat);
    };
  }, [rootRef, target]);

  // A look belongs to the target it was measured for. Derived here rather
  // than cleared in the effect: the frame that drops its target must not
  // carry the old direction for one more render.
  return look && look.target === target ? look.gaze : null;
}
