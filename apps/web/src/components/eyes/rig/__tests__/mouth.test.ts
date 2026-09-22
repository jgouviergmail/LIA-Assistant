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

import { POSES, exaggeratePose, resolveLoops, resolvePose } from '@/components/eyes/rig/poses';
import { FAMILY_DYNAMICS } from '@/components/eyes/rig/dynamics';
import { AMPLITUDE_MAX } from '@/components/eyes/tone';
import { createEyeRig, type EyeRig } from '@/components/eyes/rig/runtime';
import { ARRIVAL_SCRIPTS, resolvePatterns } from '@/components/eyes/rig/scripts';
import { CHANNELS, type ChannelKey } from '@/components/eyes/rig/channels';
import { EYE_EXPRESSIONS, type EyeExpression } from '@/components/eyes/expression-engine';

const CSS = readFileSync(join(process.cwd(), 'src/styles/eyes.css'), 'utf8');

/** The brow's own lift above the eye, from its `translate` — its own regex
 * because the value lives inside a `calc()` rather than in a plain length. */
function browBaseOffset(): number {
  const block = CSS.slice(CSS.indexOf('.lia-eye-brow {'));
  const match = block
    .slice(0, block.indexOf('}'))
    .match(/calc\(-100% - ([\d.]+)em \+ var\(--brow-y\)\)/);
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
  it('lifts the corners for what is pleasant', () => {
    (['joy', 'excited', 'tender', 'wink', 'attentive', 'sleep'] as const).forEach(expression => {
      expect({ expression, up: curveOf(expression) > 0 }).toEqual({
        expression,
        up: true,
      });
    });
  });

  it('drops them for what is not', () => {
    (['sad', 'anger', 'worried', 'fear', 'focused', 'bored', 'tired'] as const).forEach(
      expression => {
        expect({ expression, down: curveOf(expression) < 0 }).toEqual({
          expression,
          down: true,
        });
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
    expect(smiling.values().mouthCurve).toBeGreaterThan(0);

    const frowning = createEyeRig({
      initial: { expression: 'sad', styleId: 'cozmo', family: 'calm' },
    });
    expect(frowning.values().mouthArc).toBeGreaterThan(0);
    expect(frowning.values().mouthCurve).toBeLessThan(0);
  });

  it('never emits a negative depth, on any expression', () => {
    EYE_EXPRESSIONS.forEach(expression => {
      const rig = createEyeRig({
        initial: { expression, styleId: 'cozmo', family: 'calm' },
      });
      trace(rig, 'mouthArc', 40);
      expect({ expression, negative: rig.values().mouthArc < 0 }).toEqual({
        expression,
        negative: false,
      });
    });
  });
});

describe('speaking', () => {
  it('finally speaks: the mouth flaps', () => {
    const rig = createEyeRig();
    rig.setPose({ expression: 'speaking', styleId: 'cozmo', family: 'calm' });
    const opening = trace(rig, 'mouthOpen', 120);
    expect(Math.max(...opening) - Math.min(...opening)).toBeGreaterThan(0.15);
  });

  it('is GENERATED speech, not a loop: the mouth is the state pattern and the loops only bob the eyes', () => {
    // Sines on a mouth get louder and quieter; they never say a word. The
    // opening, the shape and the brows are keyed syllable by syllable in
    // `rig/speech.ts`; what is left to loop is the eyes' bob.
    resolveLoops('speaking', 'calm').forEach(loop =>
      expect({
        channel: loop.channel,
        eyes: /^(ty|sy)[LR]$/.test(loop.channel),
      }).toEqual({
        channel: loop.channel,
        eyes: true,
      })
    );
    const pattern = resolvePatterns('speaking').map(tape => tape.channel);
    expect(pattern).toEqual(
      expect.arrayContaining(['mouthOpen', 'mouthW', 'mouthCurve', 'mouthSkew'])
    );
  });

  it('rests between two phrases on a CLOSED mouth — the pose is the listening face', () => {
    expect(resolvePose('speaking', 'cozmo').mouthOpen).toBe(0);
    expect(resolvePose('speaking', 'cozmo').mouthCurve).toBeGreaterThan(0);
  });

  it('never flaps a mouth that is not speaking — a sleeper breathes, it does not talk', () => {
    EYE_EXPRESSIONS.filter(expression => expression !== 'speaking').forEach(expression => {
      resolveLoops(expression, 'calm')
        .filter(loop => loop.channel === 'mouthOpen')
        .forEach(loop =>
          expect({ expression, slowBreath: loop.periodMs > 2000 }).toEqual({
            expression,
            slowBreath: true,
          })
        );
    });
  });

  it('has PHRASES: the mouth closes for a beat between them, and talks at a size the face can hold', () => {
    const rig = createEyeRig();
    rig.setPose({ expression: 'speaking', styleId: 'cozmo', family: 'calm' });
    trace(rig, 'mouthOpen', 60);
    const opening = trace(rig, 'mouthOpen', 1250); // 20 s
    let longestClosedMs = 0;
    let run = 0;
    for (const value of opening) {
      run = value <= 1e-6 ? run + 16 : 0;
      longestClosedMs = Math.max(longestClosedMs, run);
    }
    // A phrase pause: at least half a second shut.
    expect(longestClosedMs).toBeGreaterThanOrEqual(500);
    const closedShare = opening.filter(value => value <= 1e-6).length / opening.length;
    expect(closedShare).toBeGreaterThan(0.08);
    expect(closedShare).toBeLessThan(0.5);
    expect(Math.max(...opening)).toBeGreaterThan(0.4);
    expect(Math.max(...opening)).toBeLessThan(0.75);
  });
});

describe('drawing', () => {
  it('follows the HEAD but never the gaze — eyes move inside a face', () => {
    const block = CSS.slice(CSS.indexOf('.lia-mouth {'));
    const rule = block.slice(0, block.indexOf('\n}'));
    const head = CSS.slice(CSS.indexOf('.lia-head {'));
    const headRule = head.slice(0, head.indexOf('\n}'));
    expect(headRule).toContain('--rig-tilt');
    expect(headRule).toContain('--rig-mass');
    expect(rule).toContain('--rig-head-yaw');
    expect(rule).not.toContain('--rig-gaze');
  });

  it('is gated on a style token, like the other organs', () => {
    expect(CSS).toMatch(/opacity:\s*var\(--has-mouth\)/);
  });
});

describe('the speech bubble', () => {
  /** The eye box height the brow's `top:` is a fraction of (`--eye-h`). */
  const EYE_H_EM = 1.05;

  /** How far a raised brow reaches above the widget's own top edge, in the
   * widget's em — computed, not remembered, and at the LOUDEST the face can
   * be: the pose exaggerated by the widest amplitude a register can earn
   * times the liveliest mood family. The previous guard measured the pose as
   * authored, which is not what a `surprised` answer at full intensity draws. */
  function browReachEm(): number {
    const base = browBaseOffset();
    const height = cssLength('.lia-eye-brow {', 'height');
    const padding = cssLength('.lia-eyes-gaze {', 'padding');
    const loudest = AMPLITUDE_MAX * FAMILY_DYNAMICS.lively.amplitude;
    const neutral = resolvePose('neutral', 'cozmo');
    const reach = EYE_EXPRESSIONS.map(e => {
      const pose = exaggeratePose(neutral, resolvePose(e, 'cozmo'), loudest);
      const raise = Math.abs(Math.min(0, pose.browYL));
      // The brow is anchored to the visible top of the shape: a widened eye
      // (sy above 1) lifts that edge above the box, and the brow with it.
      const anchor =
        ((pose.oyL / 100) * (1 - pose.syL) + (pose.lidTopL / 100) * pose.syL) * EYE_H_EM;
      return raise + height - anchor;
    });
    return base + Math.max(...reach) - padding;
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
    // A wink, a question, consideration and boredom are all read from the corner
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
    const hold = resolveLoops('joy', 'calm')
      .filter(loop => loop.channel === 'mouthCurve')
      .reduce((sum, loop) => sum + Math.abs(loop.amplitude), 0);
    expect(Math.abs(rig.values().mouthArc - settled)).toBeLessThan(hold + 1e-3);
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
    expect(BLOCK).toContain('fill: var(--mouth-color, var(--eyes-color))');
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

  it('gives every SMILING expression a visible lean', () => {
    // A perfectly symmetric smile is the thing being corrected. 0.04 was
    // arithmetically an asymmetry and visually a compass.
    for (const expression of ['joy', 'excited', 'tender'] as const) {
      expect(Math.abs(resolvePose(expression, 'cozmo').mouthSkew)).toBeGreaterThan(0.12);
    }
  });

  it('lets the jaw drop with the opening', () => {
    const block = CSS.slice(CSS.indexOf('.lia-mouth {'));
    const coefficient = block.slice(0, block.indexOf('\n}')).match(/mouth-open, 0\) \* ([\d.]+)em/);
    expect(coefficient).not.toBeNull();
    expect(Number(coefficient?.[1])).toBeGreaterThan(0);
    expect(Number(coefficient?.[1])).toBeLessThanOrEqual(0.04);
  });
});
