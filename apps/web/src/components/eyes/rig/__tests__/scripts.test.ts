/**
 * Scripts — the entrance each emotion makes, and the behaviour a state keeps.
 *
 * These are the tests that answer "does it read as alive?" with something
 * other than an opinion:
 *
 *  - a SEARCH must be saccadic. A sine sweep and a saccade both move the eyes
 *    left and right; only one of them has the spiky velocity profile of a
 *    real search, and that is measurable.
 *  - an ARRIVAL must be specific. Anger inhales before it strikes, sadness
 *    only ever sinks, a question tips its head. A face where every emotion
 *    lands on the same curve is a face reciting labels.
 */

import { describe, it, expect } from 'vitest';
import { ARRIVAL_SCRIPTS, resolvePatterns } from '@/components/eyes/rig/scripts';
import { createEyeRig, type EyeRig } from '@/components/eyes/rig/runtime';
import { blinkTapes } from '@/components/eyes/rig/gestures';
import { resolvePose } from '@/components/eyes/rig/poses';
import { CHANNELS, type ChannelKey } from '@/components/eyes/rig/channels';
import { tapeDurationMs } from '@/components/eyes/rig/tape';
import { EYE_EXPRESSIONS, type EyeExpression } from '@/components/eyes/expression-engine';

const FRAME_MS = 16;

function trace(rig: EyeRig, channel: ChannelKey, frames: number): number[] {
  const values: number[] = [];
  for (let index = 0; index < frames; index += 1) {
    rig.step(FRAME_MS);
    values.push(rig.values()[channel]);
  }
  return values;
}

function searchingRig(): EyeRig {
  const rig = createEyeRig();
  rig.setPose({ expression: 'searching', styleId: 'cozmo', family: 'calm' });
  return rig;
}

/** Frame-to-frame movement, which is what separates a jump from a glide. */
function frameDeltas(values: readonly number[]): number[] {
  return values.slice(1).map((value, index) => Math.abs(value - values[index]));
}

function median(values: readonly number[]): number {
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.floor(sorted.length / 2)];
}

describe('the search pattern', () => {
  it('moves both axes on the SAME beats — a saccade is one movement', () => {
    const [x, y] = resolvePatterns('searching');
    expect(x.channel).toBe('gazeX');
    expect(y.channel).toBe('gazeY');
    expect(x.keys.map(key => key.atMs)).toEqual(y.keys.map(key => key.atMs));
  });

  it('never fixates on a beat: the intervals are irregular', () => {
    const [x] = resolvePatterns('searching');
    const gaps = x.keys.slice(1).map((key, index) => key.atMs - x.keys[index].atMs);
    expect(new Set(gaps).size).toBeGreaterThan(gaps.length / 2);
  });

  it('never lands twice in the same place in a row', () => {
    resolvePatterns('searching').forEach(tape => {
      tape.keys.slice(1).forEach((key, index) => {
        expect(key.value).not.toBe(tape.keys[index].value);
      });
    });
  });

  it('JUMPS and HOLDS — the velocity profile of a search, not of a sweep', () => {
    // The distinguishing measurement: a sine moves by a similar amount on
    // every frame (peak / median around 1.5), while a saccadic search barely
    // moves during a fixation and crosses the eye in a few frames. Anything
    // near a sine here means the windscreen wiper came back.
    const deltas = frameDeltas(trace(searchingRig(), 'gazeX', 170));
    const moving = deltas.filter(delta => delta > 1e-4);
    expect(Math.max(...deltas) / median(moving)).toBeGreaterThan(6);
  });

  it('actually reaches its fixations, left and right', () => {
    const values = trace(searchingRig(), 'gazeX', 170);
    expect(Math.min(...values)).toBeLessThan(-0.5);
    expect(Math.max(...values)).toBeGreaterThan(0.5);
  });

  it('searches with its whole gaze, not along a rail', () => {
    const vertical = trace(searchingRig(), 'gazeY', 170);
    expect(Math.max(...vertical) - Math.min(...vertical)).toBeGreaterThan(0.3);
  });

  it('LOOPS: the search does not stop after one cycle', () => {
    const rig = searchingRig();
    trace(rig, 'gazeX', 200);
    const second = trace(rig, 'gazeX', 170);
    expect(Math.max(...second) - Math.min(...second)).toBeGreaterThan(0.8);
    expect(rig.isAwake()).toBe(true);
  });

  it('is dropped the moment the state changes — a pattern never outlives it', () => {
    const rig = searchingRig();
    trace(rig, 'gazeX', 40);
    rig.setPose({ expression: 'neutral', styleId: 'cozmo', family: 'calm' });
    trace(rig, 'gazeX', 200);
    expect(Math.abs(rig.values().gazeX)).toBeLessThan(0.1);
  });

  it('lets a one-shot beat through: the eyes still blink while searching', () => {
    const rig = searchingRig();
    trace(rig, 'gazeX', 20);
    rig.play(...blinkTapes());
    const closure = trace(rig, 'blinkL', 10);
    expect(Math.max(...closure)).toBeGreaterThan(0.7);
  });

  it('gives no pattern to any expression that neither searches nor speaks', () => {
    EYE_EXPRESSIONS.filter(
      expression => expression !== 'searching' && expression !== 'speaking'
    ).forEach(expression => {
      expect(resolvePatterns(expression)).toHaveLength(0);
    });
  });
});

