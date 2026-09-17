/**
 * Sketches — the little scenes, and the three fences around them.
 *
 *  - each scene is a PIECE: three to five seconds, on the channels the rig
 *    owns and never on the lids or the silhouette, and the face is exactly
 *    where it was when the curtain falls;
 *  - the rig plays them RARELY and only on a resting face, from its own
 *    entropy stream, never two at once, with the face's own life stood aside;
 *  - a scene never outlives its state: a one-shot beat still wins over it,
 *    and an expression change drops it on the spot.
 */

import { describe, it, expect } from 'vitest';

import {
  createSketchClock,
  drawFirstSketchDelayMs,
  drawSketchDelayMs,
  HEAD_FOLLOW_X_EM,
  pickSketch,
  SKETCH_EXPRESSIONS,
  SKETCH_FIRST_MAX_DELAY_MS,
  SKETCH_FIRST_MIN_DELAY_MS,
  SKETCH_HISTORY,
  SKETCH_MAX_DELAY_MS,
  SKETCH_MAX_MS,
  SKETCH_MIN_DELAY_MS,
  SKETCH_MIN_MS,
  SKETCHES,
  sketchDurationMs,
  sketchTapes,
  type SketchName,
} from '@/components/eyes/rig/sketches';
import { createLifeRandom } from '@/components/eyes/rig/life';
import { blinkTapes } from '@/components/eyes/rig/gestures';
import { CHANNEL_KEYS, CHANNELS, isDerived } from '@/components/eyes/rig/channels';
import { resolvePose } from '@/components/eyes/rig/poses';
import { createEyeRig, type EyeRig } from '@/components/eyes/rig/runtime';
import { tapeDurationMs } from '@/components/eyes/rig/tape';
import { EYE_EXPRESSIONS } from '@/components/eyes/expression-engine';

function run(rig: EyeRig, ms: number, onFrame?: (values: ReturnType<EyeRig['values']>) => void) {
  for (let frame = 0; frame < Math.round(ms / 16); frame += 1) {
    rig.step(16);
    onFrame?.(rig.values());
  }
}

function sequence(values: readonly number[]): () => number {
  let index = 0;
  return () => values[index++ % values.length];
}

/** The scene on right now — the clock records it as it starts. */
function currentScene(rig: EyeRig): SketchName {
  const recent = rig.sketchClock().recent;
  return recent[recent.length - 1];
}

/** Rig time at which the first scene starts within `ms`, or a failure. */
function firstOnsetMs(rig: EyeRig, ms: number): number {
  let onset = -1;
  let clock = 0;
  run(rig, ms, () => {
    clock += 16;
    if (onset < 0 && rig.isPerforming()) onset = clock;
  });
  if (onset < 0) throw new Error(`no scene started within ${ms} ms`);
  return onset;
}

