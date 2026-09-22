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
import {
  BROW_SMILE_LIFT_EM,
  BROW_STRETCH_MAX,
  BROW_STRETCH_MIN,
  browStretchFor,
  createEyeRig,
} from '@/components/eyes/rig/runtime';
import { CHANNELS, CHANNEL_KEYS } from '@/components/eyes/rig/channels';
import { GROUP_FREQUENCY_SCALE, GROUP_LEAD_MS } from '@/components/eyes/rig/dynamics';
import { EYE_EXPRESSIONS, type EyeExpression } from '@/components/eyes/expression-engine';

const CSS = readFileSync(join(process.cwd(), 'src/styles/eyes.css'), 'utf8');

/** Expressions whose asymmetry is deliberate — the whole point, in fact. */
const ASYMMETRIC: ReadonlySet<EyeExpression> = new Set(['question', 'thinking', 'wink']);

/** How much each eye's INNER end is lowered (positive) or raised (negative).
 * The two eyes mirror, so the right eye's angle is negated. */
function innerEndDrop(expression: EyeExpression): {
  left: number;
  right: number;
} {
  const pose = resolvePose(expression, 'cozmo');
  return { left: pose.browRotL, right: -pose.browRotR };
}

describe('the brow', () => {
  it('is FULLY present, always — drawn, never faded in (no presence channel exists)', () => {
    // ADR-264 kept the brows at half presence and inked them up for every
    // scene; measured on the running widget (2026-09-17), that ink rose from
    // 0.5 to 1 twenty-seven times in five minutes, in under 100 ms each time,
    // and read as an interface element switching on. A face is drawn whole.
    const keys: readonly string[] = CHANNEL_KEYS;
    expect(keys.filter(key => /^browA[LR]$/.test(key))).toEqual([]);
    expect(keys.includes('mouthA')).toBe(false);
    expect(CSS).toMatch(/\.lia-eye-brow \{[^}]*opacity:\s*var\(--has-brow\)/);
    expect(CSS).toMatch(/\.lia-mouth \{[^}]*opacity:\s*var\(--has-mouth\)/);
  });

  it('KNITS: a scowl, a worry and a fright pull the brows toward the nose, a startle sends them apart', () => {
    const knit = (expression: EyeExpression) => {
      const pose = resolvePose(expression, 'cozmo');
      // Screen em: the left brow moves right (+) and the right brow moves
      // left (-) to meet at the nose.
      return { left: pose.browXL + 0, right: -pose.browXR + 0 };
    };
    (['anger', 'focused', 'worried', 'fear', 'sad'] as const).forEach(expression => {
      const { left, right } = knit(expression);
      expect({ expression, left: left > 0, right: right > 0 }).toEqual({
        expression,
        left: true,
        right: true,
      });
    });
    expect(knit('surprise').left).toBeLessThan(0);
    expect(knit('neutral')).toEqual({ left: 0, right: 0 });
    expect(CHANNELS.browXL.unit).toBe('em');
  });

  it('is WEIGHTED by its own motion: raised it stretches thin, pressed it thickens', () => {
    // Squash and stretch on the organ, derived from the motion it already
    // makes: no pose declares a thickness, and no beat can forget one.
    expect(CHANNELS.browSL.derived).toBe(true);
    expect(browStretchFor(0, CHANNELS.browArcL.rest)).toBe(1);
    expect(browStretchFor(-0.1, CHANNELS.browArcL.rest)).toBeLessThan(0.85);
    expect(browStretchFor(0.03, CHANNELS.browArcL.rest)).toBeGreaterThan(1.04);
    expect(browStretchFor(0, 0.85)).toBeLessThan(1);
    expect(browStretchFor(-1, 1)).toBe(BROW_STRETCH_MIN);
    expect(browStretchFor(1, 0)).toBe(BROW_STRETCH_MAX);
    const settled = (expression: EyeExpression) => {
      const rig = createEyeRig({
        initial: { expression, styleId: 'cozmo', family: 'calm' },
        reducedMotion: true,
      });
      rig.step(16);
      return rig.values().browSL;
    };
    expect(settled('surprise')).toBeLessThan(0.85);
    expect(settled('anger')).toBeGreaterThan(1.04);
    expect(settled('neutral')).toBe(1);
    // ...and the sheet draws the thickness AND the width from it, at
    // constant ink: a thin brow is a long one.
    const block = CSS.slice(CSS.indexOf('.lia-eye-brow {'));
    const rule = block.slice(0, block.indexOf('\n}'));
    expect(CSS).toContain('stroke-width: calc(10px * clamp(0.94, var(--brow-s), 1.06))');
    expect(rule).toMatch(/width:\s*calc\(var\(--eye-w, 1\.3em\) \* 0\.72\)/);
  });

  it('sits ON the eye: anchored to the visible top edge of the shape, so a dome never leaves it floating', () => {
    // Measured on the running widget (2026-09-17): the brow was pinned to
    // the top of the eye BOX, and a joy dome (the shape squashed to 0.55
    // around its fifth) left it hanging a third of an eye above the eye.
    const block = CSS.slice(CSS.indexOf('.lia-eye-brow {'));
    const rule = block.slice(0, block.indexOf('\n}'));
    expect(rule).toMatch(
      /top:\s*calc\(var\(--oy\) \* \(1 - var\(--sy\)\) \+ var\(--lid-top\) \* var\(--sy\)\)/
    );
    expect(rule).not.toContain('bottom: 100%');
    expect(rule).toMatch(
      /translate:\s*calc\(-50% \+ var\(--brow-x\)\)\s*calc\(-100% - [\d.]+em \+ var\(--brow-y\)\)/
    );
  });

  it('lifts a hair with a smile — the cheeks push the whole face up', () => {
    const rig = createEyeRig({
      initial: { expression: 'joy', styleId: 'cozmo', family: 'calm' },
      reducedMotion: true,
    });
    rig.step(16);
    const pose = resolvePose('joy', 'cozmo');
    const smile = Math.max(0, pose.mouthCurve - CHANNELS.mouthCurve.rest);
    expect(smile).toBeGreaterThan(0.5);
    expect(rig.values().browYL).toBeCloseTo(pose.browYL - smile * BROW_SMILE_LIFT_EM, 6);
    const scowl = createEyeRig({
      initial: { expression: 'anger', styleId: 'cozmo', family: 'calm' },
      reducedMotion: true,
    });
    scowl.step(16);
    // A frown pushes nothing: the coupling is one-sided.
    expect(scowl.values().browYL).toBeCloseTo(resolvePose('anger', 'cozmo').browYL, 6);
  });

  it('moves on its OWN dynamics, a beat ahead of the eye it sits on', () => {
    // A startle is brows first: the pair flies before the lids have moved.
    // A group of its own is what lets it lead on every preset without a
    // per-expression script, and it departs with the willed channels.
    (['browYL', 'browRotL', 'browArcL', 'browXL'] as const).forEach(key => {
      expect({ key, group: CHANNELS[key].group }).toEqual({
        key,
        group: 'brow',
      });
    });
    expect(GROUP_FREQUENCY_SCALE.brow).toBeGreaterThan(GROUP_FREQUENCY_SCALE.pose);
    expect(GROUP_LEAD_MS.brow).toBe(0);
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
    });
    const from = resolvePose('neutral', 'cozmo');
    const to = resolvePose('surprise', 'cozmo');
    rig.setPose({ expression: 'surprise', styleId: 'cozmo', family: 'calm' });
    let browAt90 = -1;
    let eyeAt90 = -1;
    for (let frame = 1; frame <= 60; frame += 1) {
      rig.step(16);
      const values = rig.values();
      const brow = (values.browArcL - from.browArcL) / (to.browArcL - from.browArcL);
      const eye = (values.syL - from.syL) / (to.syL - from.syL);
      if (browAt90 < 0 && brow >= 0.9) browAt90 = frame;
      if (eyeAt90 < 0 && eye >= 0.9) eyeAt90 = frame;
    }
    expect(browAt90).toBeGreaterThan(0);
    expect(eyeAt90).toBeGreaterThan(0);
    expect(browAt90).toBeLessThan(eyeAt90);
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
      expect(pose.browXL + 0).toBe(-pose.browXR + 0);
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
});

