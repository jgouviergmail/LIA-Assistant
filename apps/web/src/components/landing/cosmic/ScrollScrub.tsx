'use client';

/**
 * Scroll-scrub driver: writes the target section's viewport progress (0..1)
 * into its `--sp` CSS custom property on every animation frame. The section's
 * cosmos skin turns `--sp` into staggered, scroll-synchronized tile
 * choreographies — pure CSS, transform/opacity only.
 *
 * Contract: the CSS defaults `--sp: 1` (final state) so no-JS/SEO renders are
 * complete; under prefers-reduced-motion the driver pins 1 (static finals).
 * Targeting by id keeps the shared section components untouched.
 */

import { useEffect } from 'react';
import { prefersReducedMotion, sectionProgress, useCosmosScroll } from './useCosmosScroll';

interface ScrollScrubProps {
  targetId: string;
  /**
   * Copies each descendant's inline `animation-delay` into its `--d` custom
   * property (once, on mount) so the scrub windows inherit the scene's
   * original stagger order — used by the chapter vignettes, whose stagger is
   * inline (`stage(delayMs)`), not class-based.
   */
  syncStageDelays?: boolean;
}

export function ScrollScrub({ targetId, syncStageDelays = false }: ScrollScrubProps) {
  useEffect(() => {
    if (!syncStageDelays) return;
    const host = document.getElementById(targetId);
    if (!host) return;
    host.querySelectorAll<HTMLElement>('[style*="animation-delay"]').forEach(el => {
      const ms = parseFloat(el.style.animationDelay);
      if (!Number.isNaN(ms)) {
        el.style.setProperty('--d', String(ms));
      }
    });
  }, [targetId, syncStageDelays]);

  useCosmosScroll(() => {
    const host = document.getElementById(targetId);
    if (!host) return;
    const value = prefersReducedMotion()
      ? 1
      : sectionProgress(host.getBoundingClientRect(), window.innerHeight);
    host.style.setProperty('--sp', value.toFixed(4));
  });

  return null;
}
