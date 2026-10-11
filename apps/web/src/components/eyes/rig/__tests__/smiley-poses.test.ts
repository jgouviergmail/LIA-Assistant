import { describe, expect, it } from 'vitest';
import { EYE_EXPRESSIONS } from '../../expression-engine';
import { POSES, STYLE_POSE_OVERRIDES, resolvePose } from '../poses';

describe('Smiley acting over intact sculpted eyes', () => {
  it('calibrates every expression to real lids rather than squashing an iris', () => {
    expect(Object.keys(STYLE_POSE_OVERRIDES.smiley ?? {}).sort()).toEqual(
      [...EYE_EXPRESSIONS].sort()
    );
    for (const expression of EYE_EXPRESSIONS) {
      const pose = resolvePose(expression, 'smiley');
      expect(pose.syL).toBe(1);
      expect(pose.syR).toBe(1);
    }
  });

  it('rests with a soft upper lid, opening for attention and startle', () => {
    const neutral = resolvePose('neutral', 'smiley');
    expect(neutral.lidTopL).toBeGreaterThanOrEqual(18);
    expect(neutral.lidTopL).toBeLessThanOrEqual(20);
    expect(neutral.lidBotL).toBeLessThan(20);
    expect(resolvePose('attentive', 'smiley').lidTopL).toBeLessThan(neutral.lidTopL);
    expect(resolvePose('surprise', 'smiley').lidTopL).toBeLessThan(
      resolvePose('attentive', 'smiley').lidTopL
    );
    expect(neutral.browYL).toBeGreaterThan(0);
    expect(neutral.mouthCurve).toBeGreaterThan(0.3);
    expect(neutral.mouthCurve).toBeLessThan(0.5);
    expect(neutral.mouthW).toBeLessThan(0.8);
    expect(resolvePose('joy', 'smiley').browYL).toBeLessThan(neutral.browYL);
    expect(resolvePose('surprise', 'smiley').browYL).toBeLessThan(
      resolvePose('joy', 'smiley').browYL
    );
  });

  it('smiles from the cheeks while excitement stays distinctly open', () => {
    const joy = resolvePose('joy', 'smiley');
    const excited = resolvePose('excited', 'smiley');
    expect(joy.lidBotL).toBeGreaterThan(35);
    expect(joy.lidBotL).toBeGreaterThan(joy.lidTopL);
    expect(joy.lidBotL).toBeGreaterThan(excited.lidBotL + 20);
    expect(excited.lidTopL + excited.lidBotL).toBeLessThan(30);
  });

  it('asks asymmetrically and grieves with raised inner brows and visible lids', () => {
    const question = resolvePose('question', 'smiley');
    expect(question.lidTopR).toBeGreaterThan(question.lidTopL + 15);
    expect(question.browYL).toBeLessThan(question.browYR);
    for (const expression of ['sad', 'worried'] as const) {
      const pose = resolvePose(expression, 'smiley');
      expect(pose.browRotL).toBeLessThan(0);
      expect(pose.browRotR).toBeGreaterThan(0);
      expect(pose.lidTopL).toBeGreaterThan(resolvePose('neutral', 'smiley').lidTopL);
    }
  });

  it('distinguishes concentration, drowsiness and actual closed sleep/wink', () => {
    const focused = resolvePose('focused', 'smiley');
    expect(focused.lidTopL + focused.lidBotL).toBeGreaterThan(55);
    const sleepy = resolvePose('sleepy', 'smiley');
    expect(sleepy.lidTopL + sleepy.lidBotL).toBeGreaterThan(70);
    expect(sleepy.lidTopL + sleepy.lidBotL).toBeLessThan(100);
    const sleep = resolvePose('sleep', 'smiley');
    expect(sleep.lidTopL + sleep.lidBotL).toBe(100);
    expect(sleep.lidTopR + sleep.lidBotR).toBe(100);
    expect(sleep.blinkL).toBe(1);
    expect(sleep.blinkR).toBe(1);
    const wink = resolvePose('wink', 'smiley');
    expect(wink.blinkL).toBe(0);
    expect(wink.blinkR).toBe(1);
    expect(wink.lidBotL).toBeGreaterThan(35);
  });

  it('preserves generic and Spirit native recipes', () => {
    expect(resolvePose('joy', 'billes').syL).toBe(POSES.joy.syL);
    expect(resolvePose('surprise', 'cozmo').syL).toBe(POSES.surprise.syL);
    expect(resolvePose('neutral', 'billes').lidTopL).toBe(0);
  });
});
