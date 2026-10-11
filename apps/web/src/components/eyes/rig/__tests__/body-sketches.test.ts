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

const ROOM: BodyMotionSpace = { minX: -4, maxX: 3, minY: -3, maxY: 0.4, roaming: true };
const EDGE: BodyMotionSpace = { minX: -0.08, maxX: 0.02, minY: 0, maxY: 0.04, roaming: true };
const BODY_CHANNELS = ['bodyX', 'bodyY', 'bodyRoll', 'bodySx', 'bodySy'] as const;

function channel(tapes: Tape[], name: (typeof BODY_CHANNELS)[number]): Tape {
  const tape = tapes.find(candidate => candidate.channel === name);
  if (!tape) throw new Error(`missing ${name}`);
  return tape;
}

/** The actual analytic spring follows the planned targets, not a linear keyframe oracle. */
function samples(tape: Tape): number[] {
  let state = { value: tape.channel.startsWith('bodyS') ? 1 : 0, velocity: 0 };
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

function sequence(draws: readonly number[]): () => number {
  let index = 0;
  return () => draws[index++ % draws.length];
}

describe('whole-body scenes', () => {
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
  it('registers the eight acrobatics and a courteous bow on the existing catalogue and routes host entropy', () => {
    expect(BODY_SKETCHES).toEqual([
      'body-hops',
      'body-roll',
      'body-somersault',
      'body-doze',
      'body-sneeze',
      'body-balloon',
      'body-jig',
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

  it('lands and settles at its exact anchor, with complete revolutions handed to runtime normalization', () => {
    for (const name of BODY_SKETCHES) {
      const tapes = bodySketchTapes(name, ROOM);
      for (const axis of BODY_CHANNELS) {
        const tape = channel(tapes, axis);
        const rest = axis.startsWith('bodyS') ? 1 : 0;
        const home = tape.keys.at(-1)!.value;
        expect(axis === 'bodyRoll' ? home % 360 : home).toBe(rest);
        expect(tape.keys.at(-1)!.atMs).toBeLessThanOrEqual(sketchDurationMs(tapes) - 600);
        expect(Math.abs(samples(tape).at(-1)! - home)).toBeLessThan(0.01);
      }
    }
  });

  it('makes rolls and somersaults complete forward turns instead of undoing them to reach zero', () => {
    for (const name of ['body-roll', 'body-somersault'] satisfies BodySketchName[]) {
      for (const random of [() => 0.2, () => 0.8]) {
        const tape = channel(bodySketchTapes(name, ROOM, random), 'bodyRoll');
        const direction = Math.sign(tape.keys.at(-1)!.value);
        const committed = tape.keys
          .filter(key => key.atMs >= 500)
          .map(key => key.value * direction);
        expect(committed.at(-1)).toBe(360);
        expect(
          committed.every((value, index) => index === 0 || value >= committed[index - 1])
        ).toBe(true);
      }
    }
  });

  it('anticipates a hop, stretches in the air, then compresses on landing before settling', () => {
    const tapes = bodySketchTapes('body-hops', ROOM);
    expect(tapeTargetAt(channel(tapes, 'bodyY'), 200)).toBeGreaterThan(0);
    expect(tapeTargetAt(channel(tapes, 'bodyY'), 600)).toBeLessThan(-0.3);
    expect(tapeTargetAt(channel(tapes, 'bodySy'), 600)).toBeGreaterThan(1);
    expect(tapeTargetAt(channel(tapes, 'bodySy'), 1050)).toBeLessThan(1);
    expect(tapeTargetAt(channel(tapes, 'bodySy'), 3500)).toBe(1);
    // With no room above, the visible anticipation still falls then rebounds to the anchor.
    const edgeY = channel(bodySketchTapes('body-hops', EDGE), 'bodyY');
    expect(tapeTargetAt(edgeY, 200)).toBeGreaterThan(0);
    expect(tapeTargetAt(edgeY, 600)).toBe(0);
  });

  it('lies down long enough to read as sleep and reopens both eyes when it wakes', () => {
    const tapes = bodySketchTapes('body-doze', ROOM);
    expect(tapeTargetAt(channel(tapes, 'bodyRoll'), 2100)).toBe(90);
    expect(tapeTargetAt(channel(tapes, 'bodyRoll'), 3000)).toBe(90);
    for (const side of ['L', 'R']) {
      const blink = tapes.find(tape => tape.channel === `blink${side}`)!;
      expect(tapeTargetAt(blink, 2100)).toBe(1);
      expect(tapeTargetAt(blink, 3000)).toBe(1);
      expect(tapeTargetAt(blink, 4500)).toBe(0);
    }
  });

  it('makes a visible upward leap from a temporary lower floor when the widget starts at the top', () => {
    const top: BodyMotionSpace = { minX: -1, maxX: 1, minY: 0, maxY: 1.2, roaming: true };
    for (const name of [
      'body-hops',
      'body-somersault',
      'body-startle',
    ] satisfies BodySketchName[]) {
      const tape = channel(bodySketchTapes(name, top), 'bodyY');
      const values = samples(tape);
      expect(Math.max(...values)).toBeGreaterThan(0.45);
      expect(Math.min(...values)).toBeGreaterThanOrEqual(0);
      expect(values.at(-1)).toBeLessThan(0.001);
      const launch = tape.keys.find(key => key.atMs >= 300 && key.atMs <= 600)!;
      const preparation = tape.keys.find(key => key.atMs > 0 && key.atMs < 300)!;
      expect(preparation.value - launch.value).toBeGreaterThanOrEqual(0.55);
    }
  });

  it('deflates, flies through roaming space, returns home and reinflates; previews stay local', () => {
    const roaming = bodySketchTapes('body-balloon', ROOM, () => 0.2);
    const local = bodySketchTapes('body-balloon', { ...ROOM, roaming: false }, () => 0.2);
    expect(tapeTargetAt(channel(roaming, 'bodySx'), 800)).toBeLessThan(0.6);
    expect(tapeTargetAt(channel(roaming, 'bodySy'), 800)).toBeLessThan(0.6);
    expect(Math.max(...samples(channel(roaming, 'bodyX')).map(Math.abs))).toBeGreaterThan(1);
    expect(Math.max(...samples(channel(local, 'bodyX')).map(Math.abs))).toBeLessThanOrEqual(0.45);
    expect(Math.max(...samples(channel(local, 'bodyY')).map(Math.abs))).toBeLessThanOrEqual(0.45);
    expect(tapeTargetAt(channel(roaming, 'bodyX'), 3700)).toBe(0);
    expect(tapeTargetAt(channel(roaming, 'bodySx'), 3900)).toBeGreaterThan(1);
    expect(tapeTargetAt(channel(roaming, 'bodySx'), 4700)).toBe(1);
    expect(bodySketchTapes('body-balloon', ROOM, () => 0.8)).not.toEqual(roaming);
  });

  it('plans distinct seeded flight points even when the two balloons turn in the same direction', () => {
    const firstSeed = [0.2, 0.1, 0.25, 0.8, 0.7, 0.9, 0.2, 0.2, 0.9];
    const secondSeed = [0.2, 0.8, 0.7, 0.2, 0.3, 0.1, 0.8, 0.9, 0.1];
    const first = bodySketchTapes('body-balloon', ROOM, sequence(firstSeed));
    const second = bodySketchTapes('body-balloon', ROOM, sequence(secondSeed));
    expect(channel(first, 'bodyRoll').keys).toEqual(channel(second, 'bodyRoll').keys);
    for (const axis of ['bodyX', 'bodyY'] as const) {
      const firstPoints = channel(first, axis).keys.filter(
        key => key.atMs >= 900 && key.atMs < 3480
      );
      const secondPoints = channel(second, axis).keys.filter(
        key => key.atMs >= 900 && key.atMs < 3480
      );
      expect(firstPoints).toHaveLength(4);
      expect(firstPoints).not.toEqual(secondPoints);
      expect(firstPoints.map(key => Math.abs(key.value))).not.toEqual(
        secondPoints.map(key => Math.abs(key.value))
      );
    }
    expect(bodySketchTapes('body-balloon', ROOM, sequence(firstSeed))).toEqual(first);
  });

  it('flies into the room below a top-edge anchor and consumes entropy only when planning', () => {
    const top: BodyMotionSpace = { minX: -2, maxX: 2, minY: 0, maxY: 4, roaming: true };
    let draws = 0;
    const random = () => {
      draws += 1;
      return 0.2;
    };
    const tapes = bodySketchTapes('body-balloon', top, random);
    const plannedDraws = draws;
    const y = channel(tapes, 'bodyY');
    expect(tapeTargetAt(y, 400)).toBeGreaterThan(0);
    expect(tapeTargetAt(y, 1200)).toBeGreaterThan(0.6);
    expect(plannedDraws).toBeGreaterThan(4);
    const range = extremes(y);
    expect(range.min).toBeGreaterThanOrEqual(0);
    expect(range.max).toBeLessThanOrEqual(4);
    expect(tapeTargetAt(y, 3700)).toBe(0);
    expect(samples(y).at(-1)).toBeLessThan(0.001);
    expect(draws).toBe(plannedDraws);
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
        initial: { expression: 'neutral', styleId: 'smiley', family: 'calm' },
      });
      rig.setBodySpace(ROOM);
      rig.playScene(name);
      expect(rig.isPerforming()).toBe(true);
      expect(rig.sketchClock().scene).toBe(name);
      let deformation = 0;
      for (let time = 0; time < 7200; time += 16) {
        rig.step(16);
        const value = rig.values();
        expect(value.bodyX).toBeGreaterThanOrEqual(ROOM.minX - 0.001);
        expect(value.bodyX).toBeLessThanOrEqual(ROOM.maxX + 0.001);
        expect(value.bodyY).toBeGreaterThanOrEqual(ROOM.minY - 0.001);
        expect(value.bodyY).toBeLessThanOrEqual(ROOM.maxY + 0.001);
        deformation = Math.max(deformation, Math.abs(value.bodySx - 1), Math.abs(value.bodySy - 1));
      }
      expect(deformation).toBeGreaterThan(0.05);
      expect(rig.isPerforming()).toBe(false);
      for (const key of BODY_CHANNELS) {
        expect(rig.values()[key]).toBeCloseTo(key.startsWith('bodyS') ? 1 : 0, 2);
      }
    }
  });
});
