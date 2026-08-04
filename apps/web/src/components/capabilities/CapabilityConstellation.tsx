'use client';

/**
 * The constellation — a star chart of what LIA can actually do for you.
 *
 * The first version of this was a hub-and-spoke diagram: dots on two circles,
 * every one wired to a centre, a uniform pulse. That is a network graph with an
 * astronomical label on it. A star chart is a different object, and the
 * difference carries information:
 *
 * - **the figure joins the LIVE capabilities to each other**, never to a hub,
 *   and in ANGULAR order so it reads as an outline rather than a knot
 *   (`figureOutline`). Activating something extends the figure, so its shape IS
 *   this account's configuration — nobody else has the same one. That is the
 *   map's signature, and it is state made visible, not decoration;
 * - **magnitude**: a star's size comes from what it holds (log-scaled, tightly
 *   bounded). Four hundred memories shine brighter than three. An atlas draws
 *   brightness; so does this;
 * - **dormant stars are open circles**, the way an atlas draws an unlit one —
 *   present, placed, waiting. Not greyed-out clutter.
 *
 * Motion, deliberately, and in ONE orchestrated arrival rather than scattered
 * effects: the stars resolve in angular order (`--capability-delay`), then the
 * figure draws itself between them (`capability-trace`), and the field settles
 * into a 240 s rotation — 1.5°/s, invisible frame to frame, alive over a
 * minute. Every star counter-rotates at the same rate so no label ever tilts.
 * Differential ring speeds would read better as orbital mechanics, but the
 * figure spans both rings and would have to be redrawn every frame; the figure
 * is the stronger idea, so the accessory goes.
 *
 * **Accessibility is not a layer under the drawing, it IS the drawing's twin.**
 * The SVG is decorative and `aria-hidden`; every reachable thing is a real
 * `<Link>` with a stable translated name. A `<circle>` with an onClick would
 * look identical and be unusable without a mouse. Reduced motion keeps the
 * chart and loses only the movement — the information was never in the motion.
 */

import Link from 'next/link';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import { nodeName } from './capability-state';
import { ConstellationSky } from './ConstellationSky';
import { figureOutline, layoutCapabilities, type NodePosition } from './constellation-layout';
import type { CapabilityNode } from '@/hooks/useCapabilities';

export interface CapabilityConstellationProps {
  nodes: readonly CapabilityNode[];
  live: number;
  total: number;
  /** Where each capability is set up — the node's next step. */
  hrefOf: (key: string) => string;
  /** Silence the movement without changing the chart. */
  reducedMotion?: boolean;
}

/**
 * A star's radius, in viewBox units, from what the capability holds.
 *
 * Logarithmic and clamped: an account with four thousand memories must read as
 * "brighter", not as a blob swallowing its neighbours. A dormant star keeps the
 * smallest radius — it is placed and waiting, not absent.
 */
function magnitude(node: CapabilityNode): number {
  // A dormant star is deliberately not the smallest thing on the chart. At
  // 1.2 it rendered as ~7 px of dashed outline — three dashes, read as an
  // artefact rather than as a capability. These ARE the next steps the map
  // exists to offer; too faint to see is the same as absent.
  if (!node.active) return 2;
  const held = Math.max(node.detail ?? 0, 1);
  return Math.min(1.7 + Math.log10(held + 1) * 1.2, 3.3);
}

/** One star: a real link, positioned over the decorative chart. */
function Star({
  node,
  position,
  href,
  delayMs,
}: {
  node: CapabilityNode;
  position: NodePosition;
  href: string;
  delayMs: number;
}) {
  const { t } = useTranslation();
  const label = t(`capabilities.nodes.${node.key}`);
  // The NAME states the state, not only the subject: "Memory, active" and
  // "Memory, to set up" are different destinations for the same word — and it
  // never invents a tally for a capability that has none (`nodeName`).
  const name = nodeName(t, node, label);
  const size = magnitude(node) * 5.6;

  return (
    <Link
      href={href}
      aria-label={name}
      style={{
        left: `${position.x}%`,
        top: `${position.y}%`,
        ['--capability-delay' as string]: `${delayMs}ms`,
      }}
      className={cn(
        'group absolute -translate-x-1/2 -translate-y-1/2 rounded-xl px-2 py-1.5',
        // The focus ring is the scene's own, not the app's: `--color-ring`
        // inverts to near-black in light mode, which on this night would be an
        // invisible focus ring — the one affordance that must never be.
        'outline-none focus-visible:ring-2 focus-visible:ring-[var(--capability-focus)]'
      )}
    >
      {/* The counter-rotation lives on an INNER wrapper, never on the
          positioned link: both would write `transform`, and the animation
          would silently drop the -50 % centring that places the star. */}
      <span className="capability-star-upright flex flex-col items-center gap-2">
        <span className="capability-emerge relative flex h-9 w-9 items-center justify-center">
          {/* The bloom: always on a live star, revealed under the pointer or
              the focus ring on a dormant one — a promise of what lighting it
              up would look like. */}
          <span
            className={cn(
              'absolute inset-0 rounded-full blur-md transition-opacity duration-500',
              node.active
                ? 'bg-[var(--capability-star)] opacity-60'
                : 'bg-[var(--capability-star)] opacity-0 group-hover:opacity-40 group-focus-visible:opacity-40'
            )}
            aria-hidden="true"
          />
          <span
            className={cn(
              'relative rounded-full transition-transform duration-300 motion-safe:group-hover:scale-125',
              node.active
                ? 'bg-[var(--capability-star)] shadow-[0_0_12px_3px_var(--capability-bloom)]'
                : // An OPEN circle, the way an atlas draws an unlit star:
                  // present, placed, waiting. A dashed edge was the mistake —
                  // at this size a dash pattern has room for three segments
                  // and reads as noise, not as a convention.
                  'border-[1.5px] border-[var(--capability-ink-dim)] bg-[var(--capability-sky)]/70 group-hover:border-[var(--capability-focus)]'
            )}
            style={{ width: `${size}px`, height: `${size}px` }}
            aria-hidden="true"
          />
        </span>

        <span className="flex flex-col items-center gap-0.5" aria-hidden="true">
          <span
            className={cn(
              'max-w-28 truncate text-center text-[11px] leading-tight tracking-wide transition-colors',
              node.active
                ? 'font-medium text-[var(--capability-ink)]'
                : 'text-[var(--capability-ink-dim)] group-hover:text-[var(--capability-ink)]'
            )}
          >
            {label}
          </span>
          {/* The magnitude line, in the vernacular of a catalogue: revealed on
              approach rather than crowding thirteen stars at rest. */}
          <span
            className={cn(
              'text-[9px] uppercase tracking-[0.14em] tabular-nums text-[var(--capability-ink-dim)]',
              'opacity-0 transition-opacity duration-300',
              'group-hover:opacity-100 group-focus-visible:opacity-100'
            )}
          >
            {node.active && node.detail !== null
              ? t('capabilities.magnitude', { count: node.detail })
              : '—'}
          </span>
        </span>
      </span>
    </Link>
  );
}

