/**
 * avatar-transitions — the pure rules behind the mood ping and the emotion burst.
 */

import { describe, expect, it } from 'vitest';

import {
  EMOTION_PARTICLES,
  PARTICLE_INTENSITY_THRESHOLD,
  emotionBurstGlyph,
  moodChangePings,
} from '../avatar-transitions';

describe('moodChangePings', () => {
  it('pings a real change between two known moods on the live avatar', () => {
    expect(moodChangePings('playful', 'serene', true)).toBe(true);
  });

  it.each([
    ['history row', 'playful', 'serene', false],
    ['first known mood', null, 'serene', true],
    ['snapshot without psyche', 'playful', null, true],
    ['same mood', 'playful', 'playful', true],
  ] as const)('stays quiet for a %s', (_case, previous, next, live) => {
    expect(moodChangePings(previous, next, live)).toBe(false);
  });
});

describe('emotionBurstGlyph', () => {
  const strong = PARTICLE_INTENSITY_THRESHOLD;

  it('bursts a whitelisted emotion at the threshold, on the live avatar', () => {
    expect(emotionBurstGlyph('amusement', 'tenderness', strong, true, false)).toBe(
      EMOTION_PARTICLES.tenderness
    );
  });

  it.each([
    ['history row', 'amusement', 'tenderness', strong, false, false],
    ['first emotion', null, 'tenderness', strong, true, false],
    ['emotion gone', 'tenderness', null, strong, true, false],
    ['same emotion', 'tenderness', 'tenderness', strong, true, false],
    ['emotion off the whitelist', 'amusement', 'confusion', strong, true, false],
    ['intensity under the threshold', 'amusement', 'tenderness', strong - 0.01, true, false],
    ['reader asking for less motion', 'amusement', 'tenderness', strong, true, true],
  ] as const)(
    'stays quiet for a %s',
    (_case, previous, next, intensity, live, reducedMotion) => {
      expect(emotionBurstGlyph(previous, next, intensity, live, reducedMotion)).toBeNull();
    }
  );
});
