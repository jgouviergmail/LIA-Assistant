/**
 * The mouth, and the bubble above it.
 *
 * The mouth is the second organ a viewer reads, and its grammar is one signed
 * number: positive lifts the corners, negative drops them, zero is the flat
 * line the two travel through. Everything here pins that — including the two
 * places it could quietly break: a mouth that FLICKERS between a smile and a
 * frown while resting near zero, and a `speaking` flap that ticks like a
 * metronome instead of sounding like speech.
 *
 * The bubble is guarded geometrically. It used to be a bare glyph 0.08em above
 * the eyes, which was fine while that space was empty — and became a mark
 * sitting in the middle of the brows the moment brows existed. The clearance
 * is therefore computed from the stylesheet and the pose table rather than
 * eyeballed once.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { POSES, resolveLoops, resolvePose } from '@/components/eyes/rig/poses';
import { createEyeRig, type EyeRig } from '@/components/eyes/rig/runtime';
import { ARRIVAL_SCRIPTS } from '@/components/eyes/rig/scripts';
import { CHANNELS, type ChannelKey } from '@/components/eyes/rig/channels';
import { EYE_EXPRESSIONS, type EyeExpression } from '@/components/eyes/expression-engine';

const CSS = readFileSync(join(process.cwd(), 'src/styles/eyes.css'), 'utf8');

/** The brow's own lift above the eye, from its `translate` — its own regex
 * because the value lives inside a `calc()` rather than in a plain length. */
