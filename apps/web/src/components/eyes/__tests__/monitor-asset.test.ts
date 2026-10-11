import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import manifest from '../../../../public/avatars/monitor/v2/manifest.json';
import { MONITOR_SCREEN } from '../monitor-geometry';
import { webpEnvelope } from '@/components/spirit/__tests__/webp-envelope';

describe('Original monitor asset', () => {
  it('ships one small transparent fixed canvas matching its manifest', () => {
    const bytes = readFileSync(join(process.cwd(), 'public/avatars/monitor/v2/body.webp'));
    expect(webpEnvelope(bytes)).toMatchObject({
      width: 192,
      height: 192,
      alpha: true,
      animation: false,
      frames: 0,
    });
    expect(bytes.length).toBeLessThanOrEqual(32 * 1024);
    expect(manifest.bytes).toBe(bytes.length);
    expect(manifest.size).toBe(192);
    expect(manifest.sha256).toBe(createHash('sha256').update(bytes).digest('hex'));
  });

  it('uses the asset projection inside its canvas, with rounded corners smaller than the screen', () => {
    expect(MONITOR_SCREEN).toBe(manifest.screen);
    const { x, y, width, height, radius } = MONITOR_SCREEN;
    expect(x).toBeGreaterThan(0);
    expect(y).toBeGreaterThan(0);
    expect(x + width).toBeLessThan(1);
    expect(y + height).toBeLessThan(1);
    expect(radius).toBeGreaterThan(0);
    expect(radius * 2).toBeLessThan(Math.min(width, height));
  });
});
