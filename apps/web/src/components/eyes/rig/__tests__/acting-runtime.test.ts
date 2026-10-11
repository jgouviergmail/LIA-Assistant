import { describe, expect, it } from 'vitest';
import { createEyeRig, type EyeRig } from '../runtime';
import { NEUTRAL_CONTEXT } from '../direction';
import { createLifeRandom } from '../life';
import { projectBodyMotion } from '../../body-motion-geometry';
import { BODY_SKETCHES } from '../body-sketches';

function advance(rig: EyeRig, ms: number) {
  for (let time = 0; time < ms; time += 16) rig.step(Math.min(16, ms - time));
}
const HOME = { bodyX: 0, bodyY: 0, bodyRoll: 0, bodySx: 1, bodySy: 1 };
const SPACE = { minX: -3, maxX: 3, minY: -2, maxY: 1, roaming: true };

describe('personality performs through the existing native rig', () => {
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
      if (nimbo.values().headPitch > 0.25) inhaled = true;
      if (nimbo.values().headPitch < -0.3 && inhaled) hit = true;
    }
    expect(inhaled).toBe(true);
    expect(hit).toBe(true);
  });

  it('gives Oscar a bow, a held courteous smile and a complete recovery', () => {
    const rig = createEyeRig({ characterId: 'oscar' });
    rig.setBodySpace(SPACE);
    rig.playScene('body-bow');
    advance(rig, 1000);
    expect(rig.values().headPitch).toBeGreaterThan(0.4);
    expect(rig.values().bodySy).toBeLessThan(0.95);
    expect(rig.values().mouthCurve).toBeGreaterThan(0);
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
    rig.playScene('body-roll');
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
