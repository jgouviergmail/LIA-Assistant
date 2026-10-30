import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { expect, it, vi } from 'vitest';
import { NEUTRAL_ATMOSPHERE } from '../atmosphere';
import { paintRoomMotion } from '../art/room-motion';
import { WORLD } from '../definition';
import type { WorldProp } from '../types';

function context() {
  return canvasContext({
    save: vi.fn(),
    restore: vi.fn(),
    translate: vi.fn(),
    transform: vi.fn(),
    fillRect: vi.fn(),
    fillText: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
  });
}
function prop(kind: WorldProp['kind']): WorldProp {
  const found = WORLD.props.find(item => item.kind === kind);
  if (!found) throw new Error('Missing authored ' + kind);
  return found;
}
it('keeps the bedside clock on the owner civil time, updates each minute and does not freeze with reduced motion', () => {
  const c = context(),
    painter = c;
  const alarm = prop('alarm');
  paintRoomMotion(painter, alarm, 0, true);
  expect(c.fillText).toHaveBeenLastCalledWith('--:--', 0, 0);
  const time = Date.parse('2026-11-03T08:23:00Z');
  const sky = { ...NEUTRAL_ATMOSPHERE, time, timezone: 'Asia/Shanghai' };
  paintRoomMotion(painter, alarm, 0, true, sky);
  expect(c.fillText).toHaveBeenLastCalledWith('16:23', 0, 0);
  paintRoomMotion(painter, alarm, 1, true, { ...sky, time: time + 45000 });
  expect(c.fillText).toHaveBeenLastCalledWith('16:23', 0, 0);
  paintRoomMotion(painter, alarm, 2, true, { ...sky, time: time + 60000 });
  expect(c.fillText).toHaveBeenLastCalledWith('16:24', 0, 0);
  paintRoomMotion(painter, alarm, 3, true, { ...sky, timezone: 'Europe/Paris' });
  expect(c.fillText).toHaveBeenLastCalledWith('09:23', 0, 0);
  expect(c.save).toHaveBeenCalledTimes(c.restore.mock.calls.length);
});

it('suppresses decorative animation entirely when reduced motion is requested', () => {
  const c = context();
  for (const kind of ['display', 'arcade', 'machine', 'jukebox', 'chair'] as const)
    paintRoomMotion(c, prop(kind), 1, true);
  expect(c.save).not.toHaveBeenCalled();
  paintRoomMotion(c, prop('chair'), 1, false);
  expect(c.save).not.toHaveBeenCalled();
});

it('animates authored screens, game cabinets and jukebox at finite coordinates and respects facing', () => {
  for (const kind of ['arcade', 'display', 'machine', 'jukebox'] as const) {
    const c = context(),
      p = c;
    paintRoomMotion(p, { ...prop(kind), facing: 0 }, 1, false);
    paintRoomMotion(p, { ...prop(kind), facing: 1 }, 2, false);
    const coordinates =
      kind === 'arcade' ? c.fillRect.mock.calls : [...c.moveTo.mock.calls, ...c.arc.mock.calls];
    expect(coordinates).toHaveLength(2);
    expect(coordinates.flat().every(Number.isFinite)).toBe(true);
    expect(coordinates[0].slice(0, 2)).not.toEqual(coordinates[1].slice(0, 2));
    expect(c.save).toHaveBeenCalledTimes(2);
    expect(c.restore).toHaveBeenCalledTimes(2);
  }
});

it('keeps front-panel animation off the rear housings and clips arcade pixels to their screen', () => {
  const c = context();
  for (const facing of [2, 3] as const)
    for (const kind of ['arcade', 'display', 'machine', 'jukebox', 'alarm'] as const)
      paintRoomMotion(c, { ...prop(kind), facing }, 3, false);
  expect(c.save).not.toHaveBeenCalled();
  paintRoomMotion(c, { ...prop('arcade'), facing: 1 }, 3, false);
  expect(c.clip).toHaveBeenCalledOnce();
  expect(c.restore).toHaveBeenCalledOnce();
});
