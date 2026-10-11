import { describe, expect, it, vi } from 'vitest';
import type { BodyMotionSpace } from '@/components/eyes/body-motion-geometry';
import { BODY_SKETCHES, type BodySketchName } from '../body-sketches';
import { CHANNELS, type ChannelValues } from '../channels';
import { absolute, warpTapes } from '../choreo';
import { NEUTRAL_CONTEXT } from '../direction';
import { createEyeRig, type EyeRig } from '../runtime';
import { createSketchClock } from '../sketches';

const ROOM: BodyMotionSpace = { minX: -4, maxX: 3, minY: -3, maxY: 0.4, roaming: true };
const BODY = ['bodyX', 'bodyY', 'bodyRoll', 'bodySx', 'bodySy'] as const;
type BodyValues = Pick<ChannelValues, (typeof BODY)[number]>;
const HOME: BodyValues = { bodyX: 0, bodyY: 0, bodyRoll: 0, bodySx: 1, bodySy: 1 };

function body(rig: EyeRig): BodyValues {
  const values = rig.values();
  return {
    bodyX: values.bodyX,
    bodyY: values.bodyY,
    bodyRoll: values.bodyRoll,
    bodySx: values.bodySx,
    bodySy: values.bodySy,
  };
}

function run(rig: EyeRig, milliseconds: number, observe?: (values: BodyValues) => void) {
  for (let elapsed = 0; elapsed < milliseconds; elapsed += 16) {
    rig.step(Math.min(16, milliseconds - elapsed));
    observe?.(body(rig));
  }
}

function actor(random = 0.8): EyeRig {
  const rig = createEyeRig({
    initial: { expression: 'neutral', styleId: 'smiley', family: 'calm' },
    lifeRandom: () => random,
  });
  rig.setBodySpace(ROOM);
  return rig;
}

/** Angular displacement as actually seen, including equivalent ±360 normalizations. */
function angleDelta(from: number, to: number): number {
  return ((((to - from + 180) % 360) + 360) % 360) - 180;
}

