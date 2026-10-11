import { describe, expect, it } from 'vitest';
import {
  bodyMotionSpace,
  projectBodyMotion,
  type BodyBox,
  type BodyMotionPose,
  type BodyViewport,
} from '../body-motion-geometry';

const BOX: BodyBox = { left: 200, top: 150, width: 78, height: 90, fontSize: 30 };
const VIEWPORT: BodyViewport = { left: 24, top: 32, width: 900, height: 640 };
const REST: BodyMotionPose = { x: 0, y: 0, roll: 0, sx: 1, sy: 1 };

/** Independent corner projection includes the ornaments around the measured face. */
function paintedBounds(pose: BodyMotionPose, box = BOX, marginEm = 0.3) {
  const angle = (pose.roll * Math.PI) / 180;
  const centreX = box.left + box.width / 2 + pose.x * box.fontSize;
  const centreY = box.top + box.height / 2 + pose.y * box.fontSize;
  const margin = box.fontSize * marginEm;
  const points = [-1, 1].flatMap(horizontal =>
    [-1, 1].map(vertical => {
      const x = horizontal * (box.width / 2 + margin) * pose.sx;
      const y = vertical * (box.height / 2 + margin) * pose.sy;
      return {
        x: centreX + x * Math.cos(angle) - y * Math.sin(angle),
        y: centreY + x * Math.sin(angle) + y * Math.cos(angle),
      };
    })
  );
  return {
    left: Math.min(...points.map(point => point.x)),
    right: Math.max(...points.map(point => point.x)),
    top: Math.min(...points.map(point => point.y)),
    bottom: Math.max(...points.map(point => point.y)),
  };
}

function expectContained(pose: BodyMotionPose, viewport = VIEWPORT, box = BOX, marginEm = 0.3) {
  const bounds = paintedBounds(pose, box, marginEm);
  expect(bounds.left).toBeGreaterThanOrEqual(viewport.left - 0.000001);
  expect(bounds.right).toBeLessThanOrEqual(viewport.left + viewport.width + 0.000001);
  expect(bounds.top).toBeGreaterThanOrEqual(viewport.top - 0.000001);
  expect(bounds.bottom).toBeLessThanOrEqual(viewport.top + viewport.height + 0.000001);
}

