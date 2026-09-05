/**
 * The mouth's own life — random mimics at a random cadence, and the two
 * fences around them: they only exist with an entropy source, and they are
 * beats that return to the pose, on the resting expressions alone.
 *
 * Every test here drives the rig with an INJECTED sequence, so "random" is
 * exact: the cadence, the pick, the side and the size are all asserted.
 */

import { describe, it, expect } from 'vitest';

import {
  createLifeRandom,
  drawMouthLifeDelayMs,
  drawMouthMimic,
  mimicTapes,
  MOUTH_LIFE_BURST_DELAY_MS,
  MOUTH_LIFE_BURST_PROBABILITY,
  MOUTH_LIFE_EXPRESSIONS,
  MOUTH_LIFE_MAX_DELAY_MS,
  MOUTH_LIFE_MAX_MS,
  MOUTH_LIFE_MIN_DELAY_MS,
  MOUTH_MIMIC_WEIGHTS,
  MOUTH_MIMICS,
  pickMimic,
  scaleMimic,
} from '@/components/eyes/rig/life';
import { EYE_SQUASH_FLOOR, MOUTH_WIDTH_FLOOR } from '@/components/eyes/rig/runtime';
import { CHANNELS } from '@/components/eyes/rig/channels';
import { resolveLoops, resolvePose } from '@/components/eyes/rig/poses';
import { createEyeRig, type EyeRig } from '@/components/eyes/rig/runtime';
import { tapeDurationMs } from '@/components/eyes/rig/tape';
import { EYE_EXPRESSIONS, type EyeExpression } from '@/components/eyes/expression-engine';
import { faceMetrics, SIZE_PX, spread } from '@/components/eyes/rig/__tests__/screen';

/** A cycling entropy source: exact, and never the same draw twice in a row. */
function sequence(values: readonly number[]): () => number {
  let index = 0;
  return () => values[index++ % values.length];
}

function run(
  rig: EyeRig,
  seconds: number,
  onFrame?: (values: ReturnType<EyeRig['values']>) => void
) {
  for (let frame = 0; frame < Math.round((seconds * 1000) / 16); frame += 1) {
    rig.step(16);
    onFrame?.(rig.values());
  }
}

/** Onset times of mimics, read from the mouth curve leaving its hold band. */
function mimicOnsets(rig: EyeRig, seconds: number, expression: EyeExpression): number[] {
  const pose = resolvePose(expression, 'cozmo').mouthCurve;
  const hold = resolveLoops(expression, 'calm')
    .filter(loop => loop.channel === 'mouthCurve')
    .reduce((sum, loop) => sum + Math.abs(loop.amplitude), 0);
  const onsets: number[] = [];
  let clock = 0;
  run(rig, seconds, values => {
    clock += 16;
    const away = Math.abs(values.mouthCurve - pose) > hold + 0.06 || values.mouthOpen > 0.03;
    // A scene holds at most 1.2 s and eases home after: anything that far
    // from the pose within 1.7 s of an onset is the same performance (a
    // smack crosses the band twice), not a new one.
    if (away && (onsets.length === 0 || clock - onsets[onsets.length - 1] > 1700)) {
      onsets.push(clock);
    }
  });
  return onsets;
}

