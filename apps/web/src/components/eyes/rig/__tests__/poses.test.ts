/**
 * Pose tables — the 20 expression recipes and the 6 style sheets, as data.
 *
 * These tables ARE the migration of the stylesheet's "Expression recipes" and
 * "STYLE SHEETS" sections. Two classes of test guard them:
 *  - completeness (every expression resolves, every declared key is a real
 *    channel, every style is known) — the boot-time registry doctrine;
 *  - transcription spot-checks, so a typo in a number that no human will ever
 *    re-read is caught by a machine.
 *
 * The resolution ORDER is the load-bearing part: a style's neutral must not be
 * overwritten by another style's expression radii. Getting that wrong is
 * exactly the bug that shipped in 2026-08 (every style turning into Cozmo the
 * moment a generic recipe declared a radius).
 */

import { describe, it, expect } from 'vitest';
import {
  POSES,
  STYLE_GEOMETRY,
  STYLE_LID_MODE,
  STYLE_POSE_OVERRIDES,
  exaggeratePose,
  resolveLoops,
  resolvePose,
} from '@/components/eyes/rig/poses';
import { CHANNELS, restChannelValues, type ChannelKey } from '@/components/eyes/rig/channels';
import { EYE_EXPRESSIONS } from '@/components/eyes/expression-engine';
import { EYE_STYLE_IDS } from '@/components/eyes/eye-styles';

const isChannel = (key: string): key is ChannelKey => key in CHANNELS;

describe('pose tables', () => {
  it('declares a pose for every expression', () => {
    EYE_EXPRESSIONS.forEach(expression => expect(POSES[expression]).toBeDefined());
    expect(Object.keys(POSES)).toHaveLength(EYE_EXPRESSIONS.length);
  });

  it('declares geometry for every registered style', () => {
    EYE_STYLE_IDS.forEach(id => expect(STYLE_GEOMETRY[id]).toBeDefined());
  });

  it('never lets a GENERIC recipe declare a silhouette radius', () => {
    // The 2026-08 production bug, translated into the new architecture. A
    // radius declared by a style-agnostic recipe is applied to all six styles,
    // so the psyche-driven idle poses (tender / bored / focused…) rendered
    // every style as a Cozmo rectangle. Radii are per-style by construction:
    // they belong in STYLE_GEOMETRY or STYLE_POSE_OVERRIDES, never in POSES.
    const offenders = Object.entries(POSES)
      .filter(([, pose]) => Object.keys(pose).some(key => /^rv?(Top|Bot)[LR]$/.test(key)))
      .map(([expression]) => expression);
    expect(offenders).toEqual([]);
  });

  it('only ever names real channels', () => {
    Object.values(POSES).forEach(pose =>
      Object.keys(pose).forEach(key => expect(isChannel(key)).toBe(true))
    );
    Object.values(STYLE_GEOMETRY).forEach(geometry =>
      Object.keys(geometry).forEach(key => expect(isChannel(key)).toBe(true))
    );
    Object.entries(STYLE_POSE_OVERRIDES).forEach(([styleId, byExpression]) => {
      expect(EYE_STYLE_IDS).toContain(styleId);
      Object.entries(byExpression ?? {}).forEach(([expression, values]) => {
        expect(EYE_EXPRESSIONS).toContain(expression);
        Object.keys(values ?? {}).forEach(key => expect(isChannel(key)).toBe(true));
      });
    });
  });
});

