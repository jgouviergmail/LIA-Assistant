'use client';

import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

/**
 * One-shot scroll trigger for the chapter vignettes. Children carry the
 * mockup's fill-both keyframe classes (chip-pop, wire-draw, fan-draw…);
 * globals.css keeps them `animation-play-state: paused` until this wrapper
 * gains `.staged`, so each figure choreographs itself exactly once, when the
 * visitor reaches it. Under prefers-reduced-motion the same staging applies,
 * but the global kill-switch zeroes the durations — the figure appears in
 * its final state instantly, with no motion.
 */

export function ScrollStage({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [staged, setStaged] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    // No reduced-motion branch needed: the global kill-switch zeroes the
    // keyframe durations, so staging on arrival shows the final state
    // instantly — and the effect never calls setState outside the callback.
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setStaged(true);
          observer.unobserve(el);
        }
      },
      { threshold: 0.35 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className={cn('scroll-stage', staged && 'staged', className)}>
      {children}
    </div>
  );
}
