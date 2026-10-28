import { expect, it } from 'vitest';
import { WorldPropIndex } from '../prop-index';
import { actorOccluders } from '../occlusion';
import { WORLD } from '../definition';
import { project } from '../geometry';
import { sortProps } from '../prop-sort';
import type { Rect, WorldProp } from '../types';
it('includes an interactive low pond surface but excludes a passive flat floor decoration', () => {
  const pond = WORLD.props.find(prop => prop.kind === 'pond');
  if (!pond) throw new Error('Missing authored pond');
  const passive = { ...pond, id: 'flat-rug', kind: 'rug' as const };
  const index = new WorldPropIndex([pond, passive]);
  expect(index.query({ x: -10000, y: -10000, width: 20000, height: 20000 })).toEqual([pond]);
});

it('keeps every full-scan occluder, in the same draw order, across the campus', () => {
  const props = sortProps(WORLD.props),
    index = new WorldPropIndex(props);
  let candidates = 0,
    queries = 0;
  for (let y = -2; y < WORLD.height + 2; y += 1.75)
    for (let x = -2; x < WORLD.width + 2; x += 1.75) {
      const actor = { x, y },
        at = project(actor);
      const area = { x: at.x - 80, y: at.y - 112, width: 160, height: 160 };
      const near = index.query(area);
      expect(actorOccluders(near, actor, area)).toEqual(actorOccluders(props, actor, area));
      expect(new Set(near).size).toBe(near.length);
      candidates += near.length;
      queries++;
    }
  expect(candidates / queries).toBeLessThan(props.length / 10);
});
it('preserves pickable pixels at fractional and negative sprite bounds, including cell edges', () => {
  const source = WORLD.props.find(p => p.kind === 'chair');
  if (!source) throw Error('No chair');
  const props: WorldProp[] = [
    { ...source, id: 'first', x: -3.25, y: 1.125, width: 1.15, depth: 0.8, height: 1.2 },
    { ...source, id: 'second', x: 0, y: 0 },
    { ...source, id: 'third', x: 4, y: 4 },
  ];
  const index = new WorldPropIndex(props);
  for (const prop of props) {
    const at = project(prop),
      h = Math.max(prop.height, 2.5);
    const left = at.x - prop.depth * 32 - 20,
      top = at.y - h * 32 - 20;
    const width = Math.ceil((prop.width + prop.depth) * 32 + 40);
    const height = Math.ceil((prop.width + prop.depth) * 16 + h * 32 + 48);
    for (const p of [
      { x: left + 0.01, y: top + 0.01 },
      { x: left + width - 0.01, y: top + height - 0.01 },
      { x: at.x, y: at.y },
      { x: 128, y: 128 },
      { x: 0, y: 0 },
    ]) {
      const expected = props.filter(value => {
        const foot = project(value),
          z = Math.max(value.height, 2.5);
        const x = foot.x - value.depth * 32 - 20,
          y = foot.y - z * 32 - 20;
        return (
          x < p.x + 1 &&
          x + Math.ceil((value.width + value.depth) * 32 + 40) > p.x &&
          y < p.y + 1 &&
          y + Math.ceil((value.width + value.depth) * 16 + z * 32 + 48) > p.y
        );
      });
      expect(index.query({ ...p, width: 1, height: 1 })).toEqual(expected);
    }
  }
});
it('bounds malformed/large queries and releases all retained scene references', () => {
  const props = sortProps(WORLD.props).filter(p => p.height >= 0.1),
    index = new WorldPropIndex(props);
  for (const area of [
    { x: Number.NaN, y: 0, width: 1, height: 1 },
    { x: 0, y: 0, width: Number.POSITIVE_INFINITY, height: 1 },
    { x: 0, y: 0, width: 0, height: 1 },
    { x: 0, y: 0, width: 1, height: -1 },
    { x: 1e308, y: 0, width: 1, height: 1 },
  ] satisfies Rect[])
    expect(index.query(area)).toEqual([]);
  expect(index.query({ x: -1e9, y: -1e9, width: 2e9, height: 2e9 })).toEqual(props);
  index.clear();
  expect(index.query({ x: -1e9, y: -1e9, width: 2e9, height: 2e9 })).toEqual([]);
});

it('rejects unindexable authored geometry before allocating buckets', () => {
  const prop = WORLD.props.find(p => p.kind === 'tree');
  if (!prop) throw Error('No tree');
  expect(() => new WorldPropIndex([{ ...prop, x: Number.NaN }])).toThrow(
    'world_prop_bounds_invalid'
  );
  expect(() => new WorldPropIndex([{ ...prop, x: 1e24 }])).toThrow('world_prop_bounds_limit');
  expect(() => new WorldPropIndex([{ ...prop, width: 1e12 }])).toThrow('world_prop_bounds_limit');
});
