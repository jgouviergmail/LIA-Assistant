import { describe, expect, it } from 'vitest';

import type { BodyMotionSpace } from '@/components/eyes/body-motion-geometry';
import {
  BODY_SKETCHES,
  bodySketchTapes,
  type BodySketchName,
} from '@/components/eyes/rig/body-sketches';
import { SKETCHES, sketchDurationMs, sketchTapes } from '@/components/eyes/rig/sketches';
import { createEyeRig } from '@/components/eyes/rig/runtime';
import { springStep } from '@/components/eyes/rig/spring';
import { tapeTargetAt, type Tape } from '@/components/eyes/rig/tape';
import { CHANNELS } from '../channels';

const ROOM: BodyMotionSpace = { minX: -4, maxX: 3, minY: -3, maxY: 0.4, roaming: true };
const EDGE: BodyMotionSpace = { minX: -0.08, maxX: 0.02, minY: 0, maxY: 0.04, roaming: true };
const BODY_CHANNELS = [
  'bodyX',
  'bodyY',
  'bodyRoll',
  'bodySx',
  'bodySy',
  'bodySupport',
  'bodySupportSide',
] as const;

function channel(tapes: Tape[], name: (typeof BODY_CHANNELS)[number]): Tape {
  const tape = tapes.find(candidate => candidate.channel === name);
  if (!tape) throw new Error(`missing ${name}`);
  return tape;
}

/** The actual analytic spring follows the planned targets, not a linear keyframe oracle. */
function samples(tape: Tape): number[] {
  let state = { value: CHANNELS[tape.channel].rest, velocity: 0 };
  const values: number[] = [];
  for (let time = 0; time <= (tape.durationMs ?? 0); time += 16) {
    state = springStep(state, tapeTargetAt(tape, time) ?? state.value, tape.spring!, 16);
    values.push(state.value);
  }
  return values;
}

function extremes(tape: Tape): { min: number; max: number } {
  const values = samples(tape);
  return { min: Math.min(...values), max: Math.max(...values) };
}

