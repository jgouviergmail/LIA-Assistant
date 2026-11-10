/** Intent, support and prosody survive the actual native spring evaluation. */
import { describe, expect, it } from 'vitest';
import { createEyeRig, type EyeRig } from '../runtime';
import { limbLoops } from '../limbs';
import { limbRestTapes } from '../limb-rest';
import { limbSpeechTapes } from '../limb-speech';
import { calibratedLoops } from '../poses';
import { mimicTapes } from '../life';
import type { ChannelValues } from '../channels';
import type { Tape } from '../tape';
import { directActingTapes } from '../acting-scenes';
import { resolveActingProfile } from '../acting-profile';

function frames(rig: EyeRig, duration: number): ChannelValues[] {
  const values: ChannelValues[] = [];
  for (let at = 0; at < duration; at += 16) {
    rig.step(16);
    values.push({ ...rig.values() });
  }
  return values;
}

describe('limb phrasing', () => {
  it('follows the existing breath while grounded legs and feet stay still', () => {
    const breath = calibratedLoops('neutral', 'calm', 1);
    const periods = breath.filter(loop => loop.channel === 'mass').map(loop => loop.periodMs);
    expect(limbLoops('bip', breath).every(loop => periods.includes(loop.periodMs))).toBe(true);
    const values = frames(createEyeRig({ characterId: 'bip' }), 20_000);
    expect(
      Math.max(...values.map(value => value.armL)) - Math.min(...values.map(value => value.armL))
    ).toBeGreaterThan(1);
    values.forEach(value => {
      expect([value.legL, value.legR, value.footL, value.footR]).toEqual([0, 0, 0, 0]);
    });
  });

  it('answers surprise, thought and disappointment with different limb intentions', () => {
    const traces = (['gasp', 'hmm', 'sulk'] as const).map(mimic => {
      const rig = createEyeRig({ characterId: 'bip', idleScale: 0 });
      rig.playSketch(limbRestTapes(mimicTapes(mimic, 1), 'bip', 1, mimic));
      return frames(rig, 1100);
    });
    expect(Math.max(...traces[0].map(value => value.armL))).toBeGreaterThan(8);
    expect(Math.max(...traces[1].map(value => value.wristL))).toBeGreaterThan(5);
    expect(Math.min(...traces[2].map(value => value.armL))).toBeLessThan(-2);
    expect(limbRestTapes(mimicTapes('wiggle', 1), 'bip', 1, 'wiggle')).toEqual([]);
  });

  it('plants the opposite foot before a playful rest tap and closes the support transfer', () => {
    const rig = createEyeRig({ characterId: 'bip', idleScale: 0 });
    rig.playSketch(limbRestTapes(mimicTapes('giggle', 1), 'bip', 1, 'giggle'));
    const values = frames(rig, 4000);
    expect(values.some(value => value.footL > 4)).toBe(true);
    values
      .filter(value => value.footL > 1)
      .forEach(value => {
        expect(value.bodySupportSide).toBeGreaterThan(0.9);
        expect(value.footR).toBe(0);
      });
    expect(values.at(-1)?.bodySupportSide).toBeCloseTo(0, 3);
    expect(values.at(-1)?.footL).toBeCloseTo(0, 3);
  });

  it.each(['moss', 'oscar'] as const)(
    '%s keeps the support selector at its actual sole despite facial amplitude',
    identity => {
      const rig = createEyeRig({ characterId: identity, idleScale: 0 });
      const gesture = limbRestTapes(mimicTapes('giggle', 1), identity, 1, 'giggle');
      rig.playSketch(
        directActingTapes(gesture, resolveActingProfile(identity, 'cozmo'), {
          minX: -1,
          maxX: 1,
          minY: -1,
          maxY: 1,
          roaming: false,
        })
      );
      const values = frames(rig, 2400);
      values
        .filter(value => value.footL > 4)
        .forEach(value => expect(value.bodySupportSide).toBeGreaterThan(0.99));
      expect(values.some(value => value.footL > 4)).toBe(true);
    }
  );

  it('places one speech stroke on phrase stress and lets the wrist follow, leaving a quiet phrase alone', () => {
    const speech: Tape[] = [
      {
        channel: 'mouthOpen',
        durationMs: 5200,
        keys: [
          { atMs: 0, value: 0.5 },
          { atMs: 1800, value: 0 },
          { atMs: 2600, value: 0.3 },
          { atMs: 4300, value: 0 },
        ],
      },
      {
        channel: 'browYL',
        durationMs: 5200,
        keys: [
          { atMs: 900, value: -0.055 },
          { atMs: 1200, value: 0 },
          { atMs: 3200, value: -0.032 },
          { atMs: 3400, value: 0 },
        ],
      },
    ];
    const rig = createEyeRig({ characterId: 'bip', idleScale: 0 });
    rig.playSketch(limbSpeechTapes(speech, 'bip'));
    const values = frames(rig, 5200);
    values.slice(0, 30).forEach(value => expect(Math.abs(value.armL)).toBeLessThan(1));
    expect(Math.max(...values.slice(45, 100).map(value => value.armL))).toBeGreaterThan(5);
    const armPeak = values.findIndex(value => value.armL > 6);
    const wristPeak = values.findIndex(value => value.wristL > 3.75);
    expect(wristPeak).toBeGreaterThan(armPeak);
    values.slice(155).forEach(value => {
      expect(Math.abs(value.armL)).toBeLessThan(0.5);
      expect(Math.abs(value.wristL)).toBeLessThan(0.5);
    });
    const precise = frames(createEyeRig({ characterId: 'boulon', idleScale: 0 }), 500);
    expect(precise.every(value => value.armL === 0 && value.wristL === 0)).toBe(true);
    const keyTime = (identity: 'boulon' | 'oscar') =>
      limbSpeechTapes(speech, identity)
        .find(tape => tape.channel === 'wristL')
        ?.keys.find(key => key.value > 0)?.atMs;
    expect(keyTime('boulon')).toBeLessThan(keyTime('oscar') ?? 0);
    expect(
      limbSpeechTapes(
        [
          speech[0],
          {
            ...speech[1],
            keys: [
              { atMs: 1640, value: -0.06 },
              { atMs: 1710, value: 0 },
            ],
          },
        ],
        'oscar'
      )
    ).toEqual([]);
  });
});
