import { expect, it } from 'vitest';
import { barbellModel } from '../art/barbell';
import { WORLD } from '../definition';
import { compilePoseSlots } from '../pose-slots';
import { WORKOUT_BODY_Y } from '../decor-presentation';
it('keeps the active bar above the chest, with thin octagonal plates outside both hands and clear of the face', () => {
  const parts = barbellModel(2, { press: 0, barReach: 1 });
  const bar = parts.find(part => part.kind === 'box' && part.width >= 2);
  if (!bar || bar.kind !== 'box') throw new Error('Missing shaft');
  const slot = compilePoseSlots(WORLD).find(item => item.id === 'workout-1:0');
  const prop = WORLD.props.find(item => item.key === 'workout-1');
  if (!slot || !prop) throw new Error('Missing workout pose');
  expect(slot.facing).toBe(3);
  expect(slot.position.y).toBeCloseTo(prop.y + prop.depth - WORKOUT_BODY_Y);
  const headFront = WORKOUT_BODY_Y + 1 - 1.28;
  expect(bar.y).toBeGreaterThan(headFront + 0.2);
  const plates = parts.filter(part => part.kind === 'face' && part.points.length === 8);
  expect(plates.length).toBeGreaterThanOrEqual(4);
  for (const part of plates) {
    if (part.kind !== 'face') continue;
    const xs = part.points.map(point => point.x);
    expect(Math.max(...xs) - Math.min(...xs)).toBeLessThan(0.001);
    expect(xs[0] < 0.35 || xs[0] > 1.65).toBe(true);
  }
  const raised = barbellModel(2, { press: 1, barReach: 1 }).find(
    part => part.kind === 'box' && part.width >= 2
  );
  expect(raised && raised.kind === 'box' ? raised.z : 0).toBeGreaterThan(bar.z + 0.4);
});