describe('the arch', () => {
  const arcOf = (expression: EyeExpression) => resolvePose(expression, 'cozmo').browArcL;

  it('is a channel of its own: a bar can tilt, only an arch can wonder', () => {
    expect(CHANNELS.browArcL.group).toBe('brow');
    expect(CHANNELS.browArcL.unit).toBe('num');
    expect(CHANNELS.browArcL.rest).toBeGreaterThan(0);
    expect(CHANNELS.browArcL.rest).toBeLessThan(0.2);
  });

  it('stays within what the stylesheet can draw, on every expression', () => {
    EYE_EXPRESSIONS.forEach(expression => {
      const pose = resolvePose(expression, 'cozmo');
      expect({
        expression,
        inRange: pose.browArcL >= 0 && pose.browArcL <= 1,
      }).toEqual({
        expression,
        inRange: true,
      });
      expect({
        expression,
        inRange: pose.browArcR >= 0 && pose.browArcR <= 1,
      }).toEqual({
        expression,
        inRange: true,
      });
    });
  });

  it('arches highest for surprise — the whole brow flies', () => {
    const arcs = EYE_EXPRESSIONS.map(arcOf);
    expect(arcOf('surprise')).toBe(Math.max(...arcs));
    expect(arcOf('surprise')).toBeGreaterThan(0.7);
  });

  it('flattens outright for the scowls: a pressed brow has no curve', () => {
    (['anger', 'focused', 'bored'] as const).forEach(expression => {
      expect({ expression, arc: arcOf(expression) }).toEqual({
        expression,
        arc: 0,
      });
    });
  });

  it('curves gently for what is pleasant', () => {
    (['joy', 'excited', 'tender', 'attentive'] as const).forEach(expression => {
      expect({
        expression,
        curved: arcOf(expression) > CHANNELS.browArcL.rest,
      }).toEqual({
        expression,
        curved: true,
      });
    });
  });

  it('breaks the symmetry ONE way for a question and a thought', () => {
    (['question', 'thinking', 'wink'] as const).forEach(expression => {
      const pose = resolvePose(expression, 'cozmo');
      expect({ expression, oneUp: pose.browArcL > pose.browArcR }).toEqual({
        expression,
        oneUp: true,
      });
    });
  });

  it('mirrors between the eyes everywhere else', () => {
    EYE_EXPRESSIONS.forEach(expression => {
      if (ASYMMETRIC.has(expression)) return;
      const pose = resolvePose(expression, 'cozmo');
      expect({ expression, arcL: pose.browArcL }).toEqual({
        expression,
        arcL: pose.browArcR,
      });
    });
  });

  it('draws a continuous SVG arch with bounded thickness and round ends', () => {
    expect(CSS).toContain('stroke-linecap: round');
    expect(CSS).toContain('fill: none');
    expect(CSS).not.toContain('--brow-curve:');
    // Shape continuity and independent sides are measured in face-geometry.test.ts.
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
    expect(CSS).toMatch(/opacity:\s*var\(--has-brow\)/);
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
