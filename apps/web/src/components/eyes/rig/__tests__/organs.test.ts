/**
 * The two organs — the brow and the pupil.
 *
 * Both were absent from the previous system: the "brow" was the eye's own
 * slant, and there was no pupil outside one style's decorative dot. They are
 * the largest single addition to the expressive range, so their GRAMMAR is
 * pinned here rather than left to twenty hand-written recipes:
 *
 *  - a brow tilt is mirrored between the eyes unless the asymmetry IS the
 *    message (a question, a thought, a wink);
 *  - lowered inner ends scowl, raised inner ends grieve — and every
 *    expression must land on the right side of that line;
 *  - a pupil constricts in fear and dilates in tenderness; it is SECONDARY
 *    action, so it moves after the face, never with it.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { POSES, resolvePose } from '@/components/eyes/rig/poses';
import { createEyeRig } from '@/components/eyes/rig/runtime';
import { CHANNELS } from '@/components/eyes/rig/channels';
import { GROUP_LEAD_MS } from '@/components/eyes/rig/dynamics';
import { EYE_EXPRESSIONS, type EyeExpression } from '@/components/eyes/expression-engine';

const CSS = readFileSync(join(process.cwd(), 'src/styles/eyes.css'), 'utf8');

/** Expressions whose asymmetry is deliberate — the whole point, in fact. */
const ASYMMETRIC: ReadonlySet<EyeExpression> = new Set(['question', 'thinking', 'wink']);

/** How much each eye's INNER end is lowered (positive) or raised (negative).
 * The two eyes mirror, so the right eye's angle is negated. */
function innerEndDrop(expression: EyeExpression): { left: number; right: number } {
  const pose = resolvePose(expression, 'cozmo');
  return { left: pose.browRotL, right: -pose.browRotR };
}

describe('the brow', () => {
  it('is absent from a neutral face, and from a sleeping one', () => {
    expect(resolvePose('neutral', 'cozmo').browAL).toBe(0);
    expect(resolvePose('sleep', 'cozmo').browAL).toBe(0);
  });

  it('shows up for every expression that has something to say', () => {
    const silent = EYE_EXPRESSIONS.filter(
      expression => resolvePose(expression, 'cozmo').browAL === 0
    );
    expect(silent).toEqual(['neutral', 'sleep']);
  });

  it('mirrors between the eyes, except where the asymmetry IS the message', () => {
    EYE_EXPRESSIONS.forEach(expression => {
      if (ASYMMETRIC.has(expression)) return;
      const pose = resolvePose(expression, 'cozmo');
      // `+ 0` normalises the negative zero a mirrored 0deg produces.
      expect({ expression, rot: pose.browRotL + 0 }).toEqual({
        expression,
        rot: -pose.browRotR + 0,
      });
      expect(pose.browYL).toBe(pose.browYR);
      expect(pose.browAL).toBe(pose.browAR);
    });
  });

  it('scowls by LOWERING the inner ends', () => {
    (['anger', 'focused', 'bored'] as const).forEach(expression => {
      const { left, right } = innerEndDrop(expression);
      expect({ expression, left: left > 0, right: right > 0 }).toEqual({
        expression,
        left: true,
        right: true,
      });
    });
  });

  it('grieves and worries by RAISING them', () => {
    (['sad', 'worried', 'fear', 'tender', 'tired'] as const).forEach(expression => {
      const { left, right } = innerEndDrop(expression);
      expect({ expression, left: left < 0, right: right < 0 }).toEqual({
        expression,
        left: true,
        right: true,
      });
    });
  });

  it('raises the whole brow highest for surprise — the reflex of the face', () => {
    const heights = EYE_EXPRESSIONS.map(expression => resolvePose(expression, 'cozmo').browYL);
    expect(resolvePose('surprise', 'cozmo').browYL).toBe(Math.min(...heights));
  });

  it('breaks the symmetry only ONE way for a question (one brow up)', () => {
    const question = resolvePose('question', 'cozmo');
    expect(question.browYL).toBeLessThan(question.browYR);
  });

  it('is never anticipated into an absent brow appearing backwards', () => {
    // Presence is `aura`: it FOLLOWS the face instead of anticipating it, so a
    // brow never flashes into view before the emotion that summons it.
    expect(CHANNELS.browAL.group).toBe('aura');
    expect(GROUP_LEAD_MS.aura).toBeGreaterThan(0);
    // Height and tilt are willed motion, so they anticipate and exaggerate.
    expect(CHANNELS.browYL.group).toBe('pose');
    expect(CHANNELS.browRotL.group).toBe('pose');
  });
});

describe('the pupil', () => {
  it('rests at its natural size', () => {
    expect(resolvePose('neutral', 'cozmo').pupilL).toBe(1);
  });

  it('pinpoints in fear and blows open in tenderness', () => {
    expect(resolvePose('fear', 'cozmo').pupilL).toBeLessThan(0.7);
    expect(resolvePose('tender', 'cozmo').pupilL).toBeGreaterThan(1.2);
    expect(resolvePose('surprise', 'cozmo').pupilL).toBeGreaterThan(1.2);
  });

  it('narrows for concentration and for anger', () => {
    expect(resolvePose('focused', 'cozmo').pupilL).toBeLessThan(1);
    expect(resolvePose('anger', 'cozmo').pupilL).toBeLessThan(1);
  });

  it('is SECONDARY action: it moves after the face, not with it', () => {
    const rig = createEyeRig();
    rig.setPose({ expression: 'fear', styleId: 'cozmo', family: 'calm' });
    rig.step(16);
    rig.step(16);
    // Two frames in, the face is already moving and the pupil has not begun.
    expect(rig.values().pupilL).toBe(1);
    expect(rig.values().sxL).not.toBe(1);
    for (let frame = 0; frame < 200; frame += 1) rig.step(16);
    expect(rig.values().pupilL).toBeCloseTo(0.55, 2);
  });

  it('never scales a pose declared without one', () => {
    expect(POSES.speaking.pupilL).toBeUndefined();
    expect(resolvePose('speaking', 'cozmo').pupilL).toBe(1);
  });
});

describe('per-style opt-in', () => {
  it('gates both organs on style tokens, not on hard-coded style lists', () => {
    expect(CSS).toContain('--has-brow');
    expect(CSS).toContain('--has-pupil');
    expect(CSS).toMatch(/opacity:\s*calc\(var\(--brow-a\)\s*\*\s*var\(--has-brow\)\)/);
    expect(CSS).toMatch(/opacity:\s*var\(--has-pupil\)/);
  });

  it('gives no brow to the stroke language — there, the stroke IS the brow', () => {
    const traits = CSS.slice(CSS.indexOf("[data-style='traits'] {"));
    expect(traits.slice(0, traits.indexOf('}'))).toContain('--has-brow: 0');
  });

  it('gives a pupil to the looks that have an inside', () => {
    ['billes', 'anneaux'].forEach(style => {
      const block = CSS.slice(CSS.indexOf(`[data-style='${style}'] {`));
      expect(block.slice(0, block.indexOf('}'))).toContain('--has-pupil: 1');
    });
  });
});
