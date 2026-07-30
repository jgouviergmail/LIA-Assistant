'use client';

/**
 * Count-up display for measured figures (hero trust stats): the number is the
 * animation — echoing the landing's "every figure is measured" positioning.
 *
 * SSR/no-JS safety: the initial display IS the final formatted value; calling
 * `start()` replays the count from zero (once). Under prefers-reduced-motion
 * or a zero duration, `start()` keeps the final value (no motion).
 */

import { useCallback, useRef, useState } from 'react';
import { prefersReducedMotion } from './useCosmosScroll';

const DEFAULT_DURATION_MS = 1400;

interface CountUpOptions {
  /** Fraction digits to render (e.g. 3 for `0,001`). */
  decimals?: number;
  /** Literal suffix appended after the number (e.g. `+`, ` %`). */
  suffix?: string;
  durationMs?: number;
  /** BCP-47 locale driving the number format (fr → comma decimals). */
  locale?: string;
}

export function useCountUp(
  target: number,
  { decimals = 0, suffix = '', durationMs = DEFAULT_DURATION_MS, locale = 'en' }: CountUpOptions = {}
): { display: string; start: () => void } {
  const format = useCallback(
    (value: number) =>
      value.toLocaleString(locale, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }) + suffix,
    [locale, decimals, suffix]
  );

  const [display, setDisplay] = useState(() => format(target));
  const started = useRef(false);

  const start = useCallback(() => {
    if (started.current) return;
    started.current = true;

    if (durationMs <= 0 || prefersReducedMotion()) {
      setDisplay(format(target));
      return;
    }

    const t0 = performance.now();
    const frame = (now: number) => {
      const progress = Math.min(1, (now - t0) / durationMs);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(format(target * eased));
      if (progress < 1) requestAnimationFrame(frame);
    };
    setDisplay(format(0));
    requestAnimationFrame(frame);
  }, [durationMs, format, target]);

  return { display, start };
}
