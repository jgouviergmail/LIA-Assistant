import { describe, expect, it } from 'vitest';
import { createEyeRig, type EyeRig } from '../runtime';
import { NEUTRAL_CONTEXT } from '../direction';
import { createLifeRandom } from '../life';
import { projectBodyMotion } from '../../body-motion-geometry';
import { BODY_SKETCHES } from '../body-sketches';
import { RIG_EYE_STYLE_IDS } from '../../eye-styles';
import type { RigCharacterId } from '../acting-profile';

function advance(rig: EyeRig, ms: number) {
  for (let time = 0; time < ms; time += 16) rig.step(Math.min(16, ms - time));
}
const HOME = { bodyX: 0, bodyY: 0, bodyRoll: 0, bodySx: 1, bodySy: 1 };
const SPACE = { minX: -3, maxX: 3, minY: -2, maxY: 1, roaming: true };
const IDENTITIES = [
  ...RIG_EYE_STYLE_IDS,
  'spirit',
  'moss',
  'lumen',
  'nimbo',
  'orbit',
  'bip',
  'boulon',
  'oscar',
] satisfies RigCharacterId[];

describe('personality performs through the existing native rig', () => {
  it('rejects retired scenes at the explicit entry point without disturbing a current pose', () => {
    const rig = createEyeRig({ characterId: 'bip' });
    for (const retired of ['body-roll', 'body-somersault', 'body-jig', 'dizzy', 'brow-groove']) {
      const before = { ...rig.values() };
      Reflect.apply(rig.playScene, rig, [retired]);
      expect(rig.isPerforming()).toBe(false);
      expect(rig.values()).toEqual(before);
    }
    rig.playScene('body-hops');
    advance(rig, 600);
    const inFlight = { ...rig.values() };
    Reflect.apply(rig.playScene, rig, ['body-roll']);
    expect(rig.sketchClock().scene).toBe('body-hops');
    expect(rig.values()).toEqual(inFlight);
  });

  it.each(IDENTITIES)('keeps %s breathing in a quiet, finite pose', characterId => {
    const rig = createEyeRig({ characterId, lifeRandom: createLifeRandom(7) });
    const mass = [];
    for (let frame = 0; frame < 300; frame += 1) {
      rig.step(16);
      const pose = rig.values();
      expect(Object.values(pose).every(Number.isFinite)).toBe(true);
      expect(pose.bodyRoll).toBe(0);
      mass.push(pose.mass);
    }
    expect(Math.max(...mass) - Math.min(...mass)).toBeGreaterThan(0.005);
  });

  it('separates the quick robot startle, soft recovery and formal bow on the native rig', () => {
    const robot = createEyeRig({ characterId: 'boulon' });
    const organic = createEyeRig({ characterId: 'lumen' });
    const oscar = createEyeRig({ characterId: 'oscar' });
    robot.playScene('body-startle');
    organic.playScene('body-startle');
    oscar.playScene('body-bow');
    for (const rig of [robot, organic, oscar]) advance(rig, 375);
    expect(robot.values().armL - organic.values().armL).toBeGreaterThan(1);
    expect(Math.abs(robot.values().gazeX)).toBeGreaterThan(0.1);
    expect(organic.values().bodySy - robot.values().bodySy).toBeGreaterThan(0.01);
    advance(oscar, 850);
    expect(oscar.values().headPitch).toBeGreaterThan(0.55);
    expect(oscar.values().bodySupport).toBe(1);
    expect(oscar.values().bodyY).toBe(0);
  });

  it('lets Bip land before one smooth wink and keeps Nimbo inhalation readable before its sneeze', () => {
    const bip = createEyeRig({ characterId: 'bip' });
    bip.setBodySpace(SPACE);
    bip.playScene('body-hops');
    advance(bip, 2100);
    let closed = false;
    for (let time = 2100; time < 3250; time += 16) {
      bip.step(16);
      if (bip.values().blinkR < 0.94) continue;
      closed = true;
      expect(bip.values().blinkL).toBeLessThan(0.1);
      expect(Math.abs(bip.values().bodyY)).toBeLessThan(0.08);
    }
    expect(closed).toBe(true);
    const nimbo = createEyeRig({ characterId: 'nimbo' });
    nimbo.playScene('body-sneeze');
    let inhaled = false;
    let hit = false;
    for (let time = 0; time < 1900; time += 16) {
      nimbo.step(16);
      if (nimbo.values().headPitch < -0.25) inhaled = true;
      if (nimbo.values().headPitch > 0.3 && inhaled) hit = true;
    }
    expect(inhaled).toBe(true);
    expect(hit).toBe(true);
  });

  it('gives Oscar a bow, a held courteous smile and a complete recovery', () => {
    const rig = createEyeRig({ characterId: 'oscar' });
    rig.setBodySpace(SPACE);
    rig.playScene('body-bow');
    let heldFrames = 0;
    let tuckedFrames = 0;
    for (let elapsed = 0; elapsed < 2100; elapsed += 16) {
      rig.step(16);
      const pose = rig.values();
      expect(pose.headPitch).toBeLessThanOrEqual(1.3);
      expect(Math.abs(pose.bodySy - 1)).toBeLessThan(0.01);
      expect(pose.bodySupport).toBe(1);
      expect(pose.bodyY).toBe(0);
      expect([pose.footL, pose.footR]).toEqual([0, 0]);
      if (pose.headPitch <= 1.1) continue;
      expect(pose.gazeX).toBeLessThan(-0.07);
      expect(pose.mouthCurve).toBeGreaterThan(0);
      heldFrames++;
      if (pose.armL < -8 && pose.wristL < -6) tuckedFrames++;
    }
    expect(heldFrames * 16).toBeGreaterThanOrEqual(240);
    expect(tuckedFrames * 16).toBeGreaterThanOrEqual(160);
    advance(rig, 7000);
    expect(rig.values()).toMatchObject(HOME);
    expect(rig.values().headPitch).toBeCloseTo(0, 4);
  });

  it('changes identity without teleporting the current performance and yields to real speech', () => {
    const rig = createEyeRig({ characterId: 'orbit' });
    rig.setBodySpace(SPACE);
    rig.playScene('body-balloon');
    advance(rig, 1100);
    const before = { ...rig.values() };
    rig.setCharacterId('boulon');
    expect(rig.isPerforming()).toBe(false);
    expect(rig.values()).toEqual(before);
    advance(rig, 3000);
    expect(rig.values()).toMatchObject(HOME);
    rig.playScene('body-startle');
    advance(rig, 650);
    rig.setContext({ ...NEUTRAL_CONTEXT, responding: true });
    expect(rig.isPerforming()).toBe(false);
    advance(rig, 3000);
    expect(rig.values()).toMatchObject(HOME);
  });

  it.each(['spirit', 'moss', 'lumen', 'nimbo', 'orbit', 'bip', 'boulon', 'oscar'] as const)(
    'contains %s at real miniature and XL dimensions, even when a performance is interrupted at a corner',
    characterId => {
      for (const fontSize of [40 / 2.6, 20, 64]) {
        const rig = createEyeRig({ characterId, lifeRandom: createLifeRandom(7) });
        rig.setBodySpace(SPACE);
        const box = { left: 1, top: 1, width: fontSize * 2.6, height: fontSize * 2.6, fontSize };
        const viewport = { left: 0, top: 0, width: 320, height: 400 };
        for (const scene of BODY_SKETCHES) {
          rig.playScene(scene);
          for (let frame = 0; frame < 350; frame++) {
            rig.step(16);
            if (frame === 65) rig.setLifePaused(true);
            const values = rig.values();
            const pose = projectBodyMotion(
              {
                x: values.bodyX,
                y: values.bodyY,
                roll: values.bodyRoll,
                sx: values.bodySx,
                sy: values.bodySy,
              },
              box,
              viewport
            );
            const angle = (pose.roll * Math.PI) / 180;
            for (const x of [-box.width / 2, box.width / 2])
              for (const y of [-box.height / 2, box.height / 2]) {
                const px =
                  box.left +
                  box.width / 2 +
                  pose.x * fontSize +
                  Math.cos(angle) * x * pose.sx -
                  Math.sin(angle) * y * pose.sy;
                const py =
                  box.top +
                  box.height / 2 +
                  pose.y * fontSize +
                  Math.sin(angle) * x * pose.sx +
                  Math.cos(angle) * y * pose.sy;
                expect(px).toBeGreaterThanOrEqual(-0.001);
                expect(px).toBeLessThanOrEqual(viewport.width + 0.001);
                expect(py).toBeGreaterThanOrEqual(-0.001);
                expect(py).toBeLessThanOrEqual(viewport.height + 0.001);
              }
          }
          expect(rig.values()).toMatchObject(HOME);
          rig.setLifePaused(false);
        }
      }
    }
  );
});