export function CapabilityConstellation({
  nodes,
  live,
  total,
  hrefOf,
  reducedMotion = false,
}: CapabilityConstellationProps) {
  const { t } = useTranslation();
  const positions = layoutCapabilities(nodes.map(node => node.key));
  const byKey = new Map(nodes.map(node => [node.key, node]));
  const outline = figureOutline(positions, position => byKey.get(position.key)?.active === true);
  // Stars resolve the way the figure is drawn — angular order, so the arrival
  // reads as one sweep instead of two rings taking turns.
  const arrival = new Map(
    [...positions]
      .sort((a, b) => Math.atan2(a.y - 50, a.x - 50) - Math.atan2(b.y - 50, b.x - 50))
      .map((position, index) => [position.key, index * 70])
  );

  return (
    <section aria-labelledby="constellation-heading" className="space-y-5">
      <header className="space-y-1">
        <p className="text-[10px] font-medium uppercase tracking-[0.2em] text-primary">
          {t('capabilities.map_eyebrow')}
        </p>
        <h2 id="constellation-heading" className="text-lg font-semibold tracking-tight">
          {t('capabilities.map_title')}
        </h2>
        {/* A COUNT of this account's own capabilities. Never a percentage of
            completion, and never anybody else's figure. */}
        <p className="text-xs text-muted-foreground">
          {t('capabilities.map_count', { live, total })}
        </p>
      </header>

      <div
        className={cn(
          'relative mx-auto aspect-square w-full max-w-3xl overflow-hidden rounded-[2rem]',
          'border border-border/50 capability-scene'
        )}
      >
        {/* The breathing wash sits BEHIND the rotating field and never turns
            with it: a drifting glow under a drifting field reads as a wobble. */}
        <div
          className={cn(
            'pointer-events-none absolute left-1/2 top-1/2 h-[70%] w-[70%] -translate-x-1/2 -translate-y-1/2 rounded-full',
            !reducedMotion && 'capability-halo'
          )}
          aria-hidden="true"
        />

        <div className={cn('absolute inset-0', !reducedMotion && 'capability-field')}>
          <ConstellationSky outline={outline} reducedMotion={reducedMotion} />

          {positions.map(position => {
            const node = byKey.get(position.key);
            if (!node) return null;
            return (
              <Star
                key={position.key}
                node={node}
                position={position}
                href={hrefOf(node.key)}
                delayMs={arrival.get(position.key) ?? 0}
              />
            );
          })}
        </div>
      </div>

      {/* A chart nobody can read is an ornament. Three lines: what a filled
          star means, what an outlined one means, and what size encodes — the
          three conventions the drawing actually uses, and no more. */}
      <ul className="mx-auto flex max-w-3xl flex-wrap items-center justify-center gap-x-5 gap-y-2 text-[11px] text-muted-foreground">
        <li className="flex items-center gap-2">
          <span
            className="h-2 w-2 rounded-full bg-[var(--capability-star)]"
            aria-hidden="true"
          />
          {t('capabilities.legend_active')}
        </li>
        <li className="flex items-center gap-2">
          <span
            className="h-2 w-2 rounded-full border border-current"
            aria-hidden="true"
          />
          {t('capabilities.legend_dormant')}
        </li>
        <li className="flex items-center gap-2">
          <span className="flex items-end gap-0.5" aria-hidden="true">
            <span className="h-1 w-1 rounded-full bg-current" />
            <span className="h-2 w-2 rounded-full bg-current" />
          </span>
          {t('capabilities.legend_size')}
        </li>
      </ul>
    </section>
  );
}
