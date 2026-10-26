import { describe, expect, it } from 'vitest';
import { actorOccluders } from '../occlusion';
import { WORLD } from '../definition';
import { project } from '../geometry';

describe('isometric actor occlusion', () => {
  const fountain = WORLD.props.find(p => p.kind === 'fountain');
  if (!fountain) throw new Error('Missing representative wide prop');
  // Fixed isolated geometry keeps the occlusion oracle independent of the campus layout.
  const props = [{ ...fountain, x: 37, y: 24 }];
  function occluders(x: number, y: number) {
    const point = { x, y },
      p = project(point);
    return actorOccluders(props, point, { x: p.x - 80, y: p.y - 112, width: 160, height: 160 });
  }
  it('does not hide a character in front of either face of a wide prop', () => {
    expect(occluders(37.5, 27.5)).toEqual([]);
    expect(occluders(40.5, 24.5)).toEqual([]);
  });
  it('masks a character behind an overlapping prop, but ignores distant props', () => {
    expect(occluders(37.5, 23.5)).toEqual(props);
    expect(occluders(5, 5)).toEqual([]);
  });
  it('never masks a character with a ground-level mosaic', () => {
    const p = project(WORLD.spawn);
    const mosaic = { ...fountain, kind: 'mosaic' as const, height: 0.05 };
    expect(
      actorOccluders([mosaic], { x: 37.5, y: 23.5 }, { ...p, width: 1000, height: 1000 })
    ).toEqual([]);
  });
  it.each([
    { x: 550, y: 900, width: 20, height: 20 },
    { x: 100, y: 900, width: 10, height: 20 },
    { x: 350, y: 700, width: 20, height: 10 },
    { x: 350, y: 1150, width: 20, height: 10 },
  ])('does not allocate masks outside the actor layer bounds: %j', area => {
    expect(actorOccluders(props, { x: 37.5, y: 23.5 }, area)).toEqual([]);
  });
});