describe('the library', () => {
  it('holds nine mimics, every one a BEAT: relative, real channels, back to the pose, a scene long', () => {
    expect(MOUTH_MIMICS).toHaveLength(9);
    MOUTH_MIMICS.forEach(mimic => {
      ([1, -1] as const).forEach(side => {
        const tapes = mimicTapes(mimic, side);
        expect(tapes.length).toBeGreaterThan(0);
        tapes.forEach(tape => {
          expect({ mimic, channel: tape.channel, known: tape.channel in CHANNELS }).toEqual({
            mimic,
            channel: tape.channel,
            known: true,
          });
          expect({ mimic, channel: tape.channel, relative: tape.relative }).toEqual({
            mimic,
            channel: tape.channel,
            relative: true,
          });
          // The tape ENDS at its release: no key after the hold, the channel
          // is handed back to the pose there.
          expect({
            mimic,
            channel: tape.channel,
            endsAfterKeys: (tape.durationMs ?? 0) >= tape.keys[tape.keys.length - 1].atMs,
          }).toEqual({ mimic, channel: tape.channel, endsAfterKeys: true });
          expect({
            mimic,
            channel: tape.channel,
            short: tapeDurationMs(tape) <= MOUTH_LIFE_MAX_MS,
          }).toEqual({
            mimic,
            channel: tape.channel,
            short: true,
          });
        });
      });
    });
  });

  it('comes HOME on its own: two seconds after any scene, every channel is back on the pose', () => {
    MOUTH_MIMICS.forEach(mimic => {
      const rig = createEyeRig({
        initial: { expression: 'focused', styleId: 'cozmo', family: 'calm' },
      });
      const pose = resolvePose('focused', 'cozmo');
      rig.play(...mimicTapes(mimic, 1));
      run(rig, 3.2);
      const away = Object.keys(pose).filter(
        key =>
          !CHANNELS[key as keyof typeof CHANNELS].derived &&
          Math.abs(rig.values()[key as keyof typeof pose] - pose[key as keyof typeof pose]) > 0.01
      );
      expect({ mimic, away }).toEqual({ mimic, away: [] });
    });
  });

  it('lets go SLOWER than it came — the release is the expression dynamics, not the attack spring', () => {
    // A grin on a still face: time to the peak on the way in, time back to
    // the pose on the way out. The first version keyed the return on the
    // attack spring and snapped shut as fast as it had opened.
    const rig = createEyeRig({
      initial: { expression: 'focused', styleId: 'cozmo', family: 'calm' },
    });
    const pose = resolvePose('focused', 'cozmo').mouthCurve;
    const lead = mimicTapes('grin', 1).find(tape => tape.channel === 'mouthCurve')!;
    const releaseMs = tapeDurationMs(lead);
    rig.play(...mimicTapes('grin', 1));
    let clock = 0;
    let peakAt = 0;
    let peak = pose;
    let homeAt: number | null = null;
    run(rig, 3, values => {
      clock += 16;
      if (clock <= releaseMs && values.mouthCurve > peak) {
        peak = values.mouthCurve;
        peakAt = clock;
      }
      if (clock > releaseMs && homeAt === null && Math.abs(values.mouthCurve - pose) < 0.05) {
        homeAt = clock;
      }
    });
    expect(peak).toBeGreaterThan(pose + 0.6);
    // Under a third of a second to the top of the grin: quick, not snapped.
    expect(peakAt).toBeLessThanOrEqual(320);
    expect(homeAt).not.toBeNull();
    const releaseTook = homeAt! - releaseMs;
    expect(releaseTook).toBeGreaterThanOrEqual(250);
    expect(releaseTook).toBeLessThanOrEqual(1100);
    expect(releaseTook).toBeGreaterThan(peakAt - lead.keys[0].atMs);
  });

  it('commits the WHOLE face — mouth, brows, the eye shapes and the head — never the gaze or the lids', () => {
    // A cartoon face does not act with its mouth alone. But the gaze belongs
    // to the host (it aims), the lids and the blink state a fact, and the
    // silhouette radii are the style's identity: none of those is a mimic's.
    const allowed = /^(mouth|brow|sy|sx|ty|rot|tilt|mass)/;
    MOUTH_MIMICS.forEach(mimic =>
      mimicTapes(mimic, 1).forEach(tape =>
        expect({ mimic, channel: tape.channel, allowed: allowed.test(tape.channel) }).toEqual({
          mimic,
          channel: tape.channel,
          allowed: true,
        })
      )
    );
    const facial = (mimic: (typeof MOUTH_MIMICS)[number]) =>
      new Set(mimicTapes(mimic, 1).map(tape => tape.channel.replace(/[LR]$/, '')));
    // The big scenes reach the eyes; the small ones may stay on the mouth.
    (['grin', 'gasp', 'sulk', 'giggle', 'pucker', 'hmm', 'smirk'] as const).forEach(mimic =>
      expect({ mimic, eyes: facial(mimic).has('sy') }).toEqual({ mimic, eyes: true })
    );
  });

  it('is written as ATTACK, HOLD, RELEASE: the shape is reached fast and held long enough to be read', () => {
    // A shape that is not held is noise. Every big scene keeps its main
    // mouth channel at its peak for at least 350 ms before letting go.
    (['grin', 'gasp', 'sulk', 'hmm', 'smirk', 'pucker'] as const).forEach(mimic => {
      const lead = mimicTapes(mimic, 1).find(
        tape =>
          tape.channel === 'mouthCurve' || tape.channel === 'mouthOpen' || tape.channel === 'mouthW'
      )!;
      const peak = lead.keys.reduce((best, key) =>
        Math.abs(key.value) > Math.abs(best.value) ? key : best
      );
      // The release is where the tape ENDS.
      const releaseMs = tapeDurationMs(lead);
      expect({ mimic, heldMs: releaseMs - peak.atMs }).toEqual({
        mimic,
        heldMs: expect.any(Number),
      });
      expect(releaseMs - peak.atMs).toBeGreaterThanOrEqual(350);
      // ...and the attack is quick: the peak key sits inside 130 ms.
      expect(peak.atMs).toBeLessThanOrEqual(130);
    });
  });

  it('INKS the mouth and the brows while it plays — a face at half presence performing reads washed out', () => {
    MOUTH_MIMICS.forEach(mimic => {
      const tapes = mimicTapes(mimic, 1);
      const ink = tapes.filter(tape => ['mouthA', 'browAL', 'browAR'].includes(tape.channel));
      expect({ mimic, inked: ink.map(tape => tape.channel).sort() }).toEqual({
        mimic,
        inked: ['browAL', 'browAR', 'mouthA'],
      });
      const lead = tapes.find(
        tape => tape.channel.startsWith('mouth') && tape.channel !== 'mouthA'
      )!;
      const releaseMs = Math.max(...tapes.map(tapeDurationMs));
      ink.forEach(tape => {
        // The ink rises with the scene's own attack and is handed back with
        // the last of its tapes, fading on the slow aura dynamics.
        expect(tape.keys[0].atMs).toBe(lead.keys[0].atMs);
        expect(tape.keys[0].value).toBeGreaterThan(0.2);
        expect(tape.keys).toHaveLength(1);
        expect(tapeDurationMs(tape)).toBe(releaseMs);
        expect(tapeDurationMs(tape)).toBeLessThanOrEqual(MOUTH_LIFE_MAX_MS);
      });
    });
    // The big scenes commit in full from the resting half presence.
    const grinInk = mimicTapes('grin', 1).find(tape => tape.channel === 'mouthA')!;
    expect(grinInk.keys[0].value + CHANNELS.mouthA.rest).toBeGreaterThanOrEqual(1);
  });

  it('is BIG where the first version was polite: a grin reaches a full smile', () => {
    const grin = mimicTapes('grin', 1).find(tape => tape.channel === 'mouthCurve')!;
    expect(Math.max(...grin.keys.map(key => key.value))).toBeGreaterThanOrEqual(0.8);
    const gasp = mimicTapes('gasp', 1).find(tape => tape.channel === 'mouthOpen')!;
    expect(Math.max(...gasp.keys.map(key => key.value))).toBeGreaterThanOrEqual(0.5);
  });

  it('draws the big scenes rarer than the small ones, and every one is reachable', () => {
    const total = MOUTH_MIMIC_WEIGHTS.reduce((sum, [, weight]) => sum + weight, 0);
    expect(total).toBeCloseTo(1, 6);
    const big = new Set(['grin', 'gasp', 'sulk', 'giggle', 'pucker']);
    const bigShare = MOUTH_MIMIC_WEIGHTS.filter(([mimic]) => big.has(mimic)).reduce(
      (sum, [, weight]) => sum + weight,
      0
    );
    expect(bigShare).toBeLessThan(0.5);
    expect(bigShare).toBeGreaterThan(0.3);
    const seen = new Set<string>();
    for (let r = 0; r < 1; r += 0.005) seen.add(pickMimic(() => r));
    expect([...seen].sort()).toEqual([...MOUTH_MIMICS].sort());
  });

  it('mirrors the asymmetric mimics with the side, and leaves the symmetric ones alone', () => {
    const skewOf = (mimic: (typeof MOUTH_MIMICS)[number], side: 1 | -1) =>
      mimicTapes(mimic, side).find(tape => tape.channel === 'mouthSkew')?.keys[0].value ?? 0;
    expect(skewOf('smirk', 1)).toBe(-skewOf('smirk', -1));
    expect(skewOf('smirk', 1)).not.toBe(0);
    expect(mimicTapes('sulk', 1)).toEqual(mimicTapes('sulk', -1));
    // The narrowed eye and the raised brow swap sides with the corner.
    const narrowed = (side: 1 | -1) =>
      mimicTapes('smirk', side).find(tape => tape.channel.startsWith('sy'))!.channel;
    expect(narrowed(1)).toBe('syR');
    expect(narrowed(-1)).toBe('syL');
  });

  it('carries the brows where a face would — a grin lifts them, a sulk climbs their inner ends', () => {
    expect(mimicTapes('grin', 1).some(tape => tape.channel === 'browArcL')).toBe(true);
    const sulk = mimicTapes('sulk', 1).find(tape => tape.channel === 'browRotL')!;
    expect(sulk.keys[0].value).toBeLessThan(0);
    // ...and a grin squashes the eyes into happy arcs.
    const eyes = mimicTapes('grin', 1).find(tape => tape.channel === 'syL')!;
    expect(Math.min(...eyes.keys.map(key => key.value))).toBeLessThan(-0.3);
  });

  it('scales the whole performance, every key of every tape, and nothing else', () => {
    const scaled = scaleMimic(mimicTapes('gasp', 1), 1.2);
    const plain = mimicTapes('gasp', 1);
    scaled.forEach((tape, index) => {
      expect(tape.durationMs).toBe(plain[index].durationMs);
      tape.keys.forEach((key, at) => {
        expect(key.atMs).toBe(plain[index].keys[at].atMs);
        expect(key.value).toBeCloseTo(plain[index].keys[at].value * 1.2, 6);
      });
    });
  });
});

