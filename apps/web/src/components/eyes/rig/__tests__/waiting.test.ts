/**
 * The wait — the most watched moment of the face, and the least varied.
 *
 * Measured on thirty days of production (2026-11-11): a turn lasts 25 to 29
 * seconds at the median, and the face spent them on ONE pattern per tool
 * family, the family "reading" being three waits in four. Two rules here:
 *
 *  - a face that reads, READS: fixations walking a line, a quick return, the
 *    next line a little lower, then the eyes up from the page;
 *  - a face that thinks changes its attitude each time it thinks again, and
 *    starts over with each new thought.
 *
 * The tapes are asked first (what is written), then the rig that plays them
 * (what a viewer sees).
 */

import { describe, expect, it } from 'vitest';

import { NEUTRAL_CONTEXT, activityPattern, thoughtPattern } from '../direction';
import { createLifeRandom } from '../life';
import { createEyeRig, type EyeRig } from '../runtime';
import { tapeDurationMs, type Tape } from '../tape';

function tapeOn(tapes: readonly Tape[], channel: Tape['channel']): Tape {
  const tape = tapes.find(candidate => candidate.channel === channel);
  if (!tape) throw new Error(`no ${channel} tape`);
  return tape;
}

interface Line {
  /** Where the eyes rest along the line, in order. */
  stops: number[];
  /** How long each rest lasts, in milliseconds. */
  rests: number[];
  /** How low the line sits. */
  height: number;
}

/** A leftward jump this long is the return to the start of a line, never a
 * second look at a word. */
const RETURN_SWEEP = 0.4;

/** Split a reading tape into its lines, and what follows the last one. */
function readPage(tapes: readonly Tape[]): { lines: Line[]; lookUp: { x: number; y: number } } {
  const across = tapeOn(tapes, 'gazeX');
  const down = tapeOn(tapes, 'gazeY');
  const heightAt = (atMs: number) =>
    down.keys.reduce((height, key) => (key.atMs <= atMs ? key.value : height), down.keys[0].value);
  const lines: Line[] = [];
  const keys = across.keys;
  // The last key is the look up from the page.
  for (let index = 0; index < keys.length - 1; index += 1) {
    const key = keys[index];
    const previous = keys[index - 1];
    if (!previous || previous.value - key.value > RETURN_SWEEP)
      lines.push({ stops: [], rests: [], height: heightAt(key.atMs) });
    const line = lines[lines.length - 1];
    line.stops.push(key.value);
    line.rests.push(keys[index + 1].atMs - key.atMs);
  }
  const last = keys[keys.length - 1];
  return { lines, lookUp: { x: last.value, y: heightAt(last.atMs) } };
}

function run(rig: EyeRig, ms: number, each: (atMs: number) => void): void {
  for (let at = 16; at <= ms; at += 16) {
    rig.step(16);
    each(at);
  }
}

const SEEDS = Array.from({ length: 40 }, (_, index) => 11 + index * 97);

