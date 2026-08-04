/**
 * The sky the capabilities are plotted on — decorative, and nothing else.
 *
 * Everything in this file is `aria-hidden` by construction: the reachable
 * layer is the set of `<Link>` stars its parent draws on top. Kept apart from
 * `CapabilityConstellation` because it is a different KIND of thing — the
 * parent decides what is true about this account, this file only draws the
 * atmosphere that makes those truths legible.
 *
 * What is drawn, from back to front, and why each earns its place:
 *
 *  - **the deep field**: a radial wash that darkens outwards, so the eye falls
 *    to the centre where the account's own figure is;
 *  - **the dust**: ninety fixed points of light. Depth, at a cost of one draw
 *    call and no state. Deterministic (`backdropStars`) and kept clear of the
 *    centre — on this map a dot is a claim about a capability, so decorative
 *    dust must never sit where a capability could;
 *  - **the orbits**: the two rings the layout actually places on. They are
 *    structure made visible, not ornament: they answer "why is that one
 *    further out?" (it extends the assistant rather than carrying it);
 *  - **the figure**: the account's own outline. It DRAWS ITSELF on arrival —
 *    `stroke-dasharray` running from fully dashed to solid over 1.8 s. This is
 *    the one orchestrated moment on the page, and it is the thing worth
 *    remembering: the shape is nobody else's.
 *
 * Colour comes from the scene's OWN tokens (`--capability-*`), never from the
 * theme's: the night stays night in light mode, so a token that inverts would
 * paint the sky onto itself. The landing's `--cosmos-*` palette is scoped to
 * `.cosmos`, a class the dashboard does not carry — reading one here paints
 * nothing at all.
 */

import { backdropStars, type NodePosition } from './constellation-layout';
import { cn } from '@/lib/utils';

/** Radii of the two rings, mirrored from the layout (percent of the box). */
const ORBITS = [24, 42] as const;

const DUST = backdropStars();

export interface ConstellationSkyProps {
  /** The account's outline, in angular order. Empty draws no figure. */
  outline: readonly NodePosition[];
  /** Silence the drawing-in without losing the figure. */
  reducedMotion?: boolean;
}

export function ConstellationSky({ outline, reducedMotion = false }: ConstellationSkyProps) {
  const points = outline.map(position => `${position.x},${position.y}`).join(' ');

  return (
    <svg
      viewBox="0 0 100 100"
      className="absolute inset-0 h-full w-full text-[var(--capability-star)]"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <radialGradient id="capability-deep-field">
          <stop offset="0%" stopColor="var(--capability-star)" stopOpacity="0.16" />
          <stop offset="55%" stopColor="var(--capability-star)" stopOpacity="0.05" />
          <stop offset="100%" stopColor="var(--capability-star)" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="capability-nucleus">
          <stop offset="0%" stopColor="var(--capability-star)" stopOpacity="0.9" />
          <stop offset="45%" stopColor="var(--capability-star)" stopOpacity="0.3" />
          <stop offset="100%" stopColor="var(--capability-star)" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="capability-figure" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--capability-star)" stopOpacity="0.9" />
          <stop offset="50%" stopColor="var(--capability-accent)" stopOpacity="0.75" />
          <stop offset="100%" stopColor="var(--capability-star)" stopOpacity="0.55" />
        </linearGradient>
      </defs>

      <circle cx="50" cy="50" r="50" fill="url(#capability-deep-field)" />

      <g fill="currentColor">
        {DUST.map(star => (
          <circle
            key={`${star.x}-${star.y}`}
            cx={star.x}
            cy={star.y}
            r={star.r}
            opacity={star.o}
          />
        ))}
      </g>

      {ORBITS.map(radius => (
        <circle
          key={radius}
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeOpacity="0.12"
          strokeWidth="0.15"
          strokeDasharray="0.8 1.6"
        />
      ))}

      {outline.length > 1 && (
        <polygon
          points={points}
          fill="var(--capability-star)"
          fillOpacity="0.06"
          stroke="url(#capability-figure)"
          strokeWidth="0.45"
          strokeLinejoin="round"
          // `pathLength` normalises the perimeter to 100 whatever the shape, so
          // one dash pattern draws every possible figure at the same speed.
          pathLength={100}
          className={cn(!reducedMotion && 'capability-trace')}
        />
      )}

      <circle cx="50" cy="50" r="12" fill="url(#capability-nucleus)" />
      <circle cx="50" cy="50" r="1.9" fill="var(--capability-star)" />
      <circle
        cx="50"
        cy="50"
        r="4.2"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.35"
        strokeWidth="0.2"
      />
    </svg>
  );
}
