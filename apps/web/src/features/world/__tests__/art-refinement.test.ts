import { afterEach, expect, it, vi } from 'vitest';
import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { Model, orientModel, paintModel } from '../art/model';
import { Painter } from '../art/painter';
import { paintPathVerge } from '../art/terrain-edge';
import { paintPerson } from '../art/person';
import { ActorMesh } from '../art/actor-mesh';
import { shadeSprite, nightColour, nightStrength } from '../art/lighting';
import { paintGroundShade } from '../art/atmosphere';
import { WORLD } from '../definition';
import { NEUTRAL_ATMOSPHERE } from '../atmosphere';
import { createCamera, project } from '../geometry';
import { compilePoseSlots } from '../pose-slots';
import { orderedModelParts } from '../art/model-order';

afterEach(() => vi.restoreAllMocks());

it.each([0, 1, 2, 3] as const)('occludes the far cabinet decoration in facing %i', facing => {
  const model = new Model();
  model.box(0, 0, 0, 2, 0.4, 2, '#456754');
  model.panel(0.2, 0.405, 0.5, 1.5, 1, '#f0dfab');
  const oriented = orientModel(model.parts, 2, 0.4, facing);
  const sorted = orderedModelParts(oriented);
  expect(sorted.map(part => part.kind)).toEqual(facing < 2 ? ['box', 'face'] : ['face', 'box']);
  expect(oriented.map(part => part.kind)).toEqual(['box', 'face']);
});

it('keeps coplanar authored detail order and paints every interlocking part once', () => {
  const m = new Model();
  m.surface(0, 0, 1, 2, 2, '#ababab');
  m.surface(0.4, 0.4, 1, 1, 1, '#dddddd');
  expect(orderedModelParts(m.parts)).toEqual(m.parts);
  m.box(0, 0, 0, 2, 0.3, 2, '#567654');
  m.box(0, 0, 0, 0.3, 2, 2, '#456754');
  expect(new Set(orderedModelParts(m.parts))).toEqual(new Set(m.parts));
});

it.each([0, 1, 2, 3] as const)(
  'keeps rounded parts inside the original projected box in facing %i',
  facing => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(canvasContext({}));
    const m = new Model();
    m.softBox(0, 0, 0, 3, 0.6, 0.12, '#678975', 0.08);
    const parts = orientModel(m.parts, 3, 0.6, facing);
    const swap = facing === 0 || facing === 2;
    const w = swap ? 0.6 : 3,
      d = swap ? 3 : 0.6;
    const p = new Painter(w, d, 0.12);
    const polygons = vi.spyOn(p, 'polygon');
    paintModel(p, parts);
    const vertices = polygons.mock.calls.flatMap(([points]) => points);
    expect(vertices.length).toBeGreaterThan(12);
    for (const point of vertices) {
      expect(Number.isFinite(point.x + point.y)).toBe(true);
      expect(point.x).toBeGreaterThanOrEqual(-d * 32 - 1e-6);
      expect(point.x).toBeLessThanOrEqual(w * 32 + 1e-6);
      expect(point.y).toBeGreaterThanOrEqual(-0.12 * 32 - 1e-6);
      expect(point.y).toBeLessThanOrEqual((w + d) * 16 + 1e-6);
    }
    const top = project({ x: w / 2, y: d / 2 }, 0.12);
    const upper = polygons.mock.calls.at(-1)![0];
    expect(upper.reduce((sum, v) => sum + v.y, 0) / upper.length).toBeCloseTo(top.y);
  }
);

it('adds verges only beside grass, never between path tiles or beyond the plateau', () => {
  const c = canvasContext({});
  const world = {
    ...WORLD,
    width: 3,
    height: 3,
    grounds: [{ x: 0, y: 0, width: 2, height: 3, kind: 'path' as const }],
  };
  paintPathVerge(c, world, 0, 0, { x: 0, y: 0 });
  expect(c.stroke).not.toHaveBeenCalled();
  paintPathVerge(c, world, 1, 1, { x: 0, y: 0 });
  expect(c.stroke).toHaveBeenCalledTimes(1);
  expect(c.fillRect).toHaveBeenCalledTimes(3);
});

it.each(['dawn', 'evening', 'night'] as const)(
  'uses the same %s pigment on sprites and ground',
  phase => {
    const c = canvasContext({});
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(c);
    const sprite = new Painter(1, 1, 1).sprite();
    shadeSprite(sprite, nightStrength(phase), phase);
    const colour = String(c.fillStyle).split(',').slice(0, 3).join(',');
    paintGroundShade(c, WORLD, createCamera({ width: 800, height: 600 }, WORLD.spawn), {
      ...NEUTRAL_ATMOSPHERE,
      phase,
    });
    expect(String(c.fillStyle).startsWith(colour)).toBe(true);
    if (phase !== 'night') expect(nightColour(0.2, phase)).not.toBe(nightColour(0.2, 'night'));
  }
);

it('never carries a walking lift into a seated pose', () => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(canvasContext({}));
  const box = vi.spyOn(ActorMesh.prototype, 'box');
  const seat = compilePoseSlots(WORLD).find(slot => slot.kind === 'sit')!;
  paintPerson(0, 0, 1, 'sage', 0, seat);
  const resting = box.mock.calls.map(call => [...call]);
  box.mockClear();
  paintPerson(0, 3, 1, 'sage', 0, seat);
  expect(box.mock.calls).toEqual(resting);
});
