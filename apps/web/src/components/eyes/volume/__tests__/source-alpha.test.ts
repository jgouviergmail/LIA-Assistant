import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { inflateSync } from 'node:zlib';
import { describe, expect, it } from 'vitest';
import {
  COMPANION_BODY_ALPHA_FLOOR,
  COMPANION_CHARACTERS,
  companionBodyAsset,
} from '@/components/spirit/companion-catalogue';
import { sourceAlphaTransfer } from '../source-alpha';
import sourceAlpha from './fixtures/limb-source-alpha.json';

describe('the measured companion alpha floor', () => {
  it.each(COMPANION_CHARACTERS)('%s still uses the measured, immutable source alpha', character => {
    for (const variant of ['female', 'male'] as const) {
      const source = sourceAlpha[`${character}/${variant}`];
      expect(source.asset).toBe(companionBodyAsset(character, variant));
      expect(
        createHash('sha256')
          .update(readFileSync(join(process.cwd(), 'public', source.asset)))
          .digest('hex')
      ).toBe(source.sha256);
      const alpha = inflateSync(Buffer.from(source.alphaZlib, 'base64'));
      const floor = COMPANION_BODY_ALPHA_FLOOR * 255;
      expect(alpha[0]).toBe(floor);
      expect(alpha[source.width - 1]).toBe(floor);
      expect(alpha.filter(value => value === floor).length).toBeGreaterThan(alpha.length / 3);
    }
  });

  it('removes the matte while retaining every higher alpha, opacity and a continuous soft edge', () => {
    const { slope, intercept, cutoff } = sourceAlphaTransfer(COMPANION_BODY_ALPHA_FLOOR);
    const corrected = (byte: number) => Math.max(0, Math.min(1, (byte / 255) * slope + intercept));
    expect([0, 1, 2].map(corrected)).toEqual([0, 0, 0]);
    expect(cutoff).toBeGreaterThanOrEqual(2 ** -14);
    expect(corrected(2)).toBeLessThan(cutoff);
    expect(corrected(255)).toBe(1);
    expect(corrected(3)).toBeCloseTo(1 / 253, 12);
    expect(corrected(3)).toBeGreaterThan(cutoff);
    for (let alpha = 3; alpha <= 255; alpha++) {
      expect(corrected(alpha)).toBeGreaterThan(corrected(alpha - 1));
      expect(alpha / 255 - corrected(alpha)).toBeLessThanOrEqual(COMPANION_BODY_ALPHA_FLOOR);
    }
  });

  it('leaves materials without the measured floor unchanged', () => {
    expect(sourceAlphaTransfer(0)).toEqual({ slope: 1, intercept: 0, cutoff: 0.004 });
  });
});
