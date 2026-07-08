'use client';

import { useEffect, useRef, useState } from 'react';

interface AnimatedCounterProps {
  target: number;
  suffix?: string;
  duration?: number;
  /** BCP 47 locale used to format the number (e.g. "fr" → 10 000). */
  locale?: string;
}

/**
 * Counts up to `target` when scrolled into view.
 *
 * The initial render shows the final value (SSR, no-JS, crawlers and
 * screenshot tools see real numbers); the count-up only replaces it once
 * the element intersects and motion is allowed.
 */
export function AnimatedCounter({
  target,
  suffix = '',
  duration = 2000,
  locale,
}: AnimatedCounterProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [value, setValue] = useState(target);
  const [hasAnimated, setHasAnimated] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || hasAnimated) return;

    // Under prefers-reduced-motion the final value is already displayed.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setHasAnimated(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setHasAnimated(true);
          observer.unobserve(el);

          const startTime = performance.now();
          const animate = (now: number) => {
            const elapsed = now - startTime;
            const progress = Math.min(elapsed / duration, 1);
            // Ease-out cubic
            const eased = 1 - Math.pow(1 - progress, 3);
            setValue(Math.round(eased * target));

            if (progress < 1) {
              requestAnimationFrame(animate);
            }
          };
          requestAnimationFrame(animate);
        }
      },
      { threshold: 0.3 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [target, duration, hasAnimated]);

  return (
    <span ref={ref} className="tabular-nums">
      {locale ? value.toLocaleString(locale) : value}
      {suffix}
    </span>
  );
}
