import { expect, it } from 'vitest';
import { WORLD } from '../definition';
import { compileNavigation, isWalkable } from '../navigation';
import { catAt, lifeBudget } from '../world-life';
import { readWorldEnvironment, atmosphereAt } from '../atmosphere';
it('keeps the decorative black cat inside its room and out of solid furniture over many cycles', () => {
  const nav = compileNavigation(WORLD),
    room = WORLD.zones.find(z => z.id === 'divination')!;
  for (let time = 0; time < 300; time += 0.1) {
    const cat = catAt(WORLD, time)!;
    expect(cat.x).toBeGreaterThan(room.x);
    expect(cat.x + cat.width).toBeLessThan(room.x + room.width);
    expect(cat.y).toBeGreaterThan(room.y);
    expect(cat.y + cat.depth).toBeLessThan(room.y + room.height);
    expect(isWalkable(nav, { x: cat.x + cat.width / 2, y: cat.y + cat.depth / 2 })).toBe(true);
    expect(cat.blocking).toBe(false);
  }
});
it('only shows butterflies with fresh clear weather in daytime, bounds the budget and respects reduced motion', () => {
  const time = Date.parse('2026-10-25T12:00:00Z');
  const anchor = readWorldEnvironment(
    {
      server_time: time / 1000,
      timezone: 'UTC',
      weather: {
        temperature_c: 18,
        condition_code: 'Clear',
        wind_speed_kmh: 2,
        observed_at: new Date(time - 1000).toISOString(),
        expires_at: new Date(time + 1000).toISOString(),
      },
    },
    0
  )!;
  const sunny = atmosphereAt(anchor, 0);
  expect(lifeBudget(sunny, 'high', false)).toEqual({ birds: 3, butterflies: 4 });
  expect(lifeBudget(sunny, 'low', false)).toEqual({ birds: 1, butterflies: 1 });
  expect(lifeBudget(sunny, 'high', true)).toEqual({ birds: 0, butterflies: 0 });
  expect(lifeBudget({ ...sunny, phase: 'night' }, 'high', false)).toEqual({
    birds: 0,
    butterflies: 0,
  });
  expect(lifeBudget(atmosphereAt(anchor, 1001), 'high', false).butterflies).toBe(0);
  expect(lifeBudget({ ...sunny, sunny: false }, 'high', false).butterflies).toBe(0);
});