describe('the life stream', () => {
  it('is deterministic for a seed, in [0, 1), and differs between seeds', () => {
    const a = createLifeRandom(42);
    const b = createLifeRandom(42);
    const c = createLifeRandom(43);
    const first = Array.from({ length: 50 }, () => a());
    expect(first).toEqual(Array.from({ length: 50 }, () => b()));
    expect(first).not.toEqual(Array.from({ length: 50 }, () => c()));
    first.forEach(value => {
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThan(1);
    });
    // A zero seed must not lock the generator on zero forever.
    const zero = createLifeRandom(0);
    expect(new Set(Array.from({ length: 10 }, () => zero())).size).toBeGreaterThan(5);
  });
});

describe('the draw', () => {
  it('reaches every mimic from the first random number', () => {
    const seen = new Set<string>();
    for (let r = 0; r < 1; r += 0.005) seen.add(drawMouthMimic(sequence([r, 0.5, 0.5])).mimic);
    expect([...seen].sort()).toEqual([...MOUTH_MIMICS].sort());
  });

  it('draws the side from the second number and the size from the third', () => {
    // 0.7 lands on `smirk`, which has a corner to mirror.
    expect(pickMimic(() => 0.7)).toBe('smirk');
    const left = drawMouthMimic(sequence([0.7, 0.2, 0.5]));
    const right = drawMouthMimic(sequence([0.7, 0.8, 0.5]));
    expect(left.mimic).toBe(right.mimic);
    const skew = (draw: typeof left) =>
      draw.tapes.find(tape => tape.channel === 'mouthSkew')!.keys[0].value;
    expect(skew(left)).toBe(-skew(right));
    const small = drawMouthMimic(sequence([0.7, 0.2, 0]));
    const large = drawMouthMimic(sequence([0.7, 0.2, 1]));
    expect(Math.abs(skew(large))).toBeGreaterThan(Math.abs(skew(small)));
  });

  it('paces the cadence uniformly inside its band, with the occasional burst', () => {
    expect(drawMouthLifeDelayMs(sequence([0.99, 0]))).toBe(MOUTH_LIFE_MIN_DELAY_MS);
    expect(drawMouthLifeDelayMs(sequence([0.99, 1]))).toBe(MOUTH_LIFE_MAX_DELAY_MS);
    expect(drawMouthLifeDelayMs(sequence([MOUTH_LIFE_BURST_PROBABILITY / 2]))).toBe(
      MOUTH_LIFE_BURST_DELAY_MS
    );
    // A resting character's facial beat every eight to twelve seconds, the
    // eyes wandering in between — never the every-two-seconds that read as
    // nervous tics on the running widget.
    expect(MOUTH_LIFE_MIN_DELAY_MS).toBeGreaterThanOrEqual(5000);
    expect(MOUTH_LIFE_MAX_DELAY_MS).toBeLessThanOrEqual(16000);
    expect((MOUTH_LIFE_MIN_DELAY_MS + MOUTH_LIFE_MAX_DELAY_MS) / 2).toBeGreaterThanOrEqual(8000);
    expect(MOUTH_LIFE_BURST_DELAY_MS).toBeGreaterThanOrEqual(1500);
    expect(MOUTH_LIFE_BURST_PROBABILITY).toBeLessThanOrEqual(0.12);
  });

  it('plays between three and nine scenes a minute over five minutes of rest', () => {
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      lifeRandom: createLifeRandom(11),
    });
    const onsets = mimicOnsets(rig, 300, 'neutral');
    expect(onsets.length).toBeGreaterThanOrEqual(15);
    expect(onsets.length).toBeLessThanOrEqual(45);
  });
});

