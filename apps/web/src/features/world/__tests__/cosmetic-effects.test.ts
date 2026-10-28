import { expect, it } from 'vitest';
import { CosmeticEffects } from '../cosmetic-effects';

const target = (id: string) => ({
  id,
  action: 'plant' as const,
  point: { x: 3, y: 4 },
  elevation: 0.1,
});
it('bounds simultaneous effects, per-target cooldowns and their absolute duration', () => {
  const effects = new CosmeticEffects();
  for (let i = 0; i < 8; i++)
    expect(effects.activate(target(String(i)), 100, true, 'balanced')).toBe(true);
  expect(effects.activate(target('ninth'), 100, true, 'balanced')).toBe(false);
  expect(effects.activate(target('0'), 2099, true, 'balanced')).toBe(false);
  expect(effects.frames(3100, 'balanced')).toEqual([]);
  expect(effects.activate(target('0'), 3100, true, 'balanced')).toBe(true);
  expect(effects.frames(3100, 'low')).toHaveLength(1);
  expect(effects.activate(target('a'), 3100, true, 'low')).toBe(true);
  expect(effects.activate(target('b'), 3100, true, 'low')).toBe(true);
  expect(effects.activate(target('c'), 3100, true, 'low')).toBe(false);
});
it('rejects offscreen or malformed events and does not accumulate motion debt', () => {
  const effects = new CosmeticEffects();
  expect(effects.activate(target('far'), 0, false, 'balanced')).toBe(false);
  expect(effects.activate(target('bad'), NaN, true, 'balanced')).toBe(false);
  expect(
    effects.activate({ ...target('bad'), point: { x: Infinity, y: 0 } }, 0, true, 'balanced')
  ).toBe(false);
  effects.activate(target('one'), 0, true, 'balanced');
  const at = effects.frames(400, 'balanced');
  for (let i = 0; i < 400; i++) effects.frames(i, 'balanced');
  expect(effects.frames(400, 'balanced')).toEqual(at);
  effects.clear();
  expect(effects.frames(400, 'balanced')).toEqual([]);
  expect(effects.frames(NaN, 'low')).toEqual([]);
});
it('keeps the accepted contact position immutable when the caller reuses its target', () => {
  const effects = new CosmeticEffects();
  const at = target('plant');
  effects.activate(at, 0, true, 'balanced');
  at.point.x = 500;
  expect(effects.frames(100, 'balanced')[0].point.x).toBe(3);
});
it('drops excess beats immediately when entering low quality and does not replay them afterwards', () => {
  const effects = new CosmeticEffects();
  for (let i = 0; i < 8; i++) effects.activate(target(String(i)), 0, true, 'high');
  expect(effects.frames(100, 'low')).toHaveLength(3);
  expect(effects.frames(200, 'balanced')).toHaveLength(3);
});
it('cancels only the interrupted target and evicts old cooldowns without retaining an unbounded history', () => {
  const effects = new CosmeticEffects();
  for (let i = 0; i < 130; i++)
    expect(effects.activate(target(String(i)), i * 2100, true, 'low')).toBe(true);
  expect(effects.remembered).toBe(128);
  const end = 129 * 2100;
  expect(effects.activate(target('kept'), end, true, 'low')).toBe(true);
  expect(effects.remembered).toBe(128);
  effects.cancel('129');
  expect(effects.remembered).toBe(127);
  expect(effects.frames(end + 1, 'low').map(frame => frame.id)).toEqual(['kept']);
  expect(effects.activate(target('fresh'), end + 1, true, 'low')).toBe(true);
  effects.cancel('missing');
  expect(effects.frames(end + 2, 'low').map(frame => frame.id)).toEqual(['kept', 'fresh']);
  // Only the interrupted object replays at once; an uninterrupted one keeps its cooldown.
  expect(effects.activate(target('129'), end + 3, true, 'low')).toBe(true);
  effects.cancel('kept');
  expect(effects.activate(target('fresh'), end + 4, true, 'low')).toBe(false);
});
it('replays an interrupted workout at once instead of refusing the re-chosen bench', () => {
  const effects = new CosmeticEffects();
  const bench = { ...target('bench'), action: 'workout' as const };
  expect(effects.activate(bench, 0, true, 'balanced')).toBe(true);
  expect(effects.activate(bench, 100, true, 'balanced')).toBe(false);
  effects.cancel('bench');
  expect(effects.frames(150, 'balanced')).toEqual([]);
  expect(effects.activate(bench, 200, true, 'balanced')).toBe(true);
  expect(effects.frames(300, 'balanced').map(frame => frame.id)).toEqual(['bench']);
});