describe('Temporary body motion geometry', () => {
  it('returns exactly to the original resting position without introducing an ornament offset', () => {
    const edgeBox = { ...BOX, left: VIEWPORT.left, top: VIEWPORT.top };
    expect(projectBodyMotion(REST, edgeBox, VIEWPORT)).toEqual(REST);
    expect(projectBodyMotion(REST, BOX, VIEWPORT)).toEqual(REST);
  });

  it('approaches the exact corner anchor continuously while still containing the true body', () => {
    const box = { ...BOX, left: VIEWPORT.left, top: VIEWPORT.top };
    for (const epsilon of [0.01, 0.001, 0.0001, 0.000001]) {
      for (const desired of [
        { ...REST, x: epsilon, y: -epsilon },
        { ...REST, roll: epsilon },
        { ...REST, sx: 1 + epsilon, sy: 1 - epsilon },
      ]) {
        const pose = projectBodyMotion(desired, box, VIEWPORT);
        expectContained(pose, VIEWPORT, box, 0);
        const departure = Math.max(Math.abs(pose.x), Math.abs(pose.y)) * box.fontSize;
        expect(departure).toBeLessThan(epsilon * (box.width + box.height) * 2);
      }
    }
  });

  it('has the same zero translation after whole revolutions as before the scene', () => {
    const box = { ...BOX, left: VIEWPORT.left, top: VIEWPORT.top };
    for (const roll of [-720, -360, 0, 360, 720]) {
      const pose = projectBodyMotion({ ...REST, roll }, box, VIEWPORT);
      expect(pose).toEqual({ ...REST, roll });
    }
  });

  it('contains every painted corner through rotations, squash and excessive travel', () => {
    for (const roll of [-360, -145, -90, -1, 0, 37, 90, 179, 360]) {
      for (const [sx, sy] of [
        [1.3, 0.55],
        [0.65, 1.3],
        [1, 1],
      ]) {
        for (const [x, y] of [
          [-100, -100],
          [100, 100],
          [-100, 100],
          [100, -100],
        ]) {
          const pose = projectBodyMotion({ x, y, roll, sx, sy }, BOX, VIEWPORT);
          expectContained(pose);
          expect(pose.roll).toBe(roll);
        }
      }
    }
  });

  it('reduces a rotated body uniformly when the visible viewport is smaller than the character', () => {
    const viewport = { left: 120, top: 80, width: 40, height: 30 };
    const desired = { x: 30, y: -30, roll: 43, sx: 1.3, sy: 0.7 };
    const pose = projectBodyMotion(desired, BOX, viewport);
    expectContained(pose, viewport);
    expect(pose.sx).toBeGreaterThan(0);
    expect(pose.sy).toBeGreaterThan(0);
    expect(pose.sx).toBeLessThan(desired.sx);
    expect(pose.sx / pose.sy).toBeCloseTo(desired.sx / desired.sy, 8);
  });

  it('reprojects against keyboard pan and resize without retaining an obsolete limit', () => {
    const desired = { x: 12, y: 8, roll: 75, sx: 1.15, sy: 0.9 };
    const wide = projectBodyMotion(desired, BOX, VIEWPORT);
    const keyboard = { left: 210, top: 220, width: 320, height: 160 };
    const small = projectBodyMotion(desired, BOX, keyboard);
    expectContained(wide);
    expectContained(small, keyboard);
    expect(small).not.toEqual(wide);
    expect(projectBodyMotion(desired, BOX, VIEWPORT)).toEqual(wide);
  });

  it('clamps the resting body only when its original rectangle no longer fits', () => {
    const viewport = { left: 350, top: 250, width: 200, height: 200 };
    const pose = projectBodyMotion(REST, BOX, viewport);
    expect(pose.x).toBeGreaterThan(0);
    expect(pose.y).toBeGreaterThan(0);
    expectContained(pose, viewport, BOX, 0);
  });

  it('provides roaming endpoints safe for every rotation at the maximum authored scale', () => {
    const space = bodyMotionSpace(BOX, VIEWPORT, true);
    expect(space.roaming).toBe(true);
    expect(space.minX).toBeLessThan(space.maxX);
    expect(space.minY).toBeLessThan(space.maxY);
    for (const x of [space.minX, space.maxX]) {
      for (const y of [space.minY, space.maxY]) {
        for (let roll = 0; roll < 360; roll += 15) {
          expectContained({ x, y, roll, sx: 1.3, sy: 1.3 });
        }
      }
    }
  });

  it('keeps non-roaming previews within a small local excursion', () => {
    const space = bodyMotionSpace(BOX, VIEWPORT, false);
    expect(space.roaming).toBe(false);
    expect(space.minX).toBeGreaterThanOrEqual(-0.7);
    expect(space.maxX).toBeLessThanOrEqual(0.7);
    expect(space.minY).toBeGreaterThanOrEqual(-0.7);
    expect(space.maxY).toBeLessThanOrEqual(0.7);
    expect(space.minX).toBeLessThanOrEqual(0);
    expect(space.maxX).toBeGreaterThanOrEqual(0);
  });

  it('cannot request a full-screen trip when the safe envelope cannot fit', () => {
    const space = bodyMotionSpace(BOX, { left: 0, top: 0, width: 20, height: 10 }, true);
    expect(space).toEqual({ minX: 0, maxX: 0, minY: 0, maxY: 0, roaming: false });
  });

  it('retains the zero terminal target at edge anchors while projecting their deformed paint safely', () => {
    for (const left of [VIEWPORT.left, VIEWPORT.left - 200]) {
      for (const top of [VIEWPORT.top, VIEWPORT.top - 200]) {
        const box = { ...BOX, left, top };
        const space = bodyMotionSpace(box, VIEWPORT, true);
        expect(space.minX).toBeLessThanOrEqual(0);
        expect(space.maxX).toBeGreaterThanOrEqual(0);
        expect(space.minY).toBeLessThanOrEqual(0);
        expect(space.maxY).toBeGreaterThanOrEqual(0);
        const pose = projectBodyMotion({ ...REST, roll: 90, sx: 1.28, sy: 0.4 }, box, VIEWPORT);
        expectContained(pose, VIEWPORT, box);
      }
    }
  });

  it('reserves more clearance when a caller authors a larger maximum scale', () => {
    const ordinary = bodyMotionSpace(BOX, VIEWPORT, true);
    const larger = bodyMotionSpace(BOX, VIEWPORT, true, 1.8);
    expect(larger.minX).toBeGreaterThan(ordinary.minX);
    expect(larger.maxX).toBeLessThan(ordinary.maxX);
    expect(larger.minY).toBeGreaterThan(ordinary.minY);
    expect(larger.maxY).toBeLessThan(ordinary.maxY);
    expectContained({ x: larger.maxX, y: larger.maxY, roll: 45, sx: 1.8, sy: 1.8 });
  });

  it('keeps em trajectories invariant when the pixel geometry is zoomed or translated', () => {
    const offset = { x: 76, y: -39 };
    const shiftedBox = { ...BOX, left: BOX.left + offset.x, top: BOX.top + offset.y };
    const shiftedViewport = {
      ...VIEWPORT,
      left: VIEWPORT.left + offset.x,
      top: VIEWPORT.top + offset.y,
    };
    expect(bodyMotionSpace(shiftedBox, shiftedViewport, true)).toEqual(
      bodyMotionSpace(BOX, VIEWPORT, true)
    );
    const desired = { x: 100, y: -100, roll: 48, sx: 1.3, sy: 0.7 };
    for (const zoom of [2, 1 / 64]) {
      const box: BodyBox = {
        left: BOX.left * zoom,
        top: BOX.top * zoom,
        width: BOX.width * zoom,
        height: BOX.height * zoom,
        fontSize: BOX.fontSize * zoom,
      };
      const viewport: BodyViewport = {
        left: VIEWPORT.left * zoom,
        top: VIEWPORT.top * zoom,
        width: VIEWPORT.width * zoom,
        height: VIEWPORT.height * zoom,
      };
      expect(projectBodyMotion(desired, box, viewport)).toEqual(
        projectBodyMotion(desired, BOX, VIEWPORT)
      );
    }
  });

  it('sanitizes absent geometry values and never emits NaN or a collapsed requested scale', () => {
    const box = { left: NaN, top: Infinity, width: -1, height: NaN, fontSize: 0 };
    const viewport = { left: NaN, top: Infinity, width: NaN, height: -20 };
    const pose = projectBodyMotion(
      { x: NaN, y: Infinity, roll: NaN, sx: 0, sy: NaN },
      box,
      viewport
    );
    expect(Object.values(pose).every(Number.isFinite)).toBe(true);
    expect(pose.sx).toBeGreaterThan(0);
    expect(pose.sy).toBeGreaterThan(0);
    const space = bodyMotionSpace(box, viewport, true, NaN);
    expect([space.minX, space.maxX, space.minY, space.maxY].every(Number.isFinite)).toBe(true);
    expect(space.roaming).toBe(false);
  });

  it('leaves input measurements and channel poses unchanged', () => {
    const desired = Object.freeze({ x: 100, y: -100, roll: 45, sx: 1.3, sy: 0.7 });
    const box = Object.freeze({ ...BOX });
    const viewport = Object.freeze({ ...VIEWPORT });
    const before = { ...desired };
    projectBodyMotion(desired, box, viewport);
    bodyMotionSpace(box, viewport, true);
    expect(desired).toEqual(before);
    expect(box).toEqual(BOX);
    expect(viewport).toEqual(VIEWPORT);
  });
});
