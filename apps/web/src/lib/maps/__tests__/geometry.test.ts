/**
 * The two geometries of the maps: the constellation (laid out in advance) and
 * the technical connectors (drawn between measured boxes).
 */

import { describe, expect, it } from 'vitest';

import {
  CONSTELLATION_CENTER,
  CONSTELLATION_RADIUS,
  arcPath,
  curvePath,
  flowBadges,
  flowPath,
  layoutConstellation,
} from '../constellation';
import { connectorPath, connectorSegments } from '../connectors';

const families = [{ id: 'a' }, { id: 'b' }];
const bricks = [
  { id: 'a1', family: 'a', deps: ['b1'] },
  { id: 'a2', family: 'a', deps: ['nowhere'] },
  { id: 'b1', family: 'b', deps: [] },
  { id: 'b2', family: 'b', deps: ['a1'] },
];

describe('layoutConstellation', () => {
  const layout = layoutConstellation(families, bricks);

  it('puts every brick on the circle, family after family, starting at the top', () => {
    expect(layout.nodes.size).toBe(4);
    for (const node of layout.nodes.values()) {
      const r = Math.hypot(node.x - CONSTELLATION_CENTER, node.y - CONSTELLATION_CENTER);
      expect(Math.abs(r - CONSTELLATION_RADIUS)).toBeLessThan(0.2);
    }
    const angles = bricks.map(b => layout.nodes.get(b.id)?.angle ?? 0);
    expect([...angles].sort((x, y) => x - y)).toEqual(angles);
    expect(angles[0]).toBeGreaterThan(-90);
  });

  it('turns the labels of the left half so they never read upside down', () => {
    for (const node of layout.nodes.values()) {
      const left = node.angle > 90 && node.angle < 270;
      expect(node.labelLeft).toBe(left);
      expect(Math.abs(node.labelRotation)).toBeLessThanOrEqual(90.1);
    }
  });

  it('draws one arc per family and an edge per known dependency only', () => {
    expect(layout.arcs.map(a => a.family)).toEqual(['a', 'b']);
    expect(layout.edges.map(e => `${e.from}>${e.to}`)).toEqual(['a1>b1', 'b2>a1']);
    expect(layout.edges[0].d).toMatch(/^M[\d.]+ [\d.]+ Q[\d.]+ [\d.]+ [\d.]+ [\d.]+$/);
  });

  it('draws a journey as one path, skipping a step that stays on the same brick', () => {
    const path = flowPath(['a1', 'a1', 'b1', 'b2'], layout.nodes);
    expect(path.match(/Q/g)).toHaveLength(2);
    expect(path.startsWith('M')).toBe(true);
    expect(flowPath(['a1'], layout.nodes)).toBe('');
    expect(flowPath(['a1', 'ghost'], layout.nodes)).toBe('');
  });

  it('gathers the step numbers of a brick visited twice', () => {
    const badges = flowBadges(['a1', 'b1', 'a1', 'ghost'], layout.nodes);
    expect(badges.map(b => [b.id, b.label])).toEqual([
      ['a1', '1·3'],
      ['b1', '2'],
    ]);
  });

  it('spells arcs and curves as SVG paths', () => {
    expect(arcPath(100, -90, 200)).toContain(' 0 1 1 ');
    expect(arcPath(100, 0, 90)).toContain(' 0 0 1 ');
    expect(curvePath({ x: 0, y: 0 }, { x: 10, y: 10 })).toMatch(/^M0 0 Q/);
  });
});

describe('connectors', () => {
  it('arcs over a row between two bricks side by side', () => {
    const d = connectorPath({ x: 0, y: 10, w: 50, h: 20 }, { x: 100, y: 10, w: 50, h: 20 });
    expect(d).toBe('M50 20 C80 -8 70 -8 100 20');
    const back = connectorPath({ x: 100, y: 10, w: 50, h: 20 }, { x: 0, y: 10, w: 50, h: 20 });
    expect(back.startsWith('M100 20')).toBe(true);
  });

  it('bends from the facing edges of two rows', () => {
    expect(connectorPath({ x: 0, y: 0, w: 40, h: 20 }, { x: 0, y: 100, w: 40, h: 20 })).toBe(
      'M20 20 C20 60 20 60 20 100'
    );
    expect(connectorPath({ x: 0, y: 100, w: 40, h: 20 }, { x: 0, y: 0, w: 40, h: 20 })).toBe(
      'M20 100 C20 60 20 60 20 20'
    );
  });

  it('draws a focused brick both ways, or a journey up to its current step', () => {
    expect(connectorSegments(new Set(['a>b']), new Set(['c>a']), null)).toEqual([
      { from: 'a', to: 'b', kind: 'out' },
      { from: 'c', to: 'a', kind: 'in' },
    ]);
    const flow = { steps: ['a', 'b', 'b', 'c'], step: 2 };
    expect(connectorSegments(new Set(['x>y']), new Set(), flow)).toEqual([
      { from: 'a', to: 'b', kind: 'flow' },
    ]);
    expect(connectorSegments(new Set(), new Set(), { ...flow, step: 9 })).toHaveLength(2);
  });
});