describe('the catalogue', () => {
  it('holds ten scenes, each three to five seconds long', () => {
    expect(SKETCHES).toHaveLength(10);
    SKETCHES.forEach(name => {
      const duration = sketchDurationMs(sketchTapes(name));
      expect({ name, inRange: duration >= SKETCH_MIN_MS && duration <= SKETCH_MAX_MS }).toEqual({
        name,
        inRange: true,
      });
    });
  });

  it('acts on the channels the rig owns — never the lids, never the silhouette', () => {
    // A relative lid tape on a style that folds its lids into a squash would
    // clip a ring (the documented ADR-252 trap); a radius is the style's
    // identity. Closing is a blink, narrowing is a squash.
    const forbidden = /^(lid|r[A-Z]|rv|baseRot|glow|pupil|stretch)/;
    SKETCHES.forEach(name =>
      sketchTapes(name).forEach(tape => {
        expect({ name, channel: tape.channel, known: tape.channel in CHANNELS }).toEqual({
          name,
          channel: tape.channel,
          known: true,
        });
        expect({ name, channel: tape.channel, allowed: !forbidden.test(tape.channel) }).toEqual({
          name,
          channel: tape.channel,
          allowed: true,
        });
      })
    );
  });

  it('commits the whole face: every scene moves the gaze or the eye shapes, the brows, the mouth', () => {
    SKETCHES.forEach(name => {
      const bases = new Set(sketchTapes(name).map(tape => tape.channel.replace(/[LR]$/, '')));
      expect({ name, eyes: bases.has('gazeX') || bases.has('sy') || bases.has('blink') }).toEqual({
        name,
        eyes: true,
      });
      expect({ name, brows: [...bases].some(base => base.startsWith('brow')) }).toEqual({
        name,
        brows: true,
      });
      expect({ name, mouth: [...bases].some(base => base.startsWith('mouth')) }).toEqual({
        name,
        mouth: true,
      });
    });
  });

  it('brings every ABSOLUTE tape back to rest before it ends — the gaze comes home, the lids reopen', () => {
    SKETCHES.forEach(name =>
      sketchTapes(name)
        .filter(tape => !tape.relative)
        .forEach(tape => {
          const rest = CHANNELS[tape.channel].rest;
          const lastOnChannel = sketchTapes(name)
            .filter(other => other.channel === tape.channel && !other.relative)
            .sort((a, b) => tapeDurationMs(b) - tapeDurationMs(a))[0];
          // Only the last tape on a channel has to land on rest: earlier ones
          // are overridden by later cues.
          if (lastOnChannel !== tape) return;
          expect({
            name,
            channel: tape.channel,
            last: tape.keys[tape.keys.length - 1].value,
          }).toEqual({ name, channel: tape.channel, last: rest });
        })
    );
  });

  it('leaves the face exactly where it was when the curtain falls', () => {
    // A twin rig without the scene, stepped the same time, is the oracle:
    // breath and drift included, every published channel agrees within a
    // hundredth one second after the longest tape has ended.
    SKETCHES.forEach(name => {
      const tapes = sketchTapes(name);
      const settleMs = sketchDurationMs(tapes) + 1600;
      const acting = createEyeRig({
        initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      });
      const twin = createEyeRig({
        initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      });
      acting.playSketch(tapes);
      run(acting, settleMs);
      run(twin, settleMs);
      const away = CHANNEL_KEYS.filter(
        key => !isDerived(key) && Math.abs(acting.values()[key] - twin.values()[key]) > 0.01
      );
      expect({ name, away }).toEqual({ name, away: [] });
    });
  });

  it('is READABLE: the fly is chased across the whole gaze, the sneeze squashes, the doze droops', () => {
    const trace = (name: (typeof SKETCHES)[number], key: 'gazeX' | 'mass' | 'syL' | 'blinkL') => {
      const rig = createEyeRig({
        initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      });
      rig.playSketch(sketchTapes(name));
      const values: number[] = [];
      run(rig, sketchDurationMs(sketchTapes(name)), v => values.push(v[key]));
      return values;
    };
    const fly = trace('fly', 'gazeX');
    expect(Math.max(...fly)).toBeGreaterThan(0.6);
    expect(Math.min(...fly)).toBeLessThan(-0.6);
    expect(Math.min(...trace('sneeze', 'mass'))).toBeLessThan(0.93);
    expect(Math.min(...trace('doze-and-snap', 'syL'))).toBeLessThan(0.5);
    expect(Math.max(...trace('peekaboo', 'blinkL'))).toBeGreaterThan(0.9);
  });

  it('turns the HEAD with the gaze: a scene that looks aside carries the whole face along', () => {
    // Measured on the running widget (2026-09-17): the gaze alone travels
    // 0.14 em per unit, six pixels at the large size, and a scene that lived
    // in it read as one more idle glance. The head follows on its own,
    // slower spring: the eyes lead, the face turns after them.
    SKETCHES.filter(name => sketchTapes(name).some(tape => tape.channel === 'gazeX')).forEach(
      name => {
        const tapes = sketchTapes(name);
        const gaze = tapes.filter(tape => tape.channel === 'gazeX');
        const head = tapes.filter(tape => tape.channel === 'massX');
        expect({ name, headTapes: head.length }).toEqual({ name, headTapes: gaze.length });
        gaze.forEach((tape, index) => {
          const follow = head[index];
          expect(follow.keys.map(key => key.atMs)).toEqual(tape.keys.map(key => key.atMs));
          follow.keys.forEach((key, at) => {
            expect(key.value).toBeCloseTo(tape.keys[at].value * HEAD_FOLLOW_X_EM, 6);
          });
        });
      }
    );
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
    });
    rig.playSketch(sketchTapes('suspicious'));
    let reach = 0;
    run(rig, 3000, values => {
      reach = Math.max(reach, Math.abs(values.massX));
    });
    expect(reach).toBeGreaterThan(HEAD_FOLLOW_X_EM * 0.5);
  });
});

