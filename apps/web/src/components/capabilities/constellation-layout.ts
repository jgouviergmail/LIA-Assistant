/**
 * Where each capability sits on the map — computed, and DETERMINISTIC.
 *
 * No physics, no randomness, no simulation: the same account draws the same
 * picture on every visit, which is what lets a reader build a mental image of
 * their own assistant instead of re-reading a new arrangement each time. It is
 * also what makes the map testable — a force layout can only be asserted on
 * "something moved".
 *
 * Two rings around a centre. The inner ring holds the capabilities the
 * assistant leans on constantly, the outer one what extends it; both are
 * ordered by `CAPABILITY_ORDER`, so adding a capability never reshuffles the
 * ones already there. A node absent from the payload (the instance disabled
 * it) simply leaves its slot empty rather than collapsing the ring — the map
 * keeps its shape across instances.
 */

/** Display order and ring of every capability the map can draw. */
export const CAPABILITY_ORDER: readonly { key: string; ring: 'inner' | 'outer' }[] = [
  { key: 'connectors', ring: 'inner' },
  { key: 'memory', ring: 'inner' },
  { key: 'personality', ring: 'inner' },
  { key: 'voice', ring: 'inner' },
  { key: 'proactivity', ring: 'inner' },
  { key: 'interests', ring: 'outer' },
  { key: 'routines', ring: 'outer' },
  { key: 'relations', ring: 'outer' },
  { key: 'peers', ring: 'outer' },
  { key: 'channels', ring: 'outer' },
  { key: 'spaces', ring: 'outer' },
  { key: 'journals', ring: 'outer' },
  { key: 'skills', ring: 'outer' },
];

/** Percentage radii — the map is rendered in a square, unit-free box. */
const RADIUS = { inner: 24, outer: 42 } as const;

export interface NodePosition {
  key: string;
  /** Percentage of the box width, from its left edge. */
  x: number;
  /** Percentage of the box height, from its top edge. */
  y: number;
  ring: 'inner' | 'outer';
}

/**
 * Place every capability of one ring on a circle.
 *
 * Args:
 *   keys: The capabilities of that ring, in display order.
 *   ring: Which circle.
 *   phase: Rotation offset in turns, so the two rings do not align their
 *     spokes — aligned spokes read as a grid, not as a constellation.
 *
 * Returns:
 *   One position per key, in the order given.
 */
function placeRing(
  keys: readonly string[],
  ring: 'inner' | 'outer',
  phase: number
): NodePosition[] {
  const radius = RADIUS[ring];
  return keys.map((key, index) => {
    const turn = keys.length === 0 ? 0 : (index / keys.length + phase) * Math.PI * 2;
    return {
      key,
      // Rounded to a tenth of a percent: enough precision for the eye, and a
      // stable string in a snapshot or an e2e assertion.
      x: Math.round((50 + radius * Math.cos(turn)) * 10) / 10,
      y: Math.round((50 + radius * Math.sin(turn)) * 10) / 10,
      ring,
    };
  });
}

/**
 * The map's layout for the capabilities this instance actually offers.
 *
 * Args:
 *   offered: Keys present in the payload. Unknown keys are dropped rather
 *     than placed at an arbitrary spot — a capability the client cannot name
 *     would appear as an unlabelled dot.
 *
 * Returns:
 *   One position per drawable capability, inner ring first.
 */
export function layoutCapabilities(offered: readonly string[]): NodePosition[] {
  const present = new Set(offered);
  const known = CAPABILITY_ORDER.filter(entry => present.has(entry.key));
  const inner = known.filter(entry => entry.ring === 'inner').map(entry => entry.key);
  const outer = known.filter(entry => entry.ring === 'outer').map(entry => entry.key);
  // `-0.25` starts the inner ring at the top; the outer one is offset by half
  // a slot so the two rings interleave instead of forming spokes.
  return [
    ...placeRing(inner, 'inner', -0.25),
    ...placeRing(outer, 'outer', -0.25 + (outer.length ? 0.5 / outer.length : 0)),
  ];
}

/**
 * The outline joining the lit capabilities, in the order it must be drawn.
 *
 * ANGULAR order, not layout order. Layout order walks the inner ring and then
 * the outer one, so the path jumps between circles and knots itself — measured
 * in a browser, and it read as a scribble rather than as a figure. Sorting by
 * angle around an interior point is the one ordering guaranteed to produce a
 * simple (non self-intersecting) closed polygon.
 *
 * Args:
 *   positions: Every drawable capability, placed.
 *   isLit: Whether that capability is active — only lit ones are joined.
 *
 * Returns:
 *   The lit positions in angular order, or an empty list when fewer than two
 *   are lit: a single star is not a constellation, and drawing a degenerate
 *   figure would claim a shape that is not there.
 */
export function figureOutline(
  positions: readonly NodePosition[],
  isLit: (position: NodePosition) => boolean
): NodePosition[] {
  const lit = positions.filter(isLit);
  if (lit.length < 2) return [];
  return [...lit].sort(
    (a, b) => Math.atan2(a.y - 50, a.x - 50) - Math.atan2(b.y - 50, b.x - 50)
  );
}

export interface BackdropStar {
  x: number;
  y: number;
  /** Radius in viewBox units. */
  r: number;
  /** Opacity, so the field has depth rather than one flat dusting. */
  o: number;
}

/** How much dust the sky carries. Enough for depth, few enough to stay quiet. */
const BACKDROP_COUNT = 90;
/** Nothing is drawn closer than this to the centre — see `backdropStars`. */
const BACKDROP_KEEPOUT = 14;

/**
 * The dust behind the capabilities — deterministic, like everything else here.
 *
 * A seeded generator rather than `Math.random`: the sky must be identical on
 * every visit and every render (React re-renders would otherwise reshuffle it
 * mid-animation), and it must be assertable. The keep-out radius around the
 * centre matters for meaning, not for looks: on this map every dot is a claim
 * about a capability, so decorative dust must never sit where a capability
 * could.
 *
 * Returns:
 *   The fixed field, from the outermost ring outwards.
 */
export function backdropStars(): BackdropStar[] {
  // Park–Miller LCG, seeded once: same sequence, always.
  let seed = 20260804;
  const next = (): number => {
    seed = (seed * 16807) % 2147483647;
    return seed / 2147483647;
  };

  const field: BackdropStar[] = [];
  while (field.length < BACKDROP_COUNT) {
    const x = Math.round(next() * 1000) / 10;
    const y = Math.round(next() * 1000) / 10;
    const brightness = next();
    if (Math.hypot(x - 50, y - 50) <= BACKDROP_KEEPOUT) continue;
    field.push({
      x,
      y,
      r: Math.round((0.15 + brightness * 0.35) * 100) / 100,
      o: Math.round((0.12 + brightness * 0.45) * 100) / 100,
    });
  }
  return field;
}
