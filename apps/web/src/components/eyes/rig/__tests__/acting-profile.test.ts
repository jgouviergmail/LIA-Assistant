import { describe, expect, it } from 'vitest';
import { RIG_EYE_STYLE_IDS } from '../../eye-styles';
import { pickActingSketch, resolveActingProfile, type RigCharacterId } from '../acting-profile';
import { SKETCHES } from '../sketches';

const SIGNATURES = {
  nimbo: 'body-sneeze',
  orbit: 'body-balloon',
  bip: 'body-hops',
  boulon: 'body-roll',
  oscar: 'body-bow',
} as const;

describe('native character direction', () => {
  it.each(Object.entries(SIGNATURES))(
    'gives %s a recognizable signature without starving other scenes',
    (id, signature) => {
      const profile = resolveActingProfile(id as RigCharacterId, 'billes');
      const draws = Array.from({ length: 1000 }, (_, index) =>
        pickActingSketch(profile, () => index / 1000)
      );
      expect(profile.signature).toBe(signature);
      expect(draws.filter(name => name === signature).length).toBeGreaterThan(120);
      expect(new Set(draws)).toEqual(new Set(SKETCHES));
      expect(draws).toEqual(
        Array.from({ length: 1000 }, (_, index) => pickActingSketch(profile, () => index / 1000))
      );
    }
  );

  it('keeps recent performances out of the draw, even for the favorite gag', () => {
    const profile = resolveActingProfile('bip', 'cozmo');
    const recent = ['body-hops', 'fly', 'body-sneeze'] as const;
    for (let draw = 0; draw <= 1; draw += 0.01)
      expect(recent).not.toContain(pickActingSketch(profile, () => draw, recent));
    expect(SKETCHES).toContain(pickActingSketch(profile, () => 1, SKETCHES));
  });

  it('derives every legacy personality from its real rig skin and never alters selection on invalid entropy', () => {
    for (const style of RIG_EYE_STYLE_IDS) {
      const profile = resolveActingProfile(undefined, style);
      expect(profile.identity).toBe(style);
      for (const draw of [-1, 1, Infinity, NaN])
        expect(SKETCHES).toContain(pickActingSketch(profile, () => draw));
    }
  });
});