describe('the scheduling', () => {
  it('spaces the scenes far apart — never a routine — and lets the first one come sooner', () => {
    expect(SKETCH_MIN_DELAY_MS).toBeGreaterThanOrEqual(40_000);
    expect(SKETCH_MAX_DELAY_MS).toBeLessThanOrEqual(150_000);
    expect(drawSketchDelayMs(() => 0)).toBe(SKETCH_MIN_DELAY_MS);
    expect(drawSketchDelayMs(() => 1)).toBe(SKETCH_MAX_DELAY_MS);
    // The first scene of a session is what proves the character is there:
    // it waits less, and still never lands on the first look at the face.
    expect(SKETCH_FIRST_MIN_DELAY_MS).toBeGreaterThanOrEqual(15_000);
    expect(SKETCH_FIRST_MAX_DELAY_MS).toBeLessThan(SKETCH_MIN_DELAY_MS);
    expect(drawFirstSketchDelayMs(() => 0)).toBe(SKETCH_FIRST_MIN_DELAY_MS);
    expect(drawFirstSketchDelayMs(() => 1)).toBe(SKETCH_FIRST_MAX_DELAY_MS);
  });

  it('reaches every scene from one random number', () => {
    const seen = new Set<string>();
    for (let r = 0; r < 1; r += 0.01) seen.add(pickSketch(() => r));
    expect([...seen].sort()).toEqual([...SKETCHES].sort());
  });

  it('never draws a scene it played recently', () => {
    const recent: SketchName[] = ['fly', 'sneeze', 'peekaboo'];
    expect(SKETCH_HISTORY).toBe(recent.length);
    const seen = new Set<string>();
    for (let r = 0; r < 1; r += 0.01) seen.add(pickSketch(() => r, recent));
    expect([...seen].sort()).toEqual(SKETCHES.filter(name => !recent.includes(name)).sort());
    // An exclusion list longer than the catalogue must never leave nothing.
    expect(SKETCHES).toContain(pickSketch(() => 0.5, [...SKETCHES]));
  });

  it('counts RESTING time only: a scene due during a thought is not lost, it waits', () => {
    // Draw order at construction: mouth life (2), then the first sketch
    // delay — 0 arms the shortest first wait (20 s of rest).
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      lifeRandom: sequence([0.5, 0.5, 0, 0.5, 0.5, 0.5]),
    });
    run(rig, 15_000);
    expect(rig.isPerforming()).toBe(false);
    // Five minutes of thinking: no scene (not a resting face), and the five
    // seconds still owed are still owed when the face comes back.
    rig.setPose({ expression: 'thinking', styleId: 'cozmo', family: 'calm' });
    let performed = false;
    run(rig, 5 * 60_000, () => {
      performed = performed || rig.isPerforming();
    });
    expect(performed).toBe(false);
    rig.setPose({ expression: 'neutral', styleId: 'cozmo', family: 'calm' });
    const onsetMs = firstOnsetMs(rig, 12_000);
    expect(onsetMs).toBeGreaterThan(4_000);
    expect(onsetMs).toBeLessThan(8_000);
  });

  it('keeps its clock across a remount: a second rig handed the same clock continues the wait', () => {
    const clock = createSketchClock();
    const first = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      lifeRandom: sequence([0.5, 0.5, 0, 0.5]),
      sketchClock: clock,
    });
    run(first, 15_000);
    expect(clock.dueMs).toBe(SKETCH_FIRST_MIN_DELAY_MS);
    expect(clock.restedMs).toBeGreaterThan(14_000);
    // The page navigates: the widget unmounts and mounts again on the same
    // document. Without the clock, the wait would start over from zero.
    const second = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      lifeRandom: sequence([0.5, 0.5, 0.5, 0.5]),
      sketchClock: clock,
    });
    expect(firstOnsetMs(second, 30_000)).toBeLessThan(7_000);
    expect(clock.played).toBe(1);
    expect(clock.recent).toHaveLength(1);
    // ...and the next wait is drawn from the LATER band.
    expect(clock.dueMs).toBeGreaterThanOrEqual(SKETCH_MIN_DELAY_MS);
  });

  it('plays every drawn scene WARPED: the same scene twice is never the same performance', () => {
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      lifeRandom: createLifeRandom(13),
    });
    const played: { name: SketchName; ms: number }[] = [];
    let was = false;
    let started = 0;
    let clock = 0;
    run(rig, 12 * 60_000, () => {
      clock += 16;
      const now = rig.isPerforming();
      if (now && !was) started = clock;
      if (!now && was) played.push({ name: currentScene(rig), ms: clock - started });
      was = now;
    });
    expect(played.length).toBeGreaterThanOrEqual(5);
    // Warped: a scene plays at its own catalogue length only by the
    // coincidence of a pace drawn within one 16 ms frame of 1 — at most
    // once in a dozen minutes — and the played lengths spread.
    const frame = (ms: number) => Math.ceil(ms / 16) * 16;
    const asWritten = played.filter(
      ({ name, ms }) => ms === frame(sketchDurationMs(sketchTapes(name)))
    );
    expect(asWritten.length).toBeLessThanOrEqual(1);
    expect(new Set(played.map(p => p.ms)).size).toBeGreaterThanOrEqual(
      Math.ceil(played.length * 0.7)
    );
  });

  it('remembers the last scenes on its clock and never repeats one of them', () => {
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      lifeRandom: createLifeRandom(11),
    });
    const names: SketchName[] = [];
    let was = false;
    run(rig, 30 * 60_000, () => {
      const now = rig.isPerforming();
      if (now && !was) names.push(currentScene(rig));
      was = now;
    });
    expect(names.length).toBeGreaterThanOrEqual(12);
    const repeats = names.filter((name, index) =>
      names.slice(Math.max(0, index - SKETCH_HISTORY), index).includes(name)
    );
    expect(repeats).toEqual([]);
    expect(rig.sketchClock().recent.length).toBeLessThanOrEqual(SKETCH_HISTORY);
  });

  it('never plays without an entropy source', () => {
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
    });
    let performing = false;
    run(rig, 10 * 60_000, () => {
      performing = performing || rig.isPerforming();
    });
    expect(performing).toBe(false);
  });

  it('plays a handful of scenes over ten resting minutes, at irregular intervals', () => {
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      lifeRandom: createLifeRandom(3),
    });
    const onsets: number[] = [];
    let was = false;
    let clock = 0;
    run(rig, 10 * 60_000, () => {
      clock += 16;
      const now = rig.isPerforming();
      if (now && !was) onsets.push(clock);
      was = now;
    });
    expect(onsets.length).toBeGreaterThanOrEqual(4);
    expect(onsets.length).toBeLessThanOrEqual(15);
    expect(onsets[0]).toBeGreaterThanOrEqual(SKETCH_FIRST_MIN_DELAY_MS);
    expect(onsets[0]).toBeLessThanOrEqual(SKETCH_FIRST_MAX_DELAY_MS + 100);
    const gaps = onsets.slice(1).map((at, index) => at - onsets[index]);
    gaps.forEach(gap => expect(gap).toBeGreaterThanOrEqual(SKETCH_MIN_DELAY_MS));
    expect(new Set(gaps).size).toBe(gaps.length);
  });

  it('only ever interrupts a resting face', () => {
    EYE_EXPRESSIONS.filter(expression => !SKETCH_EXPRESSIONS.has(expression)).forEach(
      expression => {
        const rig = createEyeRig({
          initial: { expression, styleId: 'cozmo', family: 'calm' },
          lifeRandom: createLifeRandom(5),
        });
        let performing = false;
        run(rig, 6 * 60_000, () => {
          performing = performing || rig.isPerforming();
        });
        expect({ expression, performing }).toEqual({ expression, performing: false });
      }
    );
    expect(SKETCH_EXPRESSIONS.has('thinking')).toBe(false);
  });

  it('stands the mouth own life aside while a scene is on', () => {
    // A mimic due mid-scene is pushed past the end of the scene plus a
    // breath: nothing but the sketch touches the mouth while it plays.
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      lifeRandom: sequence([0.5, 0.5, 0.5, 0.5, 0.5]),
    });
    const scene = sketchTapes('suspicious'); // a scene that never opens the mouth wide
    rig.playSketch(scene);
    let opened = 0;
    run(rig, sketchDurationMs(scene) + 2000, values => {
      opened = Math.max(opened, values.mouthOpen);
    });
    // The mimic scheduled at mount (0.5 → ~10 s) could not fire during the
    // scene; whatever it does afterwards, the scene's own mouth stayed shut.
    expect(opened).toBeLessThan(0.05);
  });

  it('honours reduced motion outright', () => {
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      lifeRandom: createLifeRandom(3),
      reducedMotion: true,
    });
    rig.playSketch(sketchTapes('fly'));
    run(rig, 3000);
    expect(rig.isPerforming()).toBe(false);
    expect(rig.values().gazeX).toBe(0);
  });
});

