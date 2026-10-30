import { expect, it } from 'vitest';
import { barbellModel } from '../art/barbell';
import { WORLD } from '../definition';
import { compilePoseSlots } from '../pose-slots';
import { WORKOUT_BODY_Y } from '../decor-presentation';
it('keeps the active bar above the chest, with thin octagonal plates outside both hands and clear of the face', () => {
  const parts = barbellModel(2, { press: 0, barReach: 1 });
  const bar = parts.find(part => part.kind === 'box' && part.width > 1);
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
    part => part.kind === 'box' && part.width > 1
  );
  expect(raised && raised.kind === 'box' ? raised.z : 0).toBeGreaterThan(bar.z + 0.4);
});

it('joins coaxial shaft sections at every plate face instead of painting one shaft behind all discs', () => {
  const parts = barbellModel(2, {});
  const shaft = parts.filter(part => part.kind === 'box');
  expect(shaft[0].x).toBe(0);
  expect(shaft.at(-1)!.x + shaft.at(-1)!.width).toBe(2);
  for (let i = 1; i < shaft.length; i++)
    expect(shaft[i].x).toBeCloseTo(shaft[i - 1].x + shaft[i - 1].width);
  for (const face of parts) {
    if (face.kind !== 'face' || face.points.length !== 8) continue;
    const x = face.points[0].x;
    expect(shaft.some(part => part.x < x - 1e-7 && part.x + part.width > x + 1e-7)).toBe(false);
    const center = face.points.reduce(
      (sum, point) => ({ y: sum.y + point.y / 8, z: sum.z + point.z / 8 }),
      { y: 0, z: 0 }
    );
    expect(center.y).toBeCloseTo(shaft[0].y + shaft[0].depth / 2);
    expect(center.z).toBeCloseTo(shaft[0].z + shaft[0].height / 2);
  }
});