describe('the speech brows', () => {
  it('punctuate the speech: both brows, height and arch, the right one trailing', () => {
    const tapes = resolvePatterns('speaking');
    const channels = tapes.map(tape => tape.channel).sort();
    expect(channels).toEqual(['browArcL', 'browArcR', 'browYL', 'browYR']);
    tapes.forEach(tape => expect(tape.relative).toBe(true));
    const left = tapes.find(tape => tape.channel === 'browYL')!;
    const right = tapes.find(tape => tape.channel === 'browYR')!;
    expect(right.keys[0].atMs).toBeGreaterThan(left.keys[0].atMs);
  });

  it('never fall on a beat: the raises are irregularly spaced', () => {
    const left = resolvePatterns('speaking').find(tape => tape.channel === 'browYL')!;
    const raises = left.keys.filter(key => key.value < 0).map(key => key.atMs);
    expect(raises.length).toBeGreaterThanOrEqual(3);
    const gaps = raises.slice(1).map((at, index) => at - raises[index]);
    expect(new Set(gaps).size).toBe(gaps.length);
  });

  it('actually RAISE the brows several times per cycle, and hand them back between', () => {
    const rig = createEyeRig();
    rig.setPose({ expression: 'speaking', styleId: 'cozmo', family: 'calm' });
    const pose = resolvePose('speaking', 'cozmo').browYL;
    // Past the arrival, one full cycle of the pattern.
    trace(rig, 'browYL', 60);
    const cycle = trace(rig, 'browYL', 330);
    // Count the distinct dips below the pose: a raise is negative travel.
    let raises = 0;
    let inRaise = false;
    for (const value of cycle) {
      const raised = value < pose - 0.015;
      if (raised && !inRaise) raises += 1;
      inRaise = raised;
    }
    expect(raises).toBeGreaterThanOrEqual(3);
    // ...and between two raises the brow rests near its pose (the breath
    // aside — speaking does not breathe, so this is exact).
    expect(cycle.some(value => Math.abs(value - pose) < 0.004)).toBe(true);
  });

  it('are dropped the moment speaking ends', () => {
    const rig = createEyeRig();
    rig.setPose({ expression: 'speaking', styleId: 'cozmo', family: 'calm' });
    trace(rig, 'browYL', 40);
    rig.setPose({ expression: 'neutral', styleId: 'cozmo', family: 'calm' });
    expect(resolvePatterns('neutral')).toHaveLength(0);
    trace(rig, 'browYL', 200);
    expect(rig.isAwake()).toBe(true); // it breathes
    expect(Math.abs(rig.values().browYL)).toBeLessThan(0.02);
  });
});

