import { describe, expect, it } from 'vitest';
import { EYE_EXPRESSIONS } from '@/components/eyes/expression-engine';
import { spiritAsset, spiritExpressionForMood, SPIRIT_EXPRESSIONS } from '../catalogue';

describe('Spirit expression contract', () => {
  it('addresses only the compact portrait pack', () => {
    expect(spiritAsset('female', 'joy', true)).toBe('/avatars/spirit/v1/compact/female/joy.webp');
    expect(spiritAsset('male', 'joy', false)).toBe(
      '/avatars/spirit/v1/compact/male/joy-still.webp'
    );
  });

  it('can represent every expression emitted by the companion', () => {
    expect(new Set(SPIRIT_EXPRESSIONS)).toEqual(new Set(EYE_EXPRESSIONS));
  });

  it.each([
    ['serene', 'neutral'],
    ['curious', 'attentive'],
    ['energized', 'excited'],
    ['playful', 'joy'],
    ['reflective', 'thinking'],
    ['agitated', 'worried'],
    ['melancholic', 'sad'],
    ['neutral', 'neutral'],
    ['content', 'joy'],
    ['determined', 'focused'],
    ['defiant', 'anger'],
    ['resigned', 'tired'],
    ['overwhelmed', 'fear'],
    ['tender', 'tender'],
  ] as const)('represents the %s mood with the %s expression', (mood, expression) => {
    expect(spiritExpressionForMood(mood)).toBe(expression);
  });
});
