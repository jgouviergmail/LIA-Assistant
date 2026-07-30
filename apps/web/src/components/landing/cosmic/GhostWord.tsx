'use client';

/**
 * Giant outlined word floating behind a section — the cosmos identity's
 * signature background device. The word is TRANSLATED (it must carry the
 * section's meaning in every locale) but decorative for AT (`aria-hidden`):
 * the section headings already say it accessibly.
 *
 * The lateral drift is driven by the section's scroll progress (direction
 * alternates per section). Transform-only, clipped by the host section
 * (`overflow: clip` via the `.cosmos section` rule), silent under
 * prefers-reduced-motion.
 */

import { useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { prefersReducedMotion, sectionProgress, useCosmosScroll } from './useCosmosScroll';

/** Fraction of the viewport width the word travels across its section. */
const DRIFT_FACTOR = 0.24;

interface GhostWordProps {
  /** i18n key under `landing.cosmos.ghost.*` — one short word per locale. */
  wordKey: string;
  /** Drift direction; alternate 1 / -1 between consecutive sections. */
  direction: 1 | -1;
  className?: string;
}

export function GhostWord({ wordKey, direction, className }: GhostWordProps) {
  const { t } = useTranslation();
  const ref = useRef<HTMLSpanElement>(null);

  useCosmosScroll(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion()) return;
    const host = el.closest('section') ?? el.parentElement;
    if (!host) return;
    const rect = host.getBoundingClientRect();
    const progress = sectionProgress(rect, window.innerHeight);
    const x = (progress - 0.5) * window.innerWidth * DRIFT_FACTOR * direction;
    el.style.transform = `translateX(${x.toFixed(1)}px)`;
  });

  // Outer frame: static, screen-aligned edge fade (mask). Inner word: drifts.
  return (
    <span aria-hidden="true" className={cn('cosmos-ghost-frame', className)}>
      <span ref={ref} className="cosmos-ghost">
        {t(wordKey)}
      </span>
    </span>
  );
}