describe('a face that reads', () => {
  it('walks lines: short rests left to right, a quick return, the next line lower', () => {
    for (const seed of SEEDS) {
      const { lines } = readPage(activityPattern('reading', createLifeRandom(seed)));
      expect(lines.length, `seed ${seed}`).toBeGreaterThanOrEqual(2);
      expect(lines.length).toBeLessThanOrEqual(3);
      lines.forEach((line, index) => {
        expect(line.stops.length).toBeGreaterThanOrEqual(3);
        // A line starts on the left and ends on the right...
        expect(line.stops[0]).toBeLessThan(-0.25);
        expect(line.stops[line.stops.length - 1]).toBeGreaterThan(0.25);
        // ...going forward, but for one second look at a word at most.
        const backward = line.stops.filter((stop, at) => at > 0 && stop < line.stops[at - 1]);
        expect(backward.length).toBeLessThanOrEqual(1);
        // A rest is a fixation: longer than a blink of the gaze, shorter than a stare.
        line.rests.forEach(rest => {
          expect(rest).toBeGreaterThanOrEqual(200);
          expect(rest).toBeLessThanOrEqual(460);
        });
        // The page is below the eyes, and each line is lower than the last.
        expect(line.height).toBeGreaterThan(0.08);
        if (index > 0) expect(line.height - lines[index - 1].height).toBeGreaterThan(0.04);
      });
    }
  });

  it('keeps its head: the eyes travel a page, not the room', () => {
    for (const seed of SEEDS) {
      const across = tapeOn(activityPattern('reading', createLifeRandom(seed)), 'gazeX');
      // A search throws the gaze to 0.8 either side, and the head with it.
      across.keys.forEach(key => expect(Math.abs(key.value)).toBeLessThanOrEqual(0.5));
    }
  });

  it('bows the head to the page and keeps it there: only the eyes read', () => {
    // The head follows the gaze, which is right for a look and wrong for a
    // line: measured before this rule, twenty seconds of reading carried the
    // head over 13.3 units of yaw, against 5.2 for an exploration.
    const rig = createEyeRig({
      initial: { expression: 'searching', styleId: 'billes', family: 'calm' },
      lifeRandom: createLifeRandom(42),
    });
    rig.setContext({ ...NEUTRAL_CONTEXT, activity: 'reading', attending: true });
    let travel = 0;
    let widest = 0;
    let bowed = 0;
    let onThePage = 0;
    let previous = rig.values().headYaw;
    run(rig, 20_000, at => {
      const { headYaw, headPitch, gazeY } = rig.values();
      travel += Math.abs(headYaw - previous);
      previous = headYaw;
      if (at < 1000) return;
      widest = Math.max(widest, Math.abs(headYaw));
      if (gazeY > 0.06) {
        onThePage += 16;
        if (headPitch > 0.08) bowed += 16;
      }
    });
    expect(widest).toBeLessThan(0.08);
    expect(travel).toBeLessThan(1.5);
    expect(bowed).toBeGreaterThan(onThePage * 0.9);
  });

  it('looks up from the page before it reads on', () => {
    for (const seed of SEEDS) {
      const tapes = activityPattern('reading', createLifeRandom(seed));
      const { lines, lookUp } = readPage(tapes);
      const lastLine = lines[lines.length - 1];
      expect(lookUp.y).toBeLessThan(lastLine.height - 0.15);
      expect(Math.abs(lookUp.x)).toBeLessThan(0.2);
      // ...and holds that look, the time to take the page in.
      const across = tapeOn(tapes, 'gazeX');
      const held = tapeDurationMs(across) - across.keys[across.keys.length - 1].atMs;
      expect(held).toBeGreaterThanOrEqual(500);
      expect(held).toBeLessThanOrEqual(1200);
    }
  });

  it('never reads the same page twice', () => {
    const random = createLifeRandom(2026);
    const pages = Array.from({ length: 12 }, () =>
      JSON.stringify(tapeOn(activityPattern('reading', random), 'gazeX').keys)
    );
    expect(new Set(pages).size).toBe(pages.length);
  });

  it('leaves the other families their own look', () => {
    // A calculation is looked for in the air, up and to one side: held, not walked.
    const tapes = activityPattern('calculating', createLifeRandom(7));
    expect(tapeOn(tapes, 'gazeX').keys.length).toBeLessThanOrEqual(4);
    expect(Math.min(...tapeOn(tapes, 'gazeY').keys.map(key => key.value))).toBeLessThan(-0.2);
  });

  it('is what the rig plays while a reading tool runs, page after page', () => {
    const rig = createEyeRig({
      initial: { expression: 'searching', styleId: 'billes', family: 'calm' },
      lifeRandom: createLifeRandom(42),
    });
    rig.setContext({ ...NEUTRAL_CONTEXT, activity: 'reading', attending: true });
    let onThePage = 0;
    let forward = 0;
    let returns = 0;
    let previous = rig.values().gazeX;
    let travelling = 0;
    run(rig, 20_000, () => {
      const { gazeX, gazeY, mouthOpen } = rig.values();
      if (gazeY > 0.06) onThePage += 16;
      // A direction held for a few frames is a move, not the spring settling.
      const step = gazeX - previous;
      travelling = Math.sign(step) === Math.sign(travelling) ? travelling + step : step;
      if (travelling > 0.12) {
        forward += 1;
        travelling = 0;
      } else if (travelling < -0.45) {
        returns += 1;
        travelling = 0;
      }
      previous = gazeX;
      expect(Math.abs(gazeX)).toBeLessThan(0.6);
      expect(mouthOpen).toBeLessThan(0.03);
    });
    // Most of the time is spent on the page, moving along its lines...
    expect(onThePage).toBeGreaterThan(20_000 * 0.6);
    expect(forward).toBeGreaterThanOrEqual(20);
    // ...and line after line: several returns, on several pages.
    expect(returns).toBeGreaterThanOrEqual(6);
    expect(rig.sketchClock().played).toBe(0);
  });

  it('comes home the moment the reading ends', () => {
    const rig = createEyeRig({
      initial: { expression: 'searching', styleId: 'billes', family: 'calm' },
      lifeRandom: createLifeRandom(42),
    });
    rig.setContext({ ...NEUTRAL_CONTEXT, activity: 'reading', attending: true });
    run(rig, 3000, () => undefined);
    rig.setContext({ ...NEUTRAL_CONTEXT, attending: true });
    rig.setPose({ expression: 'attentive', styleId: 'billes', family: 'calm' });
    run(rig, 1500, () => undefined);
    expect(Math.abs(rig.values().gazeX)).toBeLessThan(0.03);
    expect(Math.abs(rig.values().gazeY)).toBeLessThan(0.03);
  });
});