describe('the scene and the state', () => {
  it('lets a one-shot blink through the scene', () => {
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
    });
    rig.playSketch(sketchTapes('suspicious'));
    run(rig, 1000);
    rig.play(...blinkTapes());
    let closure = 0;
    run(rig, 200, values => {
      closure = Math.max(closure, values.blinkL);
    });
    expect(closure).toBeGreaterThan(0.7);
  });

  it('drops the scene the moment the expression changes, and the gaze comes home', () => {
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
    });
    rig.playSketch(sketchTapes('fly'));
    run(rig, 1200);
    expect(rig.isPerforming()).toBe(true);
    expect(Math.abs(rig.values().gazeX)).toBeGreaterThan(0.1);
    rig.setPose({ expression: 'attentive', styleId: 'cozmo', family: 'calm' });
    expect(rig.isPerforming()).toBe(false);
    run(rig, 1500);
    expect(Math.abs(rig.values().gazeX)).toBeLessThan(0.08);
    expect(rig.values().tilt).toBeCloseTo(0, 1);
  });

  it('is replaced, not stacked, by a second scene', () => {
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
    });
    rig.playSketch(sketchTapes('fly'));
    run(rig, 800);
    rig.playSketch(sketchTapes('peekaboo'));
    run(rig, 200);
    // Peekaboo shuts the eyes at once; the fly's gaze zigzag is gone.
    expect(rig.values().blinkL).toBeGreaterThan(0.5);
  });

  it('is settled away with everything else', () => {
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
    });
    rig.playSketch(sketchTapes('dizzy'));
    run(rig, 600);
    rig.settle();
    expect(rig.isPerforming()).toBe(false);
    expect(resolvePose('neutral', 'cozmo').gazeX).toBe(0);
  });
});
