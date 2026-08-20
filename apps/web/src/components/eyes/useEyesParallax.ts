'use client';

/**
 * useEyesParallax — desktop-only cursor gaze-follow for the eyes widget.
 *
 * Strictly gated: fine hover pointer, motion-safe, and only while the caller
 * says the gaze is free (idle-like expressions). The parallax EXPIRES after a
 * still cursor (PARALLAX_IDLE_MS) so the idle wander takes the gaze back —
 * that alternation is what reads as "alive". Extracted from EyesWidget as a
 * cohesive unit (shrink-only CC ratchet).
 */

import { useEffect, useState, type RefObject } from 'react';

import { prefersReducedMotion } from '@/lib/utils/motion';
import type { Gaze } from '@/components/eyes/expression-engine';

/** A still cursor hands the gaze back to the idle wander after this long. */
export const PARALLAX_IDLE_MS = 2500;

export function useEyesParallax(
  rootRef: RefObject<HTMLDivElement | null>,
  active: boolean
): Gaze | null {
  const [parallax, setParallax] = useState<Gaze | null>(null);

  useEffect(() => {
    if (!active) return;
    if (prefersReducedMotion()) return;
    if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
    let raf: number | null = null;
    let expiry: ReturnType<typeof setTimeout> | null = null;
    const onMove = (e: PointerEvent) => {
      if (raf !== null) return;
      raf = requestAnimationFrame(() => {
        raf = null;
        const rect = rootRef.current?.getBoundingClientRect();
        if (!rect) return;
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        setParallax({
          x: Math.min(1, Math.max(-1, (e.clientX - cx) / (window.innerWidth / 2))),
          y: Math.min(1, Math.max(-1, (e.clientY - cy) / (window.innerHeight / 2))),
        });
        if (expiry) clearTimeout(expiry);
        expiry = setTimeout(() => setParallax(null), PARALLAX_IDLE_MS);
      });
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => {
      window.removeEventListener('pointermove', onMove);
      if (raf !== null) cancelAnimationFrame(raf);
      if (expiry) clearTimeout(expiry);
      setParallax(null);
    };
  }, [active, rootRef]);

  return parallax;
}