function browBaseOffset(): number {
  const block = CSS.slice(CSS.indexOf('.lia-eye-brow {'));
  const match = block.slice(0, block.indexOf('}')).match(/translate:\s*-50%\s*calc\(-([\d.]+)em/);
  if (!match) throw new Error('no brow base offset');
  return Number(match[1]);
}

/** Pull one length out of a rule, or fail loudly — a guard that cannot find
 * what it measures must not pass quietly. */
function cssLength(rule: string, property: string): number {
  const block = CSS.slice(CSS.indexOf(rule));
  const match = block
    .slice(0, block.indexOf('}'))
    .match(new RegExp(`${property}:\\s*-?([\\d.]+)em`));
  if (!match) throw new Error(`no ${property} on ${rule}`);
  return Number(match[1]);
}

function trace(rig: EyeRig, channel: ChannelKey, frames: number): number[] {
  const values: number[] = [];
  for (let index = 0; index < frames; index += 1) {
    rig.step(16);
    values.push(rig.values()[channel]);
  }
  return values;
}

const curveOf = (expression: EyeExpression) => resolvePose(expression, 'cozmo').mouthCurve;

describe('the mouth', () => {
  it('is never absent — a face that GROWS a mouth to smile is a defect', () => {
    EYE_EXPRESSIONS.forEach(expression => {
      expect({ expression, present: resolvePose(expression, 'cozmo').mouthA > 0 }).toEqual({
        expression,
        present: true,
      });
    });
  });

  it('lifts the corners for what is pleasant', () => {
    (['joy', 'excited', 'tender', 'wink', 'attentive', 'sleep'] as const).forEach(expression => {
      expect({ expression, up: curveOf(expression) > 0 }).toEqual({ expression, up: true });
    });
  });

  it('drops them for what is not', () => {
    (['sad', 'anger', 'worried', 'fear', 'thinking', 'focused', 'bored', 'tired'] as const).forEach(
      expression => {
        expect({ expression, down: curveOf(expression) < 0 }).toEqual({ expression, down: true });
      }
    );
  });

  it('grades the extremes the way the emotions do', () => {
    const curves = EYE_EXPRESSIONS.map(curveOf);
    expect(curveOf('sad')).toBe(Math.min(...curves));
    expect(curveOf('excited')).toBe(Math.max(...curves));
  });

  it('opens widest for surprise, and stays shut at rest', () => {
    const opens = EYE_EXPRESSIONS.map(e => resolvePose(e, 'cozmo').mouthOpen);
    expect(resolvePose('surprise', 'cozmo').mouthOpen).toBe(Math.max(...opens));
    expect(resolvePose('neutral', 'cozmo').mouthOpen).toBe(0);
    // Asleep, a mouth hangs a little open. It is what sleeping looks like.
    expect(resolvePose('sleep', 'cozmo').mouthOpen).toBeGreaterThan(0);
  });

  it('is declared as ONE signed curve, never as a pair of shapes', () => {
    // A smile and a frown drawn separately are two states to keep in step, and
    // nothing can travel continuously between them.
    Object.values(POSES).forEach(pose => {
      expect('mouthArc' in pose).toBe(false);
      expect('mouthFlip' in pose).toBe(false);
    });
    expect(CHANNELS.mouthCurve.internal).toBe(true);
  });
});

describe('the derived arc', () => {
  it('is a positive depth plus a direction — what CSS can actually draw', () => {
    const smiling = createEyeRig({
      initial: { expression: 'joy', styleId: 'cozmo', family: 'calm' },
    });
    expect(smiling.values().mouthArc).toBeGreaterThan(0);
    expect(smiling.values().mouthFlip).toBe(1);

    const frowning = createEyeRig({
      initial: { expression: 'sad', styleId: 'cozmo', family: 'calm' },
    });
    expect(frowning.values().mouthArc).toBeGreaterThan(0);
    expect(frowning.values().mouthFlip).toBe(-1);
  });

  it('never emits a negative depth, on any expression', () => {
    EYE_EXPRESSIONS.forEach(expression => {
      const rig = createEyeRig({ initial: { expression, styleId: 'cozmo', family: 'calm' } });
      trace(rig, 'mouthArc', 40);
      expect({ expression, negative: rig.values().mouthArc < 0 }).toEqual({
        expression,
        negative: false,
      });
    });
  });

  it('HOLDS its direction through the flat crossing', () => {
    // Travelling from a frown to a smile, the curve passes through zero. If
    // the direction were recomputed there it would flicker on noise — the same
    // treatment the stretch axis already gets.
    const rig = createEyeRig({ initial: { expression: 'sad', styleId: 'cozmo', family: 'calm' } });
    rig.setPose({ expression: 'joy', styleId: 'cozmo', family: 'calm' });
    const flips = trace(rig, 'mouthFlip', 60);
    // Exactly one change of direction across the whole crossing.
    const changes = flips.filter((value, index) => index > 0 && value !== flips[index - 1]);
    expect(changes).toHaveLength(1);
    expect(rig.values().mouthFlip).toBe(1);
  });
});

describe('speaking', () => {
  it('finally speaks: the mouth flaps', () => {
    const rig = createEyeRig();
    rig.setPose({ expression: 'speaking', styleId: 'cozmo', family: 'calm' });
    const opening = trace(rig, 'mouthOpen', 120);
    expect(Math.max(...opening) - Math.min(...opening)).toBeGreaterThan(0.15);
  });

  it('does not tick: the flap is two incommensurable components', () => {
    // One sine on a mouth is unmistakable once you watch it — it is a metronome
    // with lips.
    const flap = resolveLoops('speaking', 'calm').filter(loop => loop.channel === 'mouthOpen');
    expect(flap).toHaveLength(2);
    expect(flap[0].periodMs).not.toBe(flap[1].periodMs);
    expect(flap[0].periodMs % flap[1].periodMs).not.toBe(0);
  });

  it('widens and narrows as much as it opens', () => {
    expect(resolveLoops('speaking', 'calm').some(loop => loop.channel === 'mouthW')).toBe(true);
  });

  it('keeps a syllable-rate cadence', () => {
    const fastest = Math.min(
      ...resolveLoops('speaking', 'calm')
        .filter(loop => loop.channel === 'mouthOpen')
        .map(loop => loop.periodMs)
    );
    expect(fastest).toBeGreaterThan(180);
    expect(fastest).toBeLessThan(400);
  });

  it('never flaps a mouth that is not speaking', () => {
    EYE_EXPRESSIONS.filter(expression => expression !== 'speaking').forEach(expression => {
      expect(resolveLoops(expression, 'calm').some(loop => loop.channel === 'mouthOpen')).toBe(
        false
      );
    });
  });
});

describe('drawing', () => {
  it('follows the HEAD but never the gaze — eyes move inside a face', () => {
    const block = CSS.slice(CSS.indexOf('.lia-mouth {'));
    const rule = block.slice(0, block.indexOf('\n}'));
    expect(rule).toContain('--rig-tilt');
    expect(rule).toContain('--rig-mass');
    expect(rule).not.toContain('--rig-gaze');
  });

  it('is gated on a style token, like the other organs', () => {
    expect(CSS).toMatch(/opacity:\s*calc\(var\(--rig-mouth-a, 0\.5\) \* var\(--has-mouth\)\)/);
  });
});

describe('the speech bubble', () => {
  /** How far a raised brow reaches above the widget's own top edge, in the
   * widget's em — computed, not remembered. */
  function browReachEm(): number {
    const base = browBaseOffset();
    const height = cssLength('.lia-eye-brow {', 'height');
    const padding = cssLength('.lia-eyes-gaze {', 'padding');
    const highest = Math.max(
      ...EYE_EXPRESSIONS.map(e => Math.abs(Math.min(0, resolvePose(e, 'cozmo').browYL)))
    );
    return base + highest + height - padding;
  }

  /** Where the tail's point sits, in the widget's em. The bubble's lengths are
   * in ITS own em (font-size: 0.6em), and the tail is a square rotated 45°, so
   * it reaches lower than its box by half the difference of its diagonal. */
  function bubbleTipEm(): number {
    const fontSize = cssLength('.lia-emote {', 'font-size');
    const margin = cssLength('.lia-emote {', 'margin-bottom');
    const tailDrop = cssLength('.lia-emote::after {', 'bottom');
    const side = cssLength('.lia-emote::after {', 'width');
    const rotationOverhang = (side * Math.SQRT2 - side) / 2;
    return (margin - tailDrop - rotationOverhang) * fontSize;
  }

  it('clears the brows — the defect that made it sit inside the face', () => {
    expect(bubbleTipEm()).toBeGreaterThan(browReachEm() + 0.15);
  });

  it('is a bubble: a filled body, an outline, and a tail', () => {
    const block = CSS.slice(CSS.indexOf('.lia-emote {'));
    const rule = block.slice(0, block.indexOf('\n}'));
    expect(rule).toContain('border-radius');
    expect(rule).toContain('background: var(--color-background)');
    expect(rule).toContain('border: 0.11em solid var(--eyes-color)');
    expect(CSS).toContain('.lia-emote::after');
  });

  it('takes its surface from the theme, so it reads on any background', () => {
    // A bubble drawn in the eyes' own colour would vanish the glyph; one drawn
    // transparent would inherit whatever the chat put behind it.
    expect(CSS).not.toMatch(/\.lia-emote \{[^}]*background:\s*transparent/);
  });
});

describe('the corners', () => {
  const skewOf = (expression: EyeExpression) => resolvePose(expression, 'cozmo').mouthSkew;

  it('are where the acting is: a face that can only be symmetric plays two notes', () => {
    const crooked = EYE_EXPRESSIONS.filter(expression => skewOf(expression) !== 0);
    expect(crooked.length).toBeGreaterThan(EYE_EXPRESSIONS.length / 2);
  });

  it('are most crooked exactly where a straight mouth would be wrong', () => {
    // A wink, a question, a thought and boredom are all read from the corner
    // of the mouth before anything else on the face.
    const strongest = [...EYE_EXPRESSIONS]
      .sort((left, right) => Math.abs(skewOf(right)) - Math.abs(skewOf(left)))
      .slice(0, 4);
    expect(strongest.sort()).toEqual(['bored', 'question', 'thinking', 'wink']);
  });

  it('stay level where the mouth must read as symmetric', () => {
    expect(skewOf('surprise')).toBe(0);
    expect(skewOf('speaking')).toBe(0);
    expect(skewOf('neutral')).toBe(0);
  });

  it('keep the SAME side through the flat crossing, in the drawing', () => {
    // The shape is mirrored for a frown, so a bare rotation would swap the
    // raised corner exactly where the mouth is a flat bar and the tilt is the
    // only thing visible. The lean is derived ONCE and every consumer reads
    // that one value.
    expect(CSS).toContain(
      '--mouth-lean: calc(var(--rig-mouth-skew, 0) * var(--rig-mouth-flip, 1))'
    );
    expect(CSS).toContain('rotate: calc(var(--mouth-lean) * 14deg)');
  });
});

describe('the mouth arrives', () => {
  it('SNAPS past a smile and settles back into it', () => {
    const rig = createEyeRig();
    rig.setPose({ expression: 'joy', styleId: 'cozmo', family: 'calm' });
    const arc = trace(rig, 'mouthArc', 40);
    const settled = resolvePose('joy', 'cozmo').mouthCurve;
    expect(Math.max(...arc)).toBeGreaterThan(settled * 1.06);
    // ...and settles INTO the pose — within the moving hold, which keeps
    // riding the curve by +/-0.03 once the beat is over (a resting mouth is
    // never quite still).
    trace(rig, 'mouthArc', 160);
    expect(Math.abs(rig.values().mouthArc - settled)).toBeLessThan(0.03 + 1e-3);
  });

  it('drops the jaw PAST the open pose on a startle', () => {
    const rig = createEyeRig();
    rig.setPose({ expression: 'surprise', styleId: 'cozmo', family: 'calm' });
    const opening = trace(rig, 'mouthOpen', 30);
    expect(Math.max(...opening)).toBeGreaterThan(resolvePose('surprise', 'cozmo').mouthOpen);
  });

  it('deepens a frown AFTER the eyes have fallen — grief is sequential', () => {
    const sad = ARRIVAL_SCRIPTS.sad ?? [];
    const mouth = sad.find(tape => tape.channel === 'mouthCurve');
    const eyes = sad.find(tape => tape.channel === 'mass');
    expect(mouth).toBeDefined();
    expect(mouth!.keys[0].atMs).toBeGreaterThan(eyes!.keys[0].atMs);
  });

  it('gives every entrance that has a mouth beat a RELATIVE one', () => {
    // An absolute target would yank a posed mouth to a fixed curve; the beat
    // has to be an offset from wherever the expression put it.
    Object.values(ARRIVAL_SCRIPTS).forEach(tapes =>
      (tapes ?? [])
        .filter(tape => tape.channel === 'mouthCurve' || tape.channel === 'mouthSkew')
        .forEach(tape => expect(tape.relative).toBe(true))
    );
  });
});

describe('the mouth is a solid shape, not a stroke', () => {
  const SHAPE = CSS.slice(CSS.indexOf('.lia-mouth-shape {'));
  const BLOCK = SHAPE.slice(0, SHAPE.indexOf('\n}'));

  it('is FILLED in the ink, the way the eyes themselves are', () => {
    // A hairline under two filled, glowing eyes is a line drawing wearing a
    // screen face. Every feature in this language is a filled silhouette.
    expect(BLOCK).toContain('background: var(--eyes-color)');
    // A stroke, not a radius: the shape is filled, so the only `border-*` it
    // may carry is geometry.
    expect(BLOCK).not.toContain('border-bottom:');
    expect(BLOCK).not.toContain('border-bottom-width');
  });

  it('draws the whole mouth with ONE element', () => {
    // Lips, an outlined opening and a tongue were three elements kept in step
    // by hand; a silhouette that morphs needs none of them.
    expect(CSS).not.toContain('.lia-mouth-line');
    expect(CSS).not.toContain('.lia-mouth-open');
    expect(CSS).not.toContain('.lia-mouth-tongue');
  });

  it('FLATTENS its top edge as the curve deepens — that is what makes it a grin', () => {
    // At rest the same shape is a fully rounded little bar; at full curve it
    // is a flat-topped, round-bottomed slab, which IS a cartoon smile.
    expect(BLOCK).toContain('(1 - var(--rig-mouth-arc, 0)) * 38%');
  });

  it('grows with BOTH the curve and the opening, so one shape covers three moods', () => {
    expect(BLOCK).toContain('var(--rig-mouth-arc, 0) * 0.26em');
    expect(BLOCK).toContain('var(--rig-mouth-open, 0) * 0.5em');
  });

  it('publishes the arc UNITLESS, because CSS cannot divide a length by a length', () => {
    // The stylesheet needs the depth as a height AND as a radius ratio. In em
    // it could be the first and never the second.
    expect(CHANNELS.mouthArc.unit).toBe('num');
    const rig = createEyeRig({ initial: { expression: 'joy', styleId: 'cozmo', family: 'calm' } });
    expect(rig.values().mouthArc).toBeLessThanOrEqual(1);
  });

  it('is turned over for a frown rather than drawn a second time', () => {
    expect(BLOCK).toContain('var(--rig-mouth-flip, 1);');
  });

  it('keeps a FROWN under the eyes instead of growing it into the face', () => {
    // Mirroring about the top edge sends the shape upwards. Measured in a
    // browser before this line existed: every flipped mouth (anger, sad)
    // overlapped the eyes by 3.2 to 7.7 px at sm/md/lg, while every unflipped
    // one cleared them by 5.5 to 13.8. Pushing the shape down by its own
    // height when — and only when — it is flipped puts both directions in the
    // same band, and the same measurement then reads 4.3 to 13.8 px, positive
    // throughout.
    expect(BLOCK).toContain(
      'translate: 0 calc((1 - var(--rig-mouth-flip, 1)) * 0.5 * var(--mouth-h))'
    );
  });

  it('is never a HALF-DISC: three measured departures from the compass', () => {
    // "Une bouche trop symetrique comme un demi cercle plein, ce n'est pas
    // esthetique ni expressif" — owner, 2026-09-01. Measured in a browser on a
    // real `joy` after the fix: bottom corners 55.07% against 44.93%, top
    // corners 16.94% (never flat), width/height 2.71 (a half-disc is 2.0).
    //
    // 1. The top edge keeps a floor of curvature however deep the smile goes.
    expect(BLOCK).toContain('calc(12% + (1 - var(--rig-mouth-arc, 0)) * 38%)');
    // 2. The two bottom corners are DIFFERENT, leaning with the mouth.
    expect(BLOCK).toContain('calc(50% + var(--mouth-lean) * 26%)');
    expect(BLOCK).toContain('calc(50% - var(--mouth-lean) * 26%)');
    // 3. It SPREADS as it curves: a big smile is wide and shallow, not a bowl.
    expect(BLOCK).toContain('calc(1 + var(--rig-mouth-arc, 0) * 0.13)');
  });

  it('derives the lean ONCE, so the tilt and the asymmetry can never disagree', () => {
    // Three consumers, one expression. Written out three times, the corner that
    // rides higher and the corner that is rounder would part company exactly at
    // the flat crossing — where they are the only thing left to see.
    expect(BLOCK).toContain(
      '--mouth-lean: calc(var(--rig-mouth-skew, 0) * var(--rig-mouth-flip, 1))'
    );
    expect(BLOCK).toContain('rotate: calc(var(--mouth-lean) * 14deg)');
  });

  it('gives every SMILING expression a visible lean', () => {
    // A perfectly symmetric smile is the thing being corrected. 0.04 was
    // arithmetically an asymmetry and visually a compass.
    for (const expression of ['joy', 'excited', 'tender'] as const) {
      expect(Math.abs(resolvePose(expression, 'cozmo').mouthSkew)).toBeGreaterThan(0.12);
    }
  });

  it('lets the jaw drop with the opening', () => {
    const block = CSS.slice(CSS.indexOf('.lia-mouth {'));
    expect(block.slice(0, block.indexOf('\n}'))).toContain('var(--rig-mouth-open, 0) * 0.06em');
  });
});
