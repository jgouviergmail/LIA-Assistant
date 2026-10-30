import { expect, it } from 'vitest';
import { WORLD } from '../definition';
import { sortProps } from '../prop-sort';
import type { WorldProp } from '../types';

it('keeps every foreground wall segment in front of the long bottle shelf', () => {
  const shelf = WORLD.props.find(p => p.kind === 'bottles')!;
  const walls = WORLD.props.filter(
    p =>
      p.kind === 'partition' &&
      p.x >= shelf.x + shelf.width &&
      p.x < shelf.x + shelf.width + 1 &&
      p.y >= shelf.y &&
      p.y < shelf.y + shelf.depth
  );
  expect(walls).toHaveLength(6);
  const sorted = sortProps(WORLD.props);
  for (const wall of walls) expect(sorted.indexOf(wall)).toBeGreaterThan(sorted.indexOf(shelf));
});

it.each(['x', 'y'] as const)('orders long furniture between walls on the %s axis', axis => {
  const furniture: WorldProp = {
    ...WORLD.props.find(p => p.kind === 'bottles')!,
    x: 1,
    y: 1,
    width: axis === 'x' ? 0.35 : 6,
    depth: axis === 'x' ? 6 : 0.35,
  };
  const walls = Array.from({ length: 6 }, (_, i) =>
    [0, 2].map(offset => ({
      ...WORLD.props.find(p => p.kind === 'partition')!,
      id: `wall:${offset}:${i}`,
      x: axis === 'x' ? offset : 1 + i,
      y: axis === 'y' ? offset : 1 + i,
    }))
  ).flat();
  const sorted = sortProps([furniture, ...walls].reverse());
  for (const wall of walls) {
    if (wall[axis] === 0) expect(sorted.indexOf(wall)).toBeLessThan(sorted.indexOf(furniture));
    else expect(sorted.indexOf(wall)).toBeGreaterThan(sorted.indexOf(furniture));
  }
});
it('paints mounted decorations after their support without changing identities or collisions', () => {
  const sorted = sortProps(WORLD.props);
  expect(new Set(sorted.map(p => p.id)).size).toBe(WORLD.props.length);
  const clock = WORLD.props.find(p => p.kind === 'alarm')!;
  expect(clock.support).toBeDefined();
  expect(sorted.indexOf(clock)).toBeGreaterThan(sorted.findIndex(p => p.id === clock.support));
  expect(sorted.find(p => p.id === clock.id)).toBe(clock);
});
it('does not loop on invalid support cycles or discard an orphaned decoration', () => {
  const first = WORLD.props[0],
    second = WORLD.props[1];
  const props = [
    { ...first, support: second.id },
    { ...second, support: first.id },
    { ...WORLD.props[2], support: 'missing' },
  ];
  expect(sortProps(props)).toHaveLength(3);
});
