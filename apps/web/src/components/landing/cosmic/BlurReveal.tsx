'use client';

/**
 * Blur→sharp one-shot reveal (the mockup's "proofs" device). Same staging
 * pattern as the editorial `ScrollStage`: an IntersectionObserver adds the
 * final-state class once, then unobserves. Under prefers-reduced-motion the
 * content renders in its final state immediately.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

const REVEAL_THRESHOLD = 0.25;

interface BlurRevealProps {
  children: ReactNode;
  /** Stagger delay in milliseconds (cascades sibling reveals). */
  delay?: number;
  className?: string;
}

export function BlurReveal({ children, delay = 0, className }: BlurRevealProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(false);

  // No reduced-motion branch needed (and no setState-in-effect): the cosmos
  // CSS kill-switch already forces `.cosmos-reveal` to its final visual state
  // under prefers-reduced-motion, so the class toggle is inert there.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          observer.unobserve(el);
        }
      },
      { threshold: REVEAL_THRESHOLD }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={cn('cosmos-reveal', inView && 'in', className)}
      style={delay > 0 ? { transitionDelay: `${delay}ms` } : undefined}
    >
      {children}
    </div>
  );
}
