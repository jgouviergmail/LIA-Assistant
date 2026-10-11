import { describe, expect, it } from 'vitest';
import { characterNeutralPose, type RigCharacterId } from '../acting-profile';
import { createEyeRig } from '../runtime';
import { resolvePose } from '../poses';
import { NEUTRAL_CONTEXT } from '../direction';
import { EYE_EXPRESSIONS } from '../../expression-engine';
import { RIG_EYE_STYLE_IDS } from '../../eye-styles';

const CHARACTERS = ['spirit', 'moss', 'lumen', 'nimbo', 'orbit', 'boulon', 'oscar'] as const;

function neutralRig(characterId: RigCharacterId) {
  return createEyeRig({
    characterId,
    initial: { expression: 'neutral', styleId: 'billes', family: 'calm' },
    reducedMotion: true,
  });
}

describe('a character has a quiet welcoming rest, not a new emotion', () => {
  it.each(CHARACTERS)(
    'gives %s a compact, slightly parted smile without widening or moving the face',
    characterId => {
      const native = resolvePose('neutral', 'billes');
      const warmed = characterNeutralPose(native, 'neutral', characterId);
      expect(warmed.mouthCurve).toBeGreaterThanOrEqual(0.25);
      expect(warmed.mouthCurve).toBeLessThanOrEqual(0.38);
      expect(warmed.mouthOpen).toBeGreaterThan(0);
      expect(warmed.mouthOpen).toBeLessThanOrEqual(0.05);
      expect({ ...warmed, mouthCurve: native.mouthCurve, mouthOpen: native.mouthOpen }).toEqual(
        native
      );
      expect(neutralRig(characterId).values()).toMatchObject({
        mouthCurve: warmed.mouthCurve,
        mouthOpen: warmed.mouthOpen,
        mouthW: native.mouthW,
      });
    }
  );

  it('preserves Bip, every legacy skin and every authored non-neutral expression', () => {
    for (const styleId of RIG_EYE_STYLE_IDS) {
      const native = resolvePose('neutral', styleId);
      expect(characterNeutralPose(native, 'neutral', styleId)).toEqual(native);
    }
    const native = resolvePose('neutral', 'billes');
    expect(characterNeutralPose(native, 'neutral', 'bip')).toEqual(native);
    for (const expression of EYE_EXPRESSIONS.filter(value => value !== 'neutral')) {
      const authored = resolvePose(expression, 'billes');
      expect(characterNeutralPose(authored, expression, 'oscar')).toEqual(authored);
      const rig = createEyeRig({
        characterId: 'oscar',
        initial: { expression, styleId: 'billes', family: 'calm' },
        reducedMotion: true,
      });
      const baseline = createEyeRig({
        initial: { expression, styleId: 'billes', family: 'calm' },
        reducedMotion: true,
      });
      expect(rig.values()).toEqual(baseline.values());
    }
    const smiley = createEyeRig({ characterId: 'oscar', reducedMotion: true });
    expect(smiley.values()).toEqual(createEyeRig({ reducedMotion: true }).values());
  });

  it('yields its courtesy to signed temperament and leaves activity and speech unchanged', () => {
    const rig = neutralRig('oscar');
    for (const pleasure of [-1, -0.8, 0, 0.8, 1]) {
      rig.setContext({ ...NEUTRAL_CONTEXT, pleasure });
      rig.settle();
      if (pleasure === -0.8) expect(rig.values().mouthCurve).toBeLessThan(-0.35);
      if (Math.abs(pleasure) === 1) {
        const baseline = createEyeRig({
          initial: { expression: 'neutral', styleId: 'billes', family: 'calm' },
          reducedMotion: true,
        });
        baseline.setContext({ ...NEUTRAL_CONTEXT, pleasure });
        baseline.settle();
        expect(rig.values().mouthCurve).toBe(baseline.values().mouthCurve);
      }
    }
    const negative = characterNeutralPose(
      resolvePose('neutral', 'billes'),
      'neutral',
      'oscar',
      -0.001
    );
    const positive = characterNeutralPose(
      resolvePose('neutral', 'billes'),
      'neutral',
      'oscar',
      0.001
    );
    expect(negative.mouthCurve).toBe(positive.mouthCurve);
    for (const context of [
      { ...NEUTRAL_CONTEXT, activity: 'reading' as const },
      { ...NEUTRAL_CONTEXT, responding: true },
    ]) {
      rig.setContext(context);
      rig.settle();
      const baseline = createEyeRig({
        initial: { expression: 'neutral', styleId: 'billes', family: 'calm' },
        reducedMotion: true,
      });
      baseline.setContext(context);
      baseline.settle();
      expect(rig.values()).toEqual(baseline.values());
    }
  });

  it('recalibrates a settled identity change without changing the current frame', () => {
    const rig = neutralRig('orbit');
    const before = { ...rig.values() };
    rig.setCharacterId('oscar');
    expect(rig.values()).toEqual(before);
    rig.settle();
    expect(rig.values()).toEqual(neutralRig('oscar').values());
  });

  it('keeps invalid temperament finite and ordinary idle movement within a slight mouth opening', () => {
    const native = resolvePose('neutral', 'billes');
    for (const pleasure of [NaN, Infinity, -Infinity, -5, 5]) {
      const pose = characterNeutralPose(native, 'neutral', 'nimbo', pleasure);
      expect(Number.isFinite(pose.mouthCurve)).toBe(true);
      expect(Number.isFinite(pose.mouthOpen)).toBe(true);
      expect(pose.mouthCurve).toBeGreaterThanOrEqual(native.mouthCurve);
      expect(pose.mouthCurve).toBeLessThanOrEqual(0.38);
      expect(pose.mouthOpen).toBeLessThanOrEqual(0.05);
    }
    const rig = createEyeRig({
      characterId: 'nimbo',
      initial: { expression: 'neutral', styleId: 'billes', family: 'calm' },
    });
    for (let frame = 0; frame < 500; frame++) {
      rig.step(16);
      expect(rig.values().mouthOpen).toBeGreaterThanOrEqual(0);
      expect(rig.values().mouthOpen).toBeLessThanOrEqual(0.08);
    }
  });
});
