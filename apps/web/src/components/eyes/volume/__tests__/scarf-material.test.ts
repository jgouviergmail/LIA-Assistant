import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { inflateSync } from 'node:zlib';
import { describe, expect, it } from 'vitest';
import source from './fixtures/scarf-source-alpha.json';
import { scarfWrapFacets } from '../scarf-wrap';
import { volumeProfile } from '../volume-geometry';

describe('the immutable woven band has connected alpha and invisible texture seams', () => {
  it('samples only the connected band, excluding the separated source fringe rows', () => {
    expect(
      createHash('sha256')
        .update(readFileSync(join(process.cwd(), 'public', source.asset)))
        .digest('hex')
    ).toBe(source.sha256);
    const alpha = inflateSync(Buffer.from(source.alphaZlib, 'base64'));
    const { uv } = scarfWrapFacets(volumeProfile('bip', 'female').collar)[0];
    const firstRow = Math.round(uv.top * source.height - 0.5);
    const lastRow = Math.round(uv.bottom * source.height - 0.5);
    for (
      let x = Math.floor(uv.left * source.width - 0.5);
      x <= Math.ceil(uv.right * source.width - 0.5);
      x++
    ) {
      expect(alpha[firstRow * source.width + x]).toBe(0);
      expect(alpha[lastRow * source.width + x]).toBe(0);
      const rows = Array.from(
        { length: lastRow - firstRow - 1 },
        (_, i) => alpha[(firstRow + 1 + i) * source.width + x]
      );
      expect(rows.every(value => value > 0)).toBe(true);
      // The neighbouring isolated fringe is real source data, not a second
      // garment layer that a rear return should expose around the silhouette.
      expect(alpha[(firstRow - 1) * source.width + x]).toBeLessThanOrEqual(4);
    }
  });
});
