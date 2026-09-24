/**
 * Geometry of the functional map's constellation — pure, so it is tested
 * without a DOM.
 *
 * The bricks sit on one circle, grouped by family: each family owns a
 * contiguous arc, separated from the next by a small gap, and an inner arc in
 * the family's tone names the group. A dependency is a quadratic curve pulled
 * toward the centre; a journey is the same curve pulled harder, so it reads
 * above the dependency web.
 */

/** Side of the square viewBox, in SVG units. */
export const CONSTELLATION_SIZE = 1200;
const CENTER = CONSTELLATION_SIZE / 2;
/** Radius of the circle the bricks sit on. */
export const CONSTELLATION_RADIUS = 300;
/** Angular gap between two families, in degrees. */
const FAMILY_GAP_DEG = 5;
/** How far a dependency curve is pulled toward the centre (0 = straight). */
const EDGE_PULL = 0.22;
/** How far a journey curve is pulled toward the centre. */
const FLOW_PULL = 0.42;
/** Distance inside the circle where a journey's step numbers sit. */
const BADGE_INSET = 52;
/** Distance inside the circle of a family's arc. */
const ARC_INSET = 24;

export interface Point {
  x: number;
  y: number;
}

export interface NodeLayout extends Point {
  id: string;
  /** Angle on the circle, in degrees (-90 = top). */
  angle: number;
  /** The label reads leftward on the left half, so it never stands upside down. */
  labelLeft: boolean;
  /** Rotation of the label, in degrees. */
  labelRotation: number;
}

export interface ArcLayout {
  family: string;
  d: string;
}

export interface EdgeLayout {
  from: string;
  to: string;
  d: string;
}

export interface BadgeLayout extends Point {
  id: string;
  /** The step numbers the brick carries in the journey, e.g. "2·5". */
  label: string;
}

export interface ConstellationLayout {
  nodes: Map<string, NodeLayout>;
  arcs: ArcLayout[];
  edges: EdgeLayout[];
}

const rad = (deg: number): number => (deg * Math.PI) / 180;
const round = (n: number): number => Math.round(n * 10) / 10;

function onCircle(radius: number, angle: number): Point {
  return { x: CENTER + radius * Math.cos(rad(angle)), y: CENTER + radius * Math.sin(rad(angle)) };
}

/** An arc of the circle of radius `r`, from `start` to `end` degrees, clockwise. */
export function arcPath(r: number, start: number, end: number): string {
  const p1 = onCircle(r, start);
  const p2 = onCircle(r, end);
  const large = end - start > 180 ? 1 : 0;
  return `M${round(p1.x)} ${round(p1.y)} A${r} ${r} 0 ${large} 1 ${round(p2.x)} ${round(p2.y)}`;
}

/** The control point pulling a curve between two nodes toward the centre. */
function control(p: Point, q: Point, pull: number): Point {
  return {
    x: round(CENTER + ((p.x + q.x) / 2 - CENTER) * pull),
    y: round(CENTER + ((p.y + q.y) / 2 - CENTER) * pull),
  };
}

/** One quadratic curve between two points. */
export function curvePath(p: Point, q: Point, pull: number = EDGE_PULL): string {
  const c = control(p, q, pull);
  return `M${round(p.x)} ${round(p.y)} Q${c.x} ${c.y} ${round(q.x)} ${round(q.y)}`;
}

/**
 * Place every brick on the circle, family after family, in the order given.
 *
 * @param families - The families, in display order.
 * @param bricks - The bricks, each naming its family and its dependencies.
 */
export function layoutConstellation(
  families: ReadonlyArray<{ id: string }>,
  bricks: ReadonlyArray<{ id: string; family: string; deps: string[] }>
): ConstellationLayout {
  const step = (360 - families.length * FAMILY_GAP_DEG) / Math.max(1, bricks.length);
  const nodes = new Map<string, NodeLayout>();
  const arcs: ArcLayout[] = [];
  let angle = -90 + FAMILY_GAP_DEG / 2;
  for (const family of families) {
    const start = angle;
    for (const brick of bricks.filter(b => b.family === family.id)) {
      const at = angle + step / 2;
      const point = onCircle(CONSTELLATION_RADIUS, at);
      const labelLeft = at > 90 && at < 270;
      nodes.set(brick.id, {
        id: brick.id,
        angle: at,
        x: round(point.x),
        y: round(point.y),
        labelLeft,
        labelRotation: round(labelLeft ? at - 180 : at),
      });
      angle += step;
    }
    arcs.push({
      family: family.id,
      d: arcPath(CONSTELLATION_RADIUS - ARC_INSET, start + 0.6, angle - 0.6),
    });
    angle += FAMILY_GAP_DEG;
  }
  const edges: EdgeLayout[] = [];
  for (const brick of bricks) {
    for (const dep of brick.deps) {
      const p = nodes.get(brick.id);
      const q = nodes.get(dep);
      if (p && q) edges.push({ from: brick.id, to: dep, d: curvePath(p, q) });
    }
  }
  return { nodes, arcs, edges };
}

/** The whole journey as one path: a curve per change of brick. */
export function flowPath(steps: readonly string[], nodes: Map<string, NodeLayout>): string {
  const parts: string[] = [];
  for (let i = 1; i < steps.length; i += 1) {
    if (steps[i] === steps[i - 1]) continue;
    const p = nodes.get(steps[i - 1]);
    const q = nodes.get(steps[i]);
    if (!p || !q) continue;
    const c = control(p, q, FLOW_PULL);
    const head = parts.length ? '' : `M${round(p.x)} ${round(p.y)} `;
    parts.push(`${head}Q${c.x} ${c.y} ${round(q.x)} ${round(q.y)}`);
  }
  return parts.join(' ');
}

/** Where each brick of a journey shows its step numbers, inside the circle. */
export function flowBadges(
  steps: readonly string[],
  nodes: Map<string, NodeLayout>
): BadgeLayout[] {
  const numbers = new Map<string, number[]>();
  steps.forEach((id, i) => numbers.set(id, [...(numbers.get(id) ?? []), i + 1]));
  const out: BadgeLayout[] = [];
  for (const [id, list] of numbers) {
    const node = nodes.get(id);
    if (!node) continue;
    const point = onCircle(CONSTELLATION_RADIUS - BADGE_INSET, node.angle);
    out.push({ id, x: round(point.x), y: round(point.y), label: list.join('·') });
  }
  return out;
}

/** Centre of the constellation, where its core label sits. */
export const CONSTELLATION_CENTER = CENTER;
