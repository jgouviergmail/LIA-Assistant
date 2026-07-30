'use client';

/**
 * One hero trust figure that counts up on arrival — the number IS the
 * animation (measured-figures doctrine). SSR renders the final value.
 */

import { useEffect } from 'react';
import { useCountUp } from './useCountUp';

interface TrustStatProps {
  value: number;
  suffix?: string;
  label: string;
  locale: string;
}

export function TrustStat({ value, suffix = '', label, locale }: TrustStatProps) {
  const { display, start } = useCountUp(value, { suffix, locale });

  useEffect(() => {
    start();
  }, [start]);

  return (
    <span className="flex items-center gap-1.5">
      <span className="font-semibold text-foreground tabular-nums">{display}</span> {label}
    </span>
  );
}