describe('whole-body scenes', () => {
  it('keeps the retained performances upright for either direction', () => {
    expect(
      SKETCHES.filter(name => /^(body-roll|body-somersault|body-jig|dizzy|brow-groove)$/.test(name))
    ).toEqual([]);
    for (const name of BODY_SKETCHES) {
      for (const draw of [0.2, 0.8]) {
        const roll = channel(
          bodySketchTapes(name, ROOM, () => draw),
          'bodyRoll'
        );
        expect(samples(roll).every(value => Math.abs(value) <= 12)).toBe(true);
      }
    }
  });

  it.each(BODY_SKETCHES)(
    '%s carries the face with a weighted head, then brings the head home',
    name => {
      const rig = createEyeRig({
        initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      });
      rig.playSketch(bodySketchTapes(name, ROOM));
      let movement = 0;
      for (let frame = 0; frame < 500; frame++) {
        rig.step(16);
        movement = Math.max(movement, Math.abs(rig.values().headPitch));
        expect(Math.abs(rig.values().headPitch)).toBeLessThanOrEqual(0.75);
      }
      expect(movement).toBeGreaterThan(0.04);
      expect(rig.values().headPitch).toBe(0);
    }
  );
  it('registers the retained body performances on the existing catalogue and routes host entropy', () => {
    expect(BODY_SKETCHES).toEqual([
      'body-hops',
      'body-doze',
      'body-sneeze',
      'body-balloon',
      'body-startle',
      'body-bow',
    ]);
    for (const name of BODY_SKETCHES) {
      expect(SKETCHES).toContain(name);
      expect(sketchTapes(name, ROOM, () => 0.2)).toEqual(bodySketchTapes(name, ROOM, () => 0.2));
    }
  });

  it('moves the whole character and its eyes, brows and mouth in three to five seconds', () => {
    for (const name of BODY_SKETCHES) {
      const tapes = bodySketchTapes(name);
      const duration = sketchDurationMs(tapes);
      expect(duration).toBeGreaterThanOrEqual(3000);
      expect(duration).toBeLessThanOrEqual(5000);
      expect(
        new Set(tapes.filter(tape => tape.channel.startsWith('body')).map(tape => tape.channel))
      ).toEqual(new Set(BODY_CHANNELS));
      expect(tapes.some(tape => /^(sy|blink|gaze)/.test(tape.channel))).toBe(true);
      expect(tapes.some(tape => tape.channel.startsWith('brow'))).toBe(true);
      expect(tapes.some(tape => tape.channel.startsWith('mouth'))).toBe(true);
      for (const tape of tapes) {
        expect(
          tape.keys.every(
            (key, index) =>
              Number.isFinite(key.value) && (index === 0 || key.atMs >= tape.keys[index - 1].atMs)
          )
        ).toBe(true);
      }
    }
  });

  it('keeps the spring trajectory within the available room, including an anchor against an edge', () => {
    for (const space of [ROOM, EDGE]) {
      for (const name of BODY_SKETCHES) {
        const tapes = bodySketchTapes(name, space, () => 0.8);
        for (const [axis, min, max] of [
          ['bodyX', space.minX, space.maxX],
          ['bodyY', space.minY, space.maxY],
        ] as const) {
          const range = extremes(channel(tapes, axis));
          expect({
            name,
            axis,
            contained: range.min >= min - 1e-9 && range.max <= max + 1e-9,
          }).toEqual({ name, axis, contained: true });
        }
        for (const axis of ['bodySx', 'bodySy'] as const) {
          const range = extremes(channel(tapes, axis));
          expect(range.min).toBeGreaterThan(0.35);
          expect(range.max).toBeLessThanOrEqual(1.3);
        }
      }
    }
  });

  it('lands and settles at its exact anchor', () => {
    for (const name of BODY_SKETCHES) {
      const tapes = bodySketchTapes(name, ROOM);
      for (const axis of BODY_CHANNELS) {
        const tape = channel(tapes, axis);
        const rest = CHANNELS[axis].rest;
        const home = tape.keys.at(-1)!.value;
        expect(home).toBe(rest);
        expect(tape.keys.at(-1)!.atMs).toBeLessThanOrEqual(sketchDurationMs(tapes) - 600);
        expect(Math.abs(samples(tape).at(-1)! - home)).toBeLessThan(0.01);
      }
    }
  });

  it('anticipates a hop, stretches in the air, then compresses on landing before settling', () => {
    const tapes = bodySketchTapes('body-hops', ROOM);
    expect(tapeTargetAt(channel(tapes, 'bodyY'), 200)).toBe(0);
    expect(tapeTargetAt(channel(tapes, 'bodySupport'), 200)).toBe(1);
    expect(tapeTargetAt(channel(tapes, 'bodySy'), 200)).toBeLessThan(1);
    expect(tapeTargetAt(channel(tapes, 'bodyY'), 600)).toBeLessThan(-0.3);
    expect(tapeTargetAt(channel(tapes, 'bodySy'), 600)).toBeGreaterThan(1);
    expect(tapeTargetAt(channel(tapes, 'bodySy'), 1050)).toBeLessThan(1);
    expect(tapeTargetAt(channel(tapes, 'bodySy'), 3500)).toBe(1);
    // With no room above, grounded compression replaces an impossible jump.
    const edgeY = channel(bodySketchTapes('body-hops', EDGE), 'bodyY');
    expect(tapeTargetAt(edgeY, 200)).toBe(0);
    expect(tapeTargetAt(edgeY, 600)).toBe(0);
  });

  it('holds a grounded sleepy lean and reopens both eyes when it wakes', () => {
    const tapes = bodySketchTapes('body-doze', ROOM);
    expect(tapeTargetAt(channel(tapes, 'bodyRoll'), 2100)).toBe(7);
    expect(tapeTargetAt(channel(tapes, 'bodyRoll'), 3000)).toBe(7);
    expect(samples(channel(tapes, 'bodySupport')).every(value => value === 1)).toBe(true);
    expect(samples(channel(tapes, 'bodyY')).every(value => value === 0)).toBe(true);
    expect(
      tapes
        .filter(tape => /^(foot|leg)/.test(tape.channel))
        .every(tape => samples(tape).every(value => value === 0))
    ).toBe(true);
    for (const side of ['L', 'R']) {
      const blink = tapes.find(tape => tape.channel === `blink${side}`)!;
      expect(tapeTargetAt(blink, 2100)).toBe(1);
      expect(tapeTargetAt(blink, 3000)).toBe(1);
      expect(tapeTargetAt(blink, 4500)).toBe(0);
    }
  });

  it('keeps the floor fixed and performs grounded anticipation when no upward room exists', () => {
    const top: BodyMotionSpace = { minX: -1, maxX: 1, minY: 0, maxY: 1.2, roaming: true };
    for (const name of ['body-hops', 'body-startle'] satisfies BodySketchName[]) {
      const tapes = bodySketchTapes(name, top);
      const tape = channel(tapes, 'bodyY');
      const values = samples(tape);
      expect(values.every(value => value === 0)).toBe(true);
      expect(samples(channel(tapes, 'bodySupport')).every(value => value === 1)).toBe(true);
      expect(extremes(channel(tapes, 'bodySy')).min).toBeLessThan(0.95);
      expect(samples(channel(tapes, 'bodyRoll')).every(value => Math.abs(value) <= 12)).toBe(true);
      expect(
        tapes
          .filter(tape => /^(foot|leg)/.test(tape.channel))
          .every(tape => samples(tape).every(value => value === 0))
      ).toBe(true);
    }
  });

  it('makes a single upright rise, holds the look at its apex, then lands and recovers', () => {
    const roaming = bodySketchTapes('body-balloon', ROOM, () => 0.2);
    const local = bodySketchTapes('body-balloon', { ...ROOM, roaming: false }, () => 0.2);
    const mirrored = bodySketchTapes('body-balloon', ROOM, () => 0.8);
    const y = channel(roaming, 'bodyY');
    expect(tapeTargetAt(y, 310)).toBe(0);
    expect(tapeTargetAt(y, 1450)).toBeLessThan(-0.7);
    expect(tapeTargetAt(y, 2000)).toBe(tapeTargetAt(y, 1450));
    expect(tapeTargetAt(channel(roaming, 'bodySupport'), 2000)).toBe(0);
    const height = samples(y);
    const contact = samples(channel(roaming, 'bodySupport'));
    height.forEach((value, frame) => {
      if (value < -0.3) expect(contact[frame]).toBeLessThan(0.1);
    });
    expect(tapeTargetAt(y, 3250)).toBe(0);
    expect(tapeTargetAt(channel(roaming, 'bodySupport'), 3250)).toBe(1);
    expect(tapeTargetAt(channel(roaming, 'bodySx'), 4600)).toBe(1);
    expect(samples(channel(roaming, 'bodyRoll')).every(value => value === 0)).toBe(true);
    expect(extremes(channel(roaming, 'bodyX')).min).toBeLessThan(-0.6);
    expect(extremes(channel(mirrored, 'bodyX')).max).toBeGreaterThan(0.6);
    expect(extremes(channel(local, 'bodyX')).min).toBeGreaterThanOrEqual(-0.45);
    expect(extremes(channel(local, 'bodyY')).min).toBeGreaterThanOrEqual(-0.45);
  });

  it('does not fake lift or release support with no headroom', () => {
    const top: BodyMotionSpace = { minX: -2, maxX: 2, minY: 0, maxY: 4, roaming: true };
    const tapes = bodySketchTapes('body-balloon', top, () => 0.2);
    for (const axis of ['bodyX', 'bodyY'] as const)
      expect(samples(channel(tapes, axis)).every(value => value === 0)).toBe(true);
    expect(samples(channel(tapes, 'bodySupport')).every(value => value === 1)).toBe(true);
    expect(tapes.find(tape => tape.channel === 'gazeX')?.keys.some(key => key.value !== 0)).toBe(
      true
    );
  });

  it('handles a tiny viewport without moving out of its zero room or collapsing into negative scale', () => {
    const space: BodyMotionSpace = { minX: 0, maxX: 0, minY: 0, maxY: 0, roaming: false };
    for (const name of BODY_SKETCHES) {
      const tapes = bodySketchTapes(name, space);
      expect(samples(channel(tapes, 'bodyX')).every(value => value === 0)).toBe(true);
      expect(samples(channel(tapes, 'bodyY')).every(value => value === 0)).toBe(true);
      expect(extremes(channel(tapes, 'bodySx')).min).toBeGreaterThan(0.35);
      expect(extremes(channel(tapes, 'bodySy')).min).toBeGreaterThan(0.35);
    }
  });

  it('plays through the native owner with paced travel and returns all five channels to rest', () => {
    for (const name of BODY_SKETCHES) {
      const rig = createEyeRig({
        initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      });
      rig.setBodySpace(ROOM);
      rig.playScene(name);
      expect(rig.isPerforming()).toBe(true);
      expect(rig.sketchClock().scene).toBe(name);
      let acting = 0;
      for (let time = 0; time < 7200; time += 16) {
        rig.step(16);
        const value = rig.values();
        expect(value.bodyX).toBeGreaterThanOrEqual(ROOM.minX - 0.001);
        expect(value.bodyX).toBeLessThanOrEqual(ROOM.maxX + 0.001);
        expect(value.bodyY).toBeGreaterThanOrEqual(ROOM.minY - 0.001);
        expect(value.bodyY).toBeLessThanOrEqual(ROOM.maxY + 0.001);
        acting = Math.max(
          acting,
          Math.abs(value.bodyRoll) / 10,
          Math.abs(value.headPitch),
          Math.abs(value.bodyY)
        );
      }
      expect(acting).toBeGreaterThan(0.2);
      expect(rig.isPerforming()).toBe(false);
      for (const key of BODY_CHANNELS) {
        expect(rig.values()[key]).toBeCloseTo(CHANNELS[key].rest, 2);
      }
    }
  });
});
