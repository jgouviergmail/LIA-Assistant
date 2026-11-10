/** Ground contact is checked in painted coordinates, independently of compensation. */
import { describe, expect, it } from 'vitest';
import { inflateSync } from 'node:zlib';
import { bodySupportFootprint, supportBodyMotion } from '../body-support';
import { projectBodyMotion, type BodyMotionPose } from '../body-motion-geometry';
import { VOLUME_SOURCE_EM, volumeProfile } from '../volume/volume-geometry';
import sourceAlpha from '../volume/__tests__/fixtures/limb-source-alpha.json';

const REST: BodyMotionPose = { x: 0, y: 0, roll: 0, sx: 1, sy: 1 };
const FOOTED = ['moss', 'lumen', 'bip', 'boulon', 'oscar'] as const;

function screenPoint(point: readonly [number, number], pose: BodyMotionPose) {
  const angle = (pose.roll * Math.PI) / 180;
  return [
    pose.x + point[0] * pose.sx * Math.cos(angle) - point[1] * pose.sy * Math.sin(angle),
    pose.y + point[0] * pose.sx * Math.sin(angle) + point[1] * pose.sy * Math.cos(angle),
  ];
}

describe('Grounded body support', () => {
  it.each(FOOTED)(
    '%s plants the selected sole during compression and a supported lean',
    character => {
      for (const variant of ['female', 'male'] as const) {
        const feet = bodySupportFootprint(character, variant)!;
        for (const side of [-1, 0, 1]) {
          const blend = (side + 1) / 2;
          const point = [
            feet.left[0] * (1 - blend) + feet.right[0] * blend,
            feet.left[1] * (1 - blend) + feet.right[1] * blend,
          ] as const;
          for (const roll of [-9, 0, 9]) {
            const pose = supportBodyMotion({ ...REST, roll, sx: 1.12, sy: 0.82 }, feet, 1, side);
            const painted = screenPoint(point, pose);
            expect(painted[0]).toBeCloseTo(point[0], 10);
            expect(painted[1]).toBeCloseTo(point[1], 10);
          }
        }
      }
    }
  );

  it.each(FOOTED)(
    '%s anchors its feet on the reviewed source sole, not its transparent canvas',
    character => {
      for (const variant of ['female', 'male'] as const) {
        const source = sourceAlpha[`${character}/${variant}`];
        const alpha = inflateSync(Buffer.from(source.alphaZlib, 'base64'));
        const scale = VOLUME_SOURCE_EM * volumeProfile(character, variant).scale;
        const feet = bodySupportFootprint(character, variant)!;
        for (const [side, point] of [feet.left, feet.right].entries()) {
          const px = (point[0] / scale + 0.5) * source.width;
          const py = (point[1] / scale + 0.5) * source.height;
          const minX = side === 0 ? 0 : source.width / 2;
          const maxX = side === 0 ? source.width / 2 : source.width;
          let bottom = 0;
          for (let y = Math.floor(source.height * 0.84); y < source.height; y++) {
            for (let x = minX; x < maxX; x++) {
              if (alpha[y * source.width + x] >= 64) bottom = Math.max(bottom, y + 0.5);
            }
          }
          expect(Math.abs(py - bottom)).toBeLessThan(0.01);
          expect(px).toBeGreaterThan(minX);
          expect(px).toBeLessThan(maxX);
          const row = Math.floor(py - 1);
          expect(alpha[row * source.width + Math.floor(px)]).toBeGreaterThanOrEqual(64);
        }
      }
    }
  );

  it('leaves airborne trajectories and floating anatomy unchanged', () => {
    const flight = { ...REST, x: 0.1, y: -0.6, roll: 70, sx: 0.9, sy: 1.1 };
    expect(supportBodyMotion(flight, bodySupportFootprint('bip', 'female'), 0, -1)).toEqual(flight);
    for (const character of ['spirit', 'nimbo', 'orbit', 'unknown']) {
      expect(bodySupportFootprint(character, 'female')).toBeNull();
      expect(supportBodyMotion(flight, null, 1, 0)).toEqual(flight);
    }
  });

  it('blends continuously through liftoff and preserves intentional travel', () => {
    const feet = bodySupportFootprint('boulon', 'male');
    const desired = { ...REST, x: 0.2, y: -0.3, roll: 6, sy: 0.9 };
    const grounded = supportBodyMotion(desired, feet, 1, 0);
    for (const weight of [0, 0.001, 0.25, 0.5, 0.999, 1]) {
      const pose = supportBodyMotion(desired, feet, weight, 0);
      expect(pose.x).toBeCloseTo(desired.x + (grounded.x - desired.x) * weight, 10);
      expect(pose.y).toBeCloseTo(desired.y + (grounded.y - desired.y) * weight, 10);
    }
  });

  it('retains identity and complete revolutions without an offset', () => {
    const feet = bodySupportFootprint('oscar', 'female');
    for (const roll of [-720, -360, 0, 360, 720]) {
      expect(supportBodyMotion({ ...REST, roll }, feet, 1, 0)).toEqual({ ...REST, roll });
    }
  });

  it('supports the shared monitor stand without inventing feet', () => {
    const monitor = bodySupportFootprint('monitor', 'female')!;
    expect(monitor.left).toEqual(monitor.right);
    expect(monitor).toEqual(bodySupportFootprint('monitor', 'male'));
    const drawn = supportBodyMotion({ ...REST, sy: 0.8, sx: 1.1 }, monitor, 1, 0);
    expect(screenPoint(monitor.left, drawn)[1]).toBeCloseTo(monitor.left[1], 10);
  });

  it('keeps viewport containment authoritative after adding a contact offset', () => {
    const box = { left: 0, top: 0, width: 78, height: 78, fontSize: 30 };
    const viewport = { left: 0, top: 0, width: 120, height: 105 };
    const supported = supportBodyMotion(
      { ...REST, roll: 15, sx: 1.1, sy: 0.82 },
      bodySupportFootprint('bip', 'female'),
      1,
      -1
    );
    const drawn = projectBodyMotion(supported, box, viewport);
    for (const x of [-1.3, 1.3]) {
      for (const y of [-1.3, 1.3]) {
        const painted = screenPoint([x, y], drawn);
        expect(39 + painted[0] * 30).toBeGreaterThanOrEqual(0);
        expect(39 + painted[0] * 30).toBeLessThanOrEqual(viewport.width);
        expect(39 + painted[1] * 30).toBeGreaterThanOrEqual(0);
        expect(39 + painted[1] * 30).toBeLessThanOrEqual(viewport.height);
      }
    }
  });

  it('bounds non-finite and excessive support inputs', () => {
    const feet = bodySupportFootprint('lumen', 'male');
    const pose = { ...REST, sy: 0.8 };
    expect(supportBodyMotion(pose, feet, NaN, Infinity)).toEqual(pose);
    expect(supportBodyMotion(pose, feet, 2, 3)).toEqual(supportBodyMotion(pose, feet, 1, 1));
    expect(supportBodyMotion(pose, feet, -1, -3)).toEqual(pose);
  });
});
