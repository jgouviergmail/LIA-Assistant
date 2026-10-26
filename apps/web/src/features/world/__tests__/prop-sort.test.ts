import { expect, it } from 'vitest';
import { WORLD } from '../definition';
import { sortProps } from '../prop-sort';
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
