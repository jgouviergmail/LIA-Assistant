/**
 * Card shell of a /more attention: animated stage on top (decorative,
 * aria-hidden — meaning lives in the visible title + description), then the
 * icon, translated title and description.
 *
 * The scene's `active` prop is the AND of two gates:
 *  - in-viewport (IntersectionObserver, threshold 0.35): off-screen cards
 *    schedule no timers;
 *  - `playing` from MoreAnimationContext: the page-level WCAG 2.2.2 pause.
 * prefers-reduced-motion is handled a level lower, inside useLoopedTimeline.
 */

'use client';

import type { LucideIcon } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { FadeInOnScroll } from '@/components/landing/FadeInOnScroll';

import { useMoreAnimation } from './animation-context';
import { SCENE_LABEL_KEYS } from './more-data';
import type { SceneComponent } from './scene-types';

/** Minimal translate signature — MoreContent passes react-i18next's `t`. */
export type Translate = (key: string) => string;

interface MoreCardProps {
  cardKey: string;
  icon: LucideIcon;
  scene: SceneComponent;
  t: Translate;
  /** Staggered entrance delay (ms) forwarded to FadeInOnScroll. */
  delay?: number;
}

export function MoreCard({ cardKey, icon: Icon, scene: Scene, t, delay = 0 }: MoreCardProps) {
  const { playing } = useMoreAnimation();
  const ref = useRef<HTMLLIElement>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), {
      threshold: 0.35,
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const labels = useMemo(() => {
    const resolved: Record<string, string> = {};
    for (const suffix of SCENE_LABEL_KEYS[cardKey] ?? []) {
      resolved[suffix] = t(`more.scenes.${cardKey}.${suffix}`);
    }
    return resolved;
  }, [cardKey, t]);

  // The li stays the direct <ul> child (valid list semantics for axe); the
  // entrance fade wraps the card box INSIDE it.
  return (
    <li ref={ref} className="h-full min-w-0">
      <FadeInOnScroll delay={delay} className="h-full">
        <div className="flex h-full flex-col overflow-hidden rounded-xl border border-border bg-background shadow-sm">
          <div aria-hidden="true">
            <Scene active={inView && playing} labels={labels} />
          </div>
          <div className="flex flex-1 flex-col gap-1.5 p-5">
            <span className="flex items-center gap-2.5">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
              </span>
              <h3 className="text-sm font-semibold leading-snug">
                {t(`more.cards.${cardKey}.title`)}
              </h3>
            </span>
            <p className="text-sm leading-relaxed text-muted-foreground">
              {t(`more.cards.${cardKey}.desc`)}
            </p>
          </div>
        </div>
      </FadeInOnScroll>
    </li>
  );
}
