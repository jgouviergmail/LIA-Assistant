'use client';

/**
 * Scroll-pinned stage: a tall wrapper (`heights` × 100dvh) whose sticky child
 * stays on screen while the visitor's scroll drives a 0→1 progress, exposed
 * both as the `--p` CSS custom property (consumed by `.cosmos-track` /
 * `.cosmos-progress`) and through the optional `onProgress` callback.
 *
 * Sticky positioning works since ADR-171 (`body { overflow-x: clip }`); this
 * component never introduces a scrollport ancestor. On mobile (≤ the site's
 * 880px breakpoint), under prefers-reduced-motion, or when `disabled`, the
 * children render in normal flow — no pin, no vars.
 */

import { useRef, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { clamp01, useCosmosScroll, useMediaFlag } from './useCosmosScroll';

const MOBILE_QUERY = '(max-width: 880px)';
const REDUCED_QUERY = '(prefers-reduced-motion: reduce)';

interface PinnedSceneProps {
  children: ReactNode;
  /** Total scene height in viewport-heights (scroll room for the pin). */
  heights?: number;
  /** Force the static fallback regardless of viewport. */
  disabled?: boolean;
  /** Called with the clamped 0..1 progress on each animation frame. */
  onProgress?: (progress: number) => void;
  className?: string;
}

export function PinnedScene({
  children,
  heights = 3.2,
  disabled = false,
  onProgress,
  className,
}: PinnedSceneProps) {
  const ref = useRef<HTMLDivElement>(null);
  const isMobile = useMediaFlag(MOBILE_QUERY);
  const isReduced = useMediaFlag(REDUCED_QUERY);
  const isStatic = disabled || isMobile || isReduced;

  useCosmosScroll(() => {
    const el = ref.current;
    if (!el || isStatic) return;
    const total = el.offsetHeight - window.innerHeight;
    if (total <= 0) return;
    const progress = clamp01(-el.getBoundingClientRect().top / total);
    el.style.setProperty('--p', progress.toFixed(4));
    onProgress?.(progress);
  });

  if (isStatic) {
    return <div className={className}>{children}</div>;
  }

  return (
    <div ref={ref} className={cn('cosmos-pin', className)} style={{ height: `${heights * 100}dvh` }}>
      <div className="cosmos-pin-stage">{children}</div>
    </div>
  );
}