type Attitude = 'up' | 'inward' | 'tilted';

/** What a thought looks like, read from what it moves. */
function attitudeOf(tapes: readonly Tape[]): Attitude {
  if (tapes.some(tape => tape.channel === 'tilt')) return 'tilted';
  const lowest = Math.max(...tapeOn(tapes, 'gazeY').keys.map(key => key.value));
  return lowest > 0.1 ? 'inward' : 'up';
}

describe('a face that thinks', () => {
  it('never holds the same attitude twice in a row, and has three of them', () => {
    const random = createLifeRandom(5);
    const attitudes = Array.from({ length: 9 }, (_, turn) =>
      attitudeOf(thoughtPattern(random, turn))
    );
    attitudes.forEach((attitude, turn) => {
      if (turn > 0) expect(attitude, `turn ${turn}`).not.toBe(attitudes[turn - 1]);
    });
    expect(new Set(attitudes)).toEqual(new Set<Attitude>(['up', 'inward', 'tilted']));
  });

  it('opens every thought on the same look: up and away', () => {
    expect(attitudeOf(thoughtPattern(createLifeRandom(1), 0))).toBe('up');
    // The call a rig makes when it knows of no earlier thought.
    expect(attitudeOf(thoughtPattern(createLifeRandom(1)))).toBe('up');
  });

  it('holds each attitude, quietly: a look, a consideration, a soft return', () => {
    for (const turn of [0, 1, 2]) {
      const tapes = thoughtPattern(createLifeRandom(31), turn);
      // No chewing, no blinking pattern: a thought moves the gaze, the head
      // and a brow, and nothing of the mouth.
      tapes.forEach(tape => expect(tape.channel).toMatch(/^(gazeX|gazeY|tilt|browY[LR])$/));
      const duration = Math.max(...tapes.map(tapeDurationMs));
      expect(duration).toBeGreaterThanOrEqual(6000);
      expect(duration).toBeLessThanOrEqual(11_500);
      // It ends where it started: the next attitude starts from rest.
      const across = tapeOn(tapes, 'gazeX');
      expect(across.keys[across.keys.length - 1].value).toBe(0);
      const tilt = tapes.find(tape => tape.channel === 'tilt');
      if (tilt) {
        expect(tilt.relative).toBe(true);
        expect(tilt.keys[tilt.keys.length - 1].value).toBe(0);
        expect(Math.max(...tilt.keys.map(key => Math.abs(key.value)))).toBeLessThanOrEqual(3);
      }
    }
  });

  it('is seen changing posture over a long wait, on the rig', () => {
    const rig = createEyeRig({
      initial: { expression: 'thinking', styleId: 'billes', family: 'calm' },
      lifeRandom: createLifeRandom(42),
    });
    rig.setContext({ ...NEUTRAL_CONTEXT, attending: true });
    const resting = rig.values().tilt;
    let lookedUp = false;
    let lookedInward = false;
    let leaned = 0;
    run(rig, 30_000, () => {
      const { gazeY, tilt, mouthOpen } = rig.values();
      lookedUp ||= gazeY < -0.15;
      lookedInward ||= gazeY > 0.12;
      leaned = Math.max(leaned, Math.abs(tilt - resting));
      expect(mouthOpen).toBeLessThan(0.03);
    });
    expect(lookedUp).toBe(true);
    expect(lookedInward).toBe(true);
    expect(leaned).toBeGreaterThan(1.5);
    expect(leaned).toBeLessThan(4);
  });

  it('starts over with each new thought', () => {
    const rig = createEyeRig({
      initial: { expression: 'thinking', styleId: 'billes', family: 'calm' },
      lifeRandom: createLifeRandom(42),
    });
    rig.setContext({ ...NEUTRAL_CONTEXT, attending: true });
    // Long enough to be past the first attitude.
    run(rig, 13_000, () => undefined);
    rig.setPose({ expression: 'attentive', styleId: 'billes', family: 'calm' });
    run(rig, 1000, () => undefined);
    rig.setPose({ expression: 'thinking', styleId: 'billes', family: 'calm' });
    let highest = 0;
    let lowest = 0;
    run(rig, 4000, () => {
      highest = Math.min(highest, rig.values().gazeY);
      lowest = Math.max(lowest, rig.values().gazeY);
    });
    expect(highest).toBeLessThan(-0.15);
    expect(lowest).toBeLessThan(0.08);
  });
});