describe('Native whole-body runtime', () => {
  it.each(BODY_SKETCHES)('returns all five body channels exactly home after %s', name => {
    const rig = actor();
    rig.playScene(name);
    expect(rig.isPerforming()).toBe(true);
    let moved = false;
    run(rig, 8_000, values => {
      moved ||= BODY.some(key => values[key] !== HOME[key]);
    });
    expect(moved).toBe(true);
    expect(rig.isPerforming()).toBe(false);
    expect(body(rig)).toEqual(HOME);
    expect(rig.sketchClock().scene).toBeNull();
  });

  it.each(['body-roll', 'body-somersault', 'body-balloon'] satisfies BodySketchName[])(
    'finishes both directions of %s without an inverse revolution on release',
    name => {
      for (const random of [0.2, 0.8]) {
        const direction = random < 0.5 ? -1 : 1;
        const terminal = name === 'body-balloon' ? 720 : 360;
        const rig = actor(random);
        rig.playScene(name);
        let previous = 0;
        let committed = false;
        let peak = 0;
        let worstReverse = 0;
        run(rig, 8_000, values => {
          const phase = direction * values.bodyRoll;
          peak = Math.max(peak, phase);
          if (phase > 20) committed = true;
          if (committed)
            worstReverse = Math.min(
              worstReverse,
              direction * angleDelta(previous, values.bodyRoll)
            );
          previous = values.bodyRoll;
        });
        expect(peak).toBeGreaterThan(terminal - 0.5);
        expect(worstReverse).toBeGreaterThan(-0.01);
        expect(body(rig)).toEqual(HOME);
      }
    }
  );

  const interruptions: ReadonlyArray<readonly [string, (rig: EyeRig) => void]> = [
    ['activity', rig => rig.setContext({ ...NEUTRAL_CONTEXT, activity: 'calculating' })],
    ['audio response', rig => rig.setContext({ ...NEUTRAL_CONTEXT, responding: true })],
    [
      'speaking pose',
      rig => rig.setPose({ expression: 'speaking', styleId: 'smiley', family: 'calm' }),
    ],
    [
      'expression',
      rig => rig.setPose({ expression: 'attentive', styleId: 'smiley', family: 'calm' }),
    ],
  ];

  it.each(interruptions)(
    'yields to %s from its current visible position, then eases home',
    (_label, interrupt) => {
      const rig = actor();
      rig.playScene('body-balloon');
      run(rig, 1_600);
      expect(rig.isPerforming()).toBe(true);
      const before = body(rig);
      expect(Math.abs(before.bodyRoll)).toBeGreaterThan(20);
      interrupt(rig);
      expect(rig.isPerforming()).toBe(false);
      const after = body(rig);
      expect(after.bodyX).toBe(before.bodyX);
      expect(after.bodyY).toBe(before.bodyY);
      expect(after.bodySx).toBe(before.bodySx);
      expect(after.bodySy).toBe(before.bodySy);
      expect(angleDelta(before.bodyRoll, after.bodyRoll)).toBe(0);
      rig.step(1);
      expect(Math.abs(angleDelta(before.bodyRoll, rig.values().bodyRoll))).toBeLessThan(5);
      expect(Math.abs(rig.values().bodyX - before.bodyX)).toBeLessThan(0.1);
      run(rig, 3_000);
      expect(body(rig)).toEqual(HOME);
    }
  );

  it('uses new body space for future trips and interrupts an in-flight resize continuously', () => {
    const rig = actor();
    const local = { minX: -0.06, maxX: 0.04, minY: -0.1, maxY: 0.1, roaming: false };
    rig.setBodySpace(local);
    rig.playScene('body-balloon');
    run(rig, 8_000, values => {
      expect(values.bodyX).toBeGreaterThanOrEqual(local.minX - 1e-9);
      expect(values.bodyX).toBeLessThanOrEqual(local.maxX + 1e-9);
      expect(values.bodyY).toBeGreaterThanOrEqual(local.minY - 1e-9);
      expect(values.bodyY).toBeLessThanOrEqual(local.maxY + 1e-9);
    });
    rig.setBodySpace(ROOM);
    rig.playScene('body-balloon');
    run(rig, 1_200);
    const before = body(rig);
    expect(Math.abs(before.bodyX)).toBeGreaterThan(0.5);
    rig.setBodySpace(local);
    expect(rig.isPerforming()).toBe(false);
    expect(body(rig).bodyX).toBe(before.bodyX);
    expect(angleDelta(before.bodyRoll, body(rig).bodyRoll)).toBe(0);
    run(rig, 3_000);
    expect(body(rig)).toEqual(HOME);
    rig.playScene('body-hops');
    expect(rig.isPerforming()).toBe(true);
    rig.setBodySpace({ ...local });
    expect(rig.isPerforming()).toBe(true);
  });

  it('pauses autonomous resting time during interaction and resumes the remaining wait', () => {
    const clock = createSketchClock();
    clock.dueMs = 900;
    const rig = createEyeRig({ lifeRandom: () => 0.8, sketchClock: clock });
    rig.setBodySpace(ROOM);
    rig.setLifePaused(true);
    rig.playScene('body-hops');
    run(rig, 20_000);
    expect(rig.isPerforming()).toBe(false);
    expect(clock.restedMs).toBe(0);
    expect(body(rig)).toEqual(HOME);
    rig.setLifePaused(false);
    run(rig, 800);
    expect(rig.isPerforming()).toBe(false);
    expect(clock.restedMs).toBe(800);
    run(rig, 112);
    expect(rig.isPerforming()).toBe(true);
  });

  it('measures temporary suppression in rig time and cannot expire on wall-clock timers', () => {
    vi.useFakeTimers();
    try {
      const rig = actor();
      rig.pauseLifeFor(1_000);
      vi.advanceTimersByTime(60_000);
      rig.step(0);
      rig.step(-16);
      rig.playScene('body-hops');
      expect(rig.isPerforming()).toBe(false);
      run(rig, 992);
      rig.playScene('body-hops');
      expect(rig.isPerforming()).toBe(false);
      rig.step(16);
      rig.playScene('body-hops');
      expect(rig.isPerforming()).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it('interrupts for pointer interaction without snapping and preserves the pause until released', () => {
    const rig = actor();
    rig.playScene('body-roll');
    run(rig, 1_200);
    const before = body(rig);
    rig.setLifePaused(true);
    expect(rig.isPerforming()).toBe(false);
    expect(body(rig).bodyX).toBe(before.bodyX);
    expect(angleDelta(before.bodyRoll, body(rig).bodyRoll)).toBe(0);
    run(rig, 3_000);
    expect(body(rig)).toEqual(HOME);
    rig.playScene('body-hops');
    expect(rig.isPerforming()).toBe(false);
    rig.setLifePaused(false);
    rig.playScene('body-hops');
    expect(rig.isPerforming()).toBe(true);
  });

  it('suppresses scenes under reduced motion and settles an active flight immediately when enabled', () => {
    const rig = createEyeRig({ reducedMotion: true, lifeRandom: () => 0.8 });
    rig.setBodySpace(ROOM);
    for (const name of BODY_SKETCHES) {
      rig.playScene(name);
      expect(rig.step(5_000)).toBe(false);
      expect(rig.isPerforming()).toBe(false);
      expect(body(rig)).toEqual(HOME);
    }
    rig.setReducedMotion(false);
    rig.playScene('body-balloon');
    run(rig, 1_200);
    expect(body(rig)).not.toEqual(HOME);
    rig.setReducedMotion(true);
    expect(rig.isPerforming()).toBe(false);
    expect(body(rig)).toEqual(HOME);
    expect(rig.step(16)).toBe(false);
  });

  it('warps the five body channels on one tempo while preserving their absolute endpoints', () => {
    let draws = 0;
    const entropy = [0.1, 0.9, 0.2, 0.8, 0.3, 0.7];
    const tapes = BODY.map(channel =>
      absolute(
        channel,
        [
          [0, CHANNELS[channel].rest],
          [250, CHANNELS[channel].rest + 0.2],
          [750, CHANNELS[channel].rest],
        ],
        1_100
      )
    );
    const warped = warpTapes(tapes, () => entropy[draws++ % entropy.length]);
    const times = warped[0].keys.map(key => key.atMs);
    for (const tape of warped) {
      expect(tape.keys.map(key => key.atMs)).toEqual(times);
      expect(tape.durationMs).toBe(warped[0].durationMs);
      expect(tape.keys.map(key => key.value)).toEqual(
        tapes.find(source => source.channel === tape.channel)!.keys.map(key => key.value)
      );
    }
    expect(times).not.toEqual([0, 250, 750]);
  });
});
