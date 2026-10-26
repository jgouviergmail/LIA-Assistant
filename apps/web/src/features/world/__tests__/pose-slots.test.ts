import { describe, expect, it } from 'vitest';
import { WORLD } from '../definition';
import { compileNavigation, findRoute } from '../navigation';
import { compilePoseSlots } from '../pose-slots';

describe('authored furniture slots', () => {
  it('provides stable distinct anchors and a reachable approach for every seat and bed', () => {
    const slots = compilePoseSlots(WORLD);
    expect(slots.length).toBeGreaterThan(10);
    expect(new Set(slots.map(slot => slot.id)).size).toBe(slots.length);
    const nav = compileNavigation(WORLD);
    for (const slot of slots) {
      expect(findRoute(nav, WORLD.spawn, slot.approach).length, slot.id).toBeGreaterThan(0);
      const prop = WORLD.props.find(p => p.id === slot.prop)!;
      expect(slot.position.x).toBeGreaterThanOrEqual(prop.x);
      expect(slot.position.x).toBeLessThan(prop.x + prop.width);
      expect(slot.position.y).toBeGreaterThanOrEqual(prop.y);
      expect(slot.position.y).toBeLessThan(prop.y + prop.depth);
    }
  });
  it('retains slot identity when an authored piece is repositioned', () => {
    const before = compilePoseSlots(WORLD);
    const moved = { ...WORLD, props: WORLD.props.map(p => ({ ...p, x: p.x + 1 })) };
    expect(compilePoseSlots(moved).map(s => s.id)).toEqual(before.map(s => s.id));
  });
});