describe('resolvePose', () => {
  it('returns a complete channel set, resting where nothing is declared', () => {
    const pose = resolvePose('neutral', 'cozmo');
    expect(pose).toEqual(restChannelValues());
  });

  it('applies the expression recipe (transcription spot-check)', () => {
    const anger = resolvePose('anger', 'cozmo');
    expect(anger.syL).toBe(0.95);
    expect(anger.oyL).toBe(100);
    expect(anger.rotL).toBe(7);
    expect(anger.rotR).toBe(-7);
    expect(anger.lidTopL).toBe(34);

    const sleep = resolvePose('sleep', 'cozmo');
    expect(sleep.lidTopL).toBe(82);
    expect(sleep.lidBotL).toBe(4);
    expect(sleep.oyR).toBe(85);
  });

  it('keeps the question asymmetric — the asymmetry IS the message', () => {
    const question = resolvePose('question', 'cozmo');
    expect(question.syL).toBeGreaterThan(1);
    expect(question.syR).toBeLessThan(1);
    expect(question.rotR).toBe(-5);
    expect(question.rotL).toBe(0);
  });

  it('shuts only the right eye on a wink, the left keeping the joy dome', () => {
    const wink = resolvePose('wink', 'cozmo');
    const joy = resolvePose('joy', 'cozmo');
    expect(wink.blinkR).toBe(1);
    expect(wink.blinkL).toBe(0);
    expect(wink.syL).toBe(joy.syL);
  });

  it('layers style geometry UNDER the expression, never over it', () => {
    // billes is a circle: its neutral radius must survive an expression that
    // Cozmo happens to give a radius to.
    const excited = resolvePose('excited', 'billes');
    expect(excited.rTopL).toBe(STYLE_GEOMETRY.billes.rTopL);
    expect(excited.syL).toBe(POSES.excited.syL);
    // ...while Cozmo's own sheet does re-shape that same expression.
    expect(resolvePose('excited', 'cozmo').rTopL).toBe(0.4);
  });

  it('lets a style override the expression itself (last word)', () => {
    // amande scowls harder than the generic recipe, and straightens its base
    // tilt when surprised.
    expect(resolvePose('anger', 'amande').rotL).toBe(12);
    expect(resolvePose('neutral', 'amande').baseRotL).toBe(-12);
    expect(resolvePose('surprise', 'amande').baseRotL).toBe(0);
    // traits is a stroke language: joy is a drawn arch, not a squashed screen.
    expect(resolvePose('joy', 'traits').syL).toBe(1);
    expect(resolvePose('joy', 'traits').oyL).toBe(50);
  });
});

describe('lid mode', () => {
  it('declares how EVERY style closes an eye', () => {
    EYE_STYLE_IDS.forEach(id => expect(['clip', 'squash']).toContain(STYLE_LID_MODE[id]));
  });

  it('clips the styles with a surface, squashes the drawn ones', () => {
    expect(STYLE_LID_MODE.cozmo).toBe('clip');
    expect(STYLE_LID_MODE.billes).toBe('clip');
    expect(STYLE_LID_MODE.traits).toBe('squash');
    expect(STYLE_LID_MODE.anneaux).toBe('squash');
  });

  it('leaves no sustained lid on a squashing style — a clipped ring breaks', () => {
    // Verified in a browser (2026-08-31): `focused` clipped rendered two
    // specks on `traits` and two disconnected side arcs on `anneaux`.
    EYE_EXPRESSIONS.forEach(expression => {
      (['traits', 'anneaux'] as const).forEach(style => {
        const pose = resolvePose(expression, style);
        expect({
          expression,
          style,
          top: pose.lidTopL,
          bottom: pose.lidBotL,
          radius: pose.lidRL,
        }).toEqual({ expression, style, top: 0, bottom: 0, radius: 0 });
      });
    });
  });

  it('flattens to exactly the band the lid would have left visible', () => {
    // `focused` covers 30 % from the top and 24 % from the bottom.
    const clipped = resolvePose('focused', 'cozmo');
    const squashed = resolvePose('focused', 'anneaux');
    const visible = (100 - clipped.lidTopL - clipped.lidBotL) / 100;
    expect(squashed.syL).toBeCloseTo(clipped.syL * visible, 6);
    // ...anchored on that band's own centre, so the eye stays where it was.
    expect(squashed.oyL).toBeCloseTo(clipped.lidTopL + (visible * 100) / 2, 6);
  });

  it('leaves a lidless pose untouched', () => {
    const surprise = resolvePose('surprise', 'anneaux');
    expect(surprise.syL).toBe(POSES.surprise.syL);
    expect(surprise.oyL).toBe(50);
  });
});

