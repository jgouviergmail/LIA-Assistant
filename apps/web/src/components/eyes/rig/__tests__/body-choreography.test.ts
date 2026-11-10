/** Acting oracles observe the real spring trajectory, not merely authored keys. */
import { describe, expect, it } from 'vitest';
import { BODY_SKETCHES, type BodySketchName } from '../body-sketches';
import type { RigCharacterId } from '../acting-profile';
import type { ChannelValues } from '../channels';
import { createEyeRig, type EyeRig } from '../runtime';
import { RIG_EYE_STYLE_IDS } from '../../eye-styles';
import { createSketchClock } from '../sketches';
import { NEUTRAL_CONTEXT } from '../direction';

const INTERRUPTIONS: readonly (readonly [string, (rig: EyeRig) => void])[] = [
  ['pause', rig => rig.setLifePaused(true)],
  ['attention', rig => rig.setContext({ ...NEUTRAL_CONTEXT, activity: 'calculating' })],
  ['resize', rig => rig.setBodySpace({ minX: -1, maxX: 1, minY: -1, maxY: 1, roaming: true })],
  ['identity', rig => rig.setCharacterId('lumen')],
  ['replacement', rig => rig.playScene('body-bow')],
  ['pose', rig => rig.setPose({ expression: 'attentive', styleId: 'cozmo', family: 'calm' })],
  ['timed pause', rig => rig.pauseLifeFor(10_000)],
  ['reduced motion', rig => rig.setReducedMotion(true)],
];
const PHASE_INTERRUPTION_CASES = (['body-bow', 'body-balloon', 'body-sneeze'] as const).flatMap(
  scene => [160, 640, 1200, 2200].map(atMs => ({ scene, atMs }))
);

function actor(identity: RigCharacterId = 'bip'): EyeRig {
  const rig = createEyeRig({ characterId: identity });
  rig.setBodySpace({ minX: -2, maxX: 2, minY: -2, maxY: 1, roaming: true });
  return rig;
}

function sample(rig: EyeRig, duration: number): ChannelValues[] {
  const frames: ChannelValues[] = [];
  for (let time = 0; time < duration; time += 16) {
    rig.step(16);
    frames.push({ ...rig.values() });
  }
  return frames;
}