describe('in the rig', () => {
  it('never plays WITHOUT an entropy source — the moving hold stays what it was', () => {
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
    });
    expect(mimicOnsets(rig, 60, 'neutral')).toEqual([]);
  });

  it('plays mimics on a resting face, at an irregular cadence, and comes back between them', () => {
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      lifeRandom: createLifeRandom(7),
    });
    const onsets = mimicOnsets(rig, 180, 'neutral');
    expect(onsets.length).toBeGreaterThanOrEqual(10);
    const gaps = onsets.slice(1).map((at, index) => at - onsets[index]);
    expect(new Set(gaps).size).toBeGreaterThan(gaps.length / 2);
    // An onset is read a few frames after the tape starts, so a follow-up at
    // the burst delay can be detected a little under it.
    gaps.forEach(gap => expect(gap).toBeGreaterThanOrEqual(MOUTH_LIFE_BURST_DELAY_MS - 200));
  });

  it('is BIG where the hold is small: a grin is a mouth several pixels tall and eyes squashed to arcs', () => {
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      // Draw order: at construction the mouth life (burst roll, delay) then
      // the sketch life (delay); at the tick the NEXT mouth delay (burst roll,
      // delay), then the mimic (pick, side, size). 0 on the pick is a grin.
      lifeRandom: sequence([0.5, 0.5, 0.99, 0.99, 0.5, 0, 0.5, 0.5]),
    });
    const heights: number[] = [];
    let squash = 1;
    run(rig, 12, values => {
      heights.push(faceMetrics(values, SIZE_PX.md).mouthHeight);
      squash = Math.min(squash, values.syL);
    });
    // At the medium size the resting bar is 3 px; the grin adds seven more.
    expect(spread(heights)).toBeGreaterThan(6);
    expect(squash).toBeLessThan(0.7);
  });

  it('keeps every drawn performance inside what the mouth can draw', () => {
    const rig = createEyeRig({
      initial: { expression: 'joy', styleId: 'cozmo', family: 'lively' },
      lifeRandom: sequence([0.99, 0.99, 0.999, 0.5, 0.99, 0.01, 0.6, 0.45, 0.2, 0.8]),
    });
    run(rig, 90, values => {
      expect(values.mouthArc).toBeLessThanOrEqual(1);
      expect(values.mouthOpen).toBeGreaterThanOrEqual(0);
      expect(values.mouthOpen).toBeLessThanOrEqual(1);
      expect(values.mouthW).toBeGreaterThanOrEqual(MOUTH_WIDTH_FLOOR);
      expect(values.mouthW).toBeLessThan(1.7);
      // A grin on a joy dome closes the eyes to the happy-arc floor, never past.
      expect(values.syL).toBeGreaterThanOrEqual(EYE_SQUASH_FLOOR);
    });
  });

  it('leaves alone every expression that does not breathe', () => {
    EYE_EXPRESSIONS.filter(expression => !MOUTH_LIFE_EXPRESSIONS.has(expression)).forEach(
      expression => {
        const rig = createEyeRig({
          initial: { expression, styleId: 'cozmo', family: 'calm' },
          lifeRandom: sequence([0.5, 0.5, 0.5]),
        });
        const pose = resolvePose(expression, 'cozmo');
        let moved = false;
        run(rig, 30, values => {
          // Speaking flaps and sleep breathes through the mouth on purpose; a
          // mimic would show as the CURVE leaving the pose, which neither does.
          if (Math.abs(values.mouthCurve - pose.mouthCurve) > 0.2) moved = true;
        });
        expect({ expression, moved }).toEqual({ expression, moved: false });
      }
    );
  });

  it('starts over with a new expression, so a mimic never lands on an entrance', () => {
    // Draw order: [no burst, delay just past the minimum] then [a far sketch]
    // at construction; [no burst, a long delay] at the pose change; then
    // [next delay: no burst, long] before [`gasp`, side, size]
    // for the first mimic that does play. A gasp is a mimic an arrival to
    // `bored` can never be mistaken for: it OPENS the mouth.
    expect(pickMimic(() => 0.18)).toBe('gasp');
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      // ...then, when it plays: [next delay: no burst, long] before [pick, side, size].
      lifeRandom: sequence([0.99, 0.02, 0.99, 0.99, 0.9, 0.99, 0.5, 0.18, 0.5, 0.5]),
    });
    run(rig, 2);
    rig.setPose({ expression: 'bored', styleId: 'cozmo', family: 'calm' });
    // The pending mimic was due 4.2 s from here; the new state pushed it out
    // by a fresh, long delay instead, so the mouth stays shut well past it.
    let opened = 0;
    run(rig, 8, values => {
      opened = Math.max(opened, values.mouthOpen);
    });
    expect(opened).toBe(0);
    // ...and the life does go on afterwards.
    run(rig, 8, values => {
      opened = Math.max(opened, values.mouthOpen);
    });
    expect(opened).toBeGreaterThan(0.05);
  });

  it('honours reduced motion outright', () => {
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      lifeRandom: sequence([0.5, 0.5, 0.5]),
      reducedMotion: true,
    });
    run(rig, 30);
    expect(rig.values().mouthCurve).toBe(resolvePose('neutral', 'cozmo').mouthCurve);
  });
});