describe('exaggeratePose', () => {
  const neutral = resolvePose('neutral', 'billes');
  const anger = resolvePose('anger', 'billes');

  it('is the identity at amplitude 1', () => {
    expect(exaggeratePose(neutral, anger, 1)).toBe(anger);
  });

  it('scales the deviation from the style neutral, in both directions', () => {
    const lively = exaggeratePose(neutral, anger, 1.5);
    const drowsy = exaggeratePose(neutral, anger, 0.5);
    expect(lively.rotL).toBeCloseTo(neutral.rotL + (anger.rotL - neutral.rotL) * 1.5, 6);
    expect(drowsy.rotL).toBeCloseTo(neutral.rotL + (anger.rotL - neutral.rotL) * 0.5, 6);
  });

  it('never eats the STYLE identity — a drowsy circle is still a circle', () => {
    // billes' radius is its whole silhouette: scaling it toward the default
    // rest value would quietly turn the marble into a Cozmo screen.
    const drowsy = exaggeratePose(neutral, resolvePose('neutral', 'billes'), 0.5);
    expect(drowsy.rTopL).toBe(neutral.rTopL);
  });

  it('never leaves a lid ajar — openness states a fact, not an intensity', () => {
    const neutral = resolvePose('neutral', 'cozmo');
    const drowsy = exaggeratePose(neutral, resolvePose('wink', 'cozmo'), 0.5);
    expect(drowsy.blinkR).toBe(1);
    // ...and the same for a sustained lid: a drowsy character asleep must not
    // sleep with its eyes 8 % open.
    const asleep = exaggeratePose(neutral, resolvePose('sleep', 'cozmo'), 0.92);
    expect(asleep.lidTopL).toBe(resolvePose('sleep', 'cozmo').lidTopL);
  });
});

describe('resolveLoops', () => {
  it('breathes on the calm poses and never on a reflex', () => {
    expect(resolveLoops('neutral', 'calm').some(loop => loop.channel === 'mass')).toBe(true);
    expect(resolveLoops('surprise', 'calm')).toHaveLength(0);
  });

  it('paces the breath by mood family (lively quicker, drowsy slower)', () => {
    const period = (family: 'lively' | 'calm' | 'drowsy') =>
      resolveLoops('neutral', family).find(loop => loop.channel === 'mass')?.periodMs;
    expect(period('lively')).toBeLessThan(period('calm')!);
    expect(period('calm')).toBeLessThan(period('drowsy')!);
  });

  it('gives fear its shiver', () => {
    expect(resolveLoops('fear', 'calm').some(loop => loop.channel === 'massX')).toBe(true);
  });

  it('gives searching NO sweep — looking is a saccade pattern, not a loop', () => {
    // A periodic sine on the gaze is a windscreen wiper. Searching is scripted
    // as jumps between fixations instead (see `rig/scripts.ts`).
    expect(resolveLoops('searching', 'calm')).toHaveLength(0);
  });

  it('desynchronises the two eyes on EVERY per-eye loop (never a metronome)', () => {
    // Universal invariant, not a spot-check: a per-eye loop that runs both
    // eyes on the same phase AND the same period is a metronome, whichever
    // expression declared it.
    EYE_EXPRESSIONS.forEach(expression => {
      (['lively', 'calm', 'drowsy'] as const).forEach(family => {
        const loops = resolveLoops(expression, family);
        const left = loops.filter(loop => loop.channel.endsWith('L'));
        const right = loops.filter(loop => loop.channel.endsWith('R'));
        expect(left.length).toBe(right.length);
        left.forEach((loop, index) => {
          const twin = right[index];
          expect(loop.channel.slice(0, -1)).toBe(twin.channel.slice(0, -1));
          expect(loop.phase === twin.phase && loop.periodMs === twin.periodMs).toBe(false);
        });
      });
    });
  });

  it('never freezes a resting face — the moving hold drifts on two axes', () => {
    const idle = resolveLoops('neutral', 'calm');
    const driftX = idle.filter(loop => loop.channel === 'gazeX');
    const driftY = idle.filter(loop => loop.channel === 'gazeY');
    // Two INCOMMENSURABLE periods per axis: a single sine reads as a pendulum.
    expect(driftX).toHaveLength(2);
    expect(driftY).toHaveLength(2);
    expect(driftX[0].periodMs).not.toBe(driftX[1].periodMs);
    // Small enough to read as life, never as an intent.
    idle
      .filter(loop => loop.channel.startsWith('gaze'))
      .forEach(loop => expect(Math.abs(loop.amplitude)).toBeLessThan(0.05));
  });

  it('does not drift a face that is concentrating or asleep', () => {
    expect(resolveLoops('focused', 'calm').some(loop => loop.channel === 'gazeX')).toBe(false);
    expect(resolveLoops('sleep', 'drowsy').some(loop => loop.channel === 'gazeX')).toBe(false);
  });

  it('only ever loops real channels, with a positive period', () => {
    EYE_EXPRESSIONS.forEach(expression => {
      (['lively', 'calm', 'drowsy'] as const).forEach(family => {
        resolveLoops(expression, family).forEach(loop => {
          expect(isChannel(loop.channel)).toBe(true);
          expect(loop.periodMs).toBeGreaterThan(0);
          expect(Number.isFinite(loop.amplitude)).toBe(true);
        });
      });
    });
  });
});
