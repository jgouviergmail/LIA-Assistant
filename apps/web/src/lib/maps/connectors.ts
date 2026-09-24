/**
 * Connectors of the technical map, drawn between two MEASURED boxes.
 *
 * The layers reflow with the viewport, so their links cannot be laid out in
 * advance: the page measures the two bricks and asks for the curve. Two bricks
 * side by side get an arc that lifts over the row; two bricks on different rows
 * get an S-curve from the edge of one to the facing edge of the other.
 */

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** How high an arc between two bricks of one row lifts above them. */
const ROW_LIFT = 28;
/** How far an arc's handles reach out from the bricks, horizontally. */
const ROW_REACH = 30;

const round = (n: number): number => Math.round(n * 10) / 10;

/** The curve from box `p` to box `q`. */
export function connectorPath(p: Box, q: Box): string {
  const pc = { x: p.x + p.w / 2, y: p.y + p.h / 2 };
  const qc = { x: q.x + q.w / 2, y: q.y + q.h / 2 };
  if (Math.abs(pc.y - qc.y) < p.h) {
    const dir = qc.x > pc.x ? 1 : -1;
    const x1 = dir > 0 ? p.x + p.w : p.x;
    const x2 = dir > 0 ? q.x : q.x + q.w;
    return (
      `M${round(x1)} ${round(pc.y)} C${round(x1 + dir * ROW_REACH)} ${round(pc.y - ROW_LIFT)} ` +
      `${round(x2 - dir * ROW_REACH)} ${round(qc.y - ROW_LIFT)} ${round(x2)} ${round(qc.y)}`
    );
  }
  const down = qc.y > pc.y;
  const y1 = down ? p.y + p.h : p.y;
  const y2 = down ? q.y : q.y + q.h;
  const mid = (y1 + y2) / 2;
  return (
    `M${round(pc.x)} ${round(y1)} C${round(pc.x)} ${round(mid)} ` +
    `${round(qc.x)} ${round(mid)} ${round(qc.x)} ${round(y2)}`
  );
}

/** What a connector links, and how it is drawn. */
export interface Segment {
  from: string;
  to: string;
  kind: 'out' | 'in' | 'flow';
}

/**
 * The connectors to draw: the focused brick's dependencies and users, or a
 * journey's path up to its current step.
 */
export function connectorSegments(
  out: ReadonlySet<string>,
  incoming: ReadonlySet<string>,
  flow: { steps: readonly string[]; step: number } | null
): Segment[] {
  const split = (key: string, kind: Segment['kind']): Segment => {
    const [from, to] = key.split('>');
    return { from, to, kind };
  };
  if (flow) {
    const segments: Segment[] = [];
    for (let k = 1; k <= Math.min(flow.step, flow.steps.length - 1); k += 1) {
      if (flow.steps[k] !== flow.steps[k - 1]) {
        segments.push({ from: flow.steps[k - 1], to: flow.steps[k], kind: 'flow' });
      }
    }
    return segments;
  }
  return [...[...out].map(k => split(k, 'out')), ...[...incoming].map(k => split(k, 'in'))];
}