describe('arrival choreography — brows and mouth', () => {
  it('SURPRISE flings the arch past its pose before it settles', () => {
    const rig = createEyeRig();
    rig.setPose({ expression: 'surprise', styleId: 'cozmo', family: 'calm' });
    const arc = trace(rig, 'browArcL', 30);
    expect(Math.max(...arc)).toBeGreaterThan(resolvePose('surprise', 'cozmo').browArcL + 0.05);
    trace(rig, 'browArcL', 200);
    expect(rig.values().browArcL).toBeCloseTo(resolvePose('surprise', 'cozmo').browArcL, 2);
  });

  it('SADNESS lets the brows sink AFTER the mass has fallen', () => {
    const sad = ARRIVAL_SCRIPTS.sad ?? [];
    const brows = sad.filter(tape => tape.channel.startsWith('browY'));
    const mass = sad.find(tape => tape.channel === 'mass')!;
    expect(brows).toHaveLength(2);
    brows.forEach(tape => {
      expect(tape.keys[0].atMs).toBeGreaterThan(mass.keys[0].atMs);
      // Sinking: positive travel is DOWN.
      expect(tape.keys[0].value).toBeGreaterThan(0);
    });
  });

  it('a QUESTION overshoots the one raised brow, not both', () => {
    const question = ARRIVAL_SCRIPTS.question ?? [];
    const brows = question.filter(tape => tape.channel.startsWith('browY'));
    expect(brows.map(tape => tape.channel)).toEqual(['browYL']);
    expect(brows[0].keys[0].value).toBeLessThan(0);
  });

  it('TIRED yawns: the mouth opens wide and closes again within the entrance', () => {
    const rig = createEyeRig();
    rig.setPose({ expression: 'tired', styleId: 'cozmo', family: 'calm' });
    const opening = trace(rig, 'mouthOpen', 90);
    expect(Math.max(...opening)).toBeGreaterThan(0.3);
    expect(rig.values().mouthOpen).toBeLessThan(0.06);
    // The pose itself has a closed mouth: the yawn was the entrance.
    expect(resolvePose('tired', 'cozmo').mouthOpen).toBe(0);
  });

  it('keeps every brow entrance RELATIVE — a beat never yanks a posed brow to a fixed height', () => {
    Object.values(ARRIVAL_SCRIPTS).forEach(tapes =>
      (tapes ?? [])
        .filter(tape => tape.channel.startsWith('brow'))
        .forEach(tape => expect(tape.relative).toBe(true))
    );
  });
});

