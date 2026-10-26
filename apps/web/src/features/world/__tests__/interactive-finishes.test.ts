import { expect, it } from 'vitest';
import { WORLD } from '../definition';
it('keeps the weather telescope reachable in the mystic north-west corner, clear of the oracle seats', () => {
  const zone = WORLD.zones.find(z => z.id === 'divination');
  const scope = WORLD.props.filter(p => p.kind === 'telescope');
  expect(scope).toHaveLength(1);
  if (!zone) throw new Error('Missing divination room');
  const telescope = scope[0];
  expect(telescope.activity).toBe('weather');
  expect(telescope.x).toBeGreaterThan(zone.x);
  expect(telescope.x + telescope.width).toBeLessThan(zone.x + zone.width / 2 + 0.1);
  expect(telescope.y).toBeGreaterThan(zone.y);
  expect(telescope.y + telescope.depth).toBeLessThan(zone.y + 4);
});
