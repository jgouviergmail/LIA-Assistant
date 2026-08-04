'use client';

/**
 * The same map, as a list — for a phone, and for anyone who asked their system
 * to minimise motion.
 *
 * Not a degraded version: the SAME data, the SAME order, the SAME destinations
 * and the same distinction between a live capability and a dormant one. What
 * it drops is the drawing, which was never where the information lived — the
 * constellation's own accessible layer is a list of buttons too.
 *
 * A 340-pixel-wide square with thirteen absolutely-positioned labels is not a
 * map, it is a pile; and an animated one for a reader who asked for stillness
 * is a refusal. Both cases get this instead.
 */

import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import { activeLabel } from './capability-state';
import { CAPABILITY_ORDER } from './constellation-layout';
import type { CapabilityNode } from '@/hooks/useCapabilities';

export interface CapabilityListProps {
  nodes: readonly CapabilityNode[];
  live: number;
  total: number;
  hrefOf: (key: string) => string;
}

export function CapabilityList({ nodes, live, total, hrefOf }: CapabilityListProps) {
  const { t } = useTranslation();
  const byKey = new Map(nodes.map(node => [node.key, node]));
  // The SAME order as the map: two surfaces describing one thing must not
  // sequence it differently.
  const ordered = CAPABILITY_ORDER.map(entry => byKey.get(entry.key)).filter(
    (node): node is CapabilityNode => node !== undefined
  );

  return (
    <section aria-labelledby="capability-list-heading" className="space-y-3">
      <div>
        <h2 id="capability-list-heading" className="text-sm font-semibold">
          {t('capabilities.map_title')}
        </h2>
        <p className="text-xs text-muted-foreground">
          {t('capabilities.map_count', { live, total })}
        </p>
      </div>

      <ul className="space-y-1.5" role="list">
        {ordered.map(node => {
          const label = t(`capabilities.nodes.${node.key}`);
          return (
            <li key={node.key}>
              <Link
                href={hrefOf(node.key)}
                className="flex min-h-11 items-center gap-3 rounded-lg border border-border/50 bg-card px-3 py-2 transition-colors hover:border-primary/40 hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span
                  className={cn(
                    'h-2.5 w-2.5 shrink-0 rounded-full',
                    node.active
                      ? 'bg-primary shadow-[0_0_8px_2px_var(--capability-bloom)]'
                      : 'bg-muted-foreground/35 ring-1 ring-border'
                  )}
                  aria-hidden="true"
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-foreground">
                    {label}
                  </span>
                  {/* The state in WORDS: a coloured dot alone tells a
                      sighted reader something and everyone else nothing. */}
                  <span className="block text-xs text-muted-foreground">
                    {/* A count is exact or it does not exist (ADR-185).
                        `personality` and `proactivity` carry no tally at all,
                        and "Active — 0 item(s)" reads as an empty capability
                        rather than as one with nothing to count. */}
                    {activeLabel(t, node)}
                  </span>
                </span>
                <ChevronRight
                  className="h-4 w-4 shrink-0 text-muted-foreground"
                  aria-hidden="true"
                />
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