describe('arrival choreography', () => {
  it('only ever targets real channels', () => {
    Object.values(ARRIVAL_SCRIPTS).forEach(tapes =>
      (tapes ?? []).forEach(tape => expect(CHANNELS[tape.channel]).toBeDefined())
    );
  });

  it('keeps every entrance an ENTRANCE — none outlives a second', () => {
    Object.entries(ARRIVAL_SCRIPTS).forEach(([expression, tapes]) => {
      (tapes ?? []).forEach(tape => {
        expect({ expression, long: tapeDurationMs(tape) > 1000 }).toEqual({
          expression,
          long: false,
        });
      });
    });
  });

  it('ANGER inhales before it strikes', () => {
    const rig = createEyeRig();
    rig.setPose({ expression: 'anger', styleId: 'cozmo', family: 'calm' });
    const mass = trace(rig, 'mass', 30);
    const peak = mass.indexOf(Math.max(...mass));
    const trough = mass.indexOf(Math.min(...mass));
    // It rises FIRST, then comes down: a scowl that simply appears is a state
    // change, not a temper.
    expect(Math.max(...mass)).toBeGreaterThan(1.01);
    expect(peak).toBeLessThan(trough);
  });

  it('SADNESS only ever sinks — it never bounces on the way in', () => {
    const rig = createEyeRig();
    rig.setPose({ expression: 'sad', styleId: 'cozmo', family: 'calm' });
    const mass = trace(rig, 'mass', 40);
    expect(Math.max(...mass)).toBeLessThanOrEqual(1.0001);
    expect(Math.min(...mass)).toBeLessThan(0.995);
  });

  it('FEAR recoils: it pulls up and away before it settles', () => {
    const rig = createEyeRig();
    rig.setPose({ expression: 'fear', styleId: 'cozmo', family: 'calm' });
    const lift = trace(rig, 'massY', 12);
    expect(Math.min(...lift)).toBeLessThan(-0.004);
  });

  it('a QUESTION tips its head, and a THOUGHT leans the other way', () => {
    const asking = createEyeRig();
    asking.setPose({ expression: 'question', styleId: 'cozmo', family: 'calm' });
    trace(asking, 'tilt', 20);
    expect(asking.values().tilt).toBeGreaterThan(1);

    const thinking = createEyeRig();
    thinking.setPose({ expression: 'thinking', styleId: 'cozmo', family: 'calm' });
    trace(thinking, 'tilt', 30);
    expect(thinking.values().tilt).toBeLessThan(-0.5);
  });

  it('returns the head to level once the entrance is over', () => {
    const rig = createEyeRig();
    rig.setPose({ expression: 'question', styleId: 'cozmo', family: 'calm' });
    trace(rig, 'tilt', 200);
    expect(rig.values().tilt).toBeCloseTo(0, 2);
  });

  it('moves the two brows apart in time — never as one bar', () => {
    const paired = (expression: EyeExpression) =>
      (ARRIVAL_SCRIPTS[expression] ?? []).filter(tape => tape.channel.startsWith('browY'));
    const brows = paired('anger');
    expect(brows).toHaveLength(2);
    expect(brows[0].keys[0].atMs).not.toBe(brows[1].keys[0].atMs);
    // ...and relative, so a brow beat never yanks a posed brow to a fixed height.
    expect(brows.every(tape => tape.relative)).toBe(true);
  });
});

describe('arrival pace', () => {
  it('is perfectly repeatable without an entropy source (what tests want)', () => {
    const land = () => {
      const rig = createEyeRig();
      rig.setPose({ expression: 'anger', styleId: 'cozmo', family: 'calm' });
      return trace(rig, 'syL', 12);
    };
    expect(land()).toEqual(land());
  });

  it('varies from one performance to the next when given one', () => {
    const land = (value: number) => {
      const rig = createEyeRig({ random: () => value });
      rig.setPose({ expression: 'anger', styleId: 'cozmo', family: 'calm' });
      return trace(rig, 'syL', 12);
    };
    // The same emotion, twice, is never quite the same speed.
    expect(land(0.05)).not.toEqual(land(0.95));
  });

  it('stays a nuance, never a wobble', () => {
    const settle = (value: number) => {
      const rig = createEyeRig({ random: () => value });
      rig.setPose({ expression: 'anger', styleId: 'cozmo', family: 'calm' });
      trace(rig, 'syL', 200);
      return rig.values().syL;
    };
    // Whatever the pace, the pose it lands on is identical.
    expect(settle(0)).toBeCloseTo(settle(1), 4);
  });
});

describe('reduced motion and patterns', () => {
  it('runs no search pattern at all while the preference is on', () => {
    const rig = createEyeRig({ reducedMotion: true });
    rig.setPose({ expression: 'searching', styleId: 'cozmo', family: 'calm' });
    const values = trace(rig, 'gazeX', 120);
    expect(Math.max(...values.map(Math.abs))).toBe(0);
    expect(rig.isAwake()).toBe(false);
  });

  it('restores it when the preference is switched back off', () => {
    // `settle` drops the patterns; without restoring them a search interrupted
    // by the preference would stay frozen until the next expression change.
    const rig = createEyeRig();
    rig.setPose({ expression: 'searching', styleId: 'cozmo', family: 'calm' });
    rig.setReducedMotion(true);
    rig.setReducedMotion(false);
    const values = trace(rig, 'gazeX', 170);
    expect(Math.max(...values) - Math.min(...values)).toBeGreaterThan(0.8);
  });
});