describe('phase-directed whole-body acting', () => {
  it.each([12, 15, 16, -12, -15, -16])(
    'supports grounded lean through the 15-degree margin, including %s degrees',
    angle => {
      const rig = actor();
      rig.playSketch([
        {
          channel: 'bodyRoll',
          keys: [{ atMs: 0, value: angle }],
          durationMs: 1500,
          spring: { frequency: 4.6, damping: 1 },
        },
        { channel: 'bodySupport', keys: [{ atMs: 0, value: 1 }], durationMs: 1500 },
      ]);
      sample(rig, 1100);
      expect(rig.values().bodySupport).toBeCloseTo(Math.abs(angle) <= 15 ? 1 : 0, 3);
    }
  );
  it.each(PHASE_INTERRUPTION_CASES)(
    '$scene yields continuously at $atMs ms and restores its stance',
    ({ scene, atMs }) => {
      for (const [reason, interrupt] of INTERRUPTIONS) {
        for (const identity of ['cozmo', 'oscar'] as const) {
          const clock = createSketchClock();
          clock.dueMs = 600_000;
          const rig = createEyeRig({
            characterId: identity,
            lifeRandom: () => 0.8,
            sketchClock: clock,
          });
          rig.setBodySpace({ minX: -2, maxX: 2, minY: -2, maxY: 1, roaming: true });
          rig.playScene(scene);
          sample(rig, atMs);
          const before = { ...rig.values() };
          interrupt(rig);
          if (reason !== 'reduced motion') expect(rig.values()).toEqual(before);
          const released = sample(rig, 6500);
          released.forEach(value => {
            expect(Math.abs(value.bodyRoll)).toBeLessThan(16);
            expect(Number.isFinite(value.bodyY)).toBe(true);
          });
          expect(released.at(-1)?.bodySupport).toBeCloseTo(1, 4);
          expect(released.at(-1)?.bodyRoll).toBeCloseTo(0, 4);
          expect(released.at(-1)?.bodyY).toBeCloseTo(0, 4);
        }
      }
    }
  );
  it.each([
    ...RIG_EYE_STYLE_IDS,
    'moss',
    'lumen',
    'bip',
    'boulon',
    'oscar',
  ] satisfies RigCharacterId[])(
    '%s releases contact while floating and lands upright',
    identity => {
      const rig = actor(identity);
      rig.playScene('body-balloon');
      const values = sample(rig, 6500);
      const airborne = values.filter(value => value.bodyY < -0.3);
      expect(airborne.length).toBeGreaterThan(15);
      airborne.forEach(value => {
        expect(value.bodySupport).toBeLessThan(0.1);
        expect(value.bodyRoll).toBe(0);
      });
      expect(values.at(-1)?.bodySupport).toBe(1);
    }
  );
  it('sleeps on a planted side with a long closed-eye hold and returns to centered support', () => {
    const rig = actor('oscar');
    rig.playScene('body-doze');
    const values = sample(rig, 6500);
    expect(
      values.filter(value => value.blinkL > 0.98 && value.blinkR > 0.98).length * 16
    ).toBeGreaterThan(900);
    values
      .filter(value => value.bodyRoll > 2)
      .forEach(value => {
        expect(value.bodySupportSide).toBeGreaterThan(0.9);
        expect(value.bodySupport).toBe(1);
        expect(value.bodyY).toBe(0);
        expect(value.footR).toBe(0);
      });
    expect(values.at(-1)?.bodySupportSide).toBe(0);
  });
  it('crosses the hop apex rather than easing to a hovering plateau', () => {
    const rig = actor();
    rig.playScene('body-hops');
    const frames = sample(rig, 1500);
    const minimum = Math.min(...frames.map(frame => frame.bodyY));
    expect(minimum).toBeLessThan(-0.25);
    const stillAir = frames.filter(
      (frame, index) =>
        index > 0 &&
        frame.bodyY < minimum * 0.8 &&
        Math.abs(frame.bodyY - frames[index - 1].bodyY) / 0.016 < 0.08
    );
    expect(stillAir.length * 16).toBeLessThan(160);
  });

  it('plants before compressing and releases ground support for the flight', () => {
    const rig = actor();
    rig.playScene('body-hops');
    const frames = sample(rig, 1500);
    expect(
      frames.some(
        frame => frame.bodySupport > 0.9 && frame.bodySy < 0.99 && Math.abs(frame.bodyY) < 0.005
      )
    ).toBe(true);
    expect(frames.some(frame => frame.bodyY < -0.25 && frame.bodySupport < 0.1)).toBe(true);
    expect(frames.at(-1)?.bodySupport).toBeGreaterThan(0.9);
  });

  it('preserves a rounded apex when a preview has less room than the authored jump', () => {
    const rig = actor();
    rig.setBodySpace({ minX: -0.45, maxX: 0.45, minY: -0.45, maxY: 0.12, roaming: false });
    rig.playScene('body-hops');
    const frames = sample(rig, 1400);
    const apex = Math.min(...frames.map(frame => frame.bodyY));
    expect(apex).toBeLessThan(-0.3);
    const flat = frames.filter(
      (frame, index) =>
        index > 0 &&
        frame.bodyY < apex * 0.85 &&
        Math.abs(frame.bodyY - frames[index - 1].bodyY) / 0.016 < 0.08
    );
    expect(flat.length * 16).toBeLessThan(100);
    frames.forEach(frame => expect(frame.bodyY).toBeLessThanOrEqual(0));
    expect(
      frames.filter(frame => frame.bodySupport > 0.9).every(frame => Math.abs(frame.bodyY) < 0.06)
    ).toBe(true);
  });

  it('holds a courteous bow with quiet feet and asymmetric hands rather than jump arms', () => {
    const rig = actor('oscar');
    rig.playScene('body-bow');
    const frames = sample(rig, 1400);
    const held = frames.filter(frame => frame.headPitch > 0.45);
    expect(held.length).toBeGreaterThan(12);
    held.forEach(frame => {
      expect(frame.bodySupport).toBeGreaterThan(0.9);
      expect(Math.abs(frame.bodyY)).toBeLessThan(0.01);
      expect(Math.abs(frame.footL) + Math.abs(frame.footR)).toBeLessThan(0.3);
    });
    expect(held.some(frame => Math.abs(frame.armL + frame.armR) > 2)).toBe(true);
  });

  it.each(['body-hops', 'body-sneeze', 'body-balloon'] satisfies BodySketchName[])(
    '%s respects a mechanical casing while an organic character keeps its softer motion',
    scene => {
      const robot = actor('bip');
      const cloud = actor('nimbo');
      robot.playScene(scene);
      cloud.playScene(scene);
      const mechanical = sample(robot, 6000);
      const organic = sample(cloud, 6000);
      const stretch = (frames: ChannelValues[]) =>
        Math.max(...frames.map(frame => Math.abs(frame.bodySy - 1)));
      expect(stretch(mechanical)).toBeLessThan(0.09);
      expect(stretch(organic)).toBeGreaterThan(stretch(mechanical) * 1.5);
    }
  );

  it.each(RIG_EYE_STYLE_IDS)(
    '%s keeps the shared monitor casing rigid during a balloon act',
    style => {
      const rig = actor(style);
      rig.playScene('body-balloon');
      const values = sample(rig, 6000);
      expect(Math.max(...values.map(value => Math.abs(value.bodySy - 1)))).toBeLessThan(0.09);
    }
  );

  it.each(BODY_SKETCHES)('%s restores support and its anchor after interruption', scene => {
    const rig = actor();
    rig.playScene(scene);
    sample(rig, 900);
    const before = { ...rig.values() };
    rig.setLifePaused(true);
    expect(rig.values()).toEqual(before);
    rig.step(1);
    expect(Math.abs(rig.values().bodyY - before.bodyY)).toBeLessThan(0.04);
    sample(rig, 3500);
    expect(rig.values().bodySupport).toBeCloseTo(1, 4);
    expect(rig.values().bodySupportSide).toBeCloseTo(0, 4);
    expect(rig.values().bodyY).toBeCloseTo(0, 4);
  });

  it.each(['body-doze', 'body-sneeze'] satisfies BodySketchName[])(
    '%s releases a small lean without inventing a full revolution',
    scene => {
      const rig = actor();
      rig.playScene(scene);
      sample(rig, scene === 'body-doze' ? 1100 : 1170);
      const before = { ...rig.values() };
      expect(Math.abs(before.bodyRoll)).toBeLessThan(10);
      rig.setLifePaused(true);
      expect(rig.values()).toEqual(before);
      const released = sample(rig, 2400);
      released.forEach(value => expect(Math.abs(value.bodyRoll)).toBeLessThan(12));
    }
  );
});
