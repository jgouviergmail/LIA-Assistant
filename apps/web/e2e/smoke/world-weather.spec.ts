import { test, expect } from '../fixtures';
import { installArtOracle } from '../fixtures/world-art';

test('world weather: moving rain stays outside and respects reduced motion at every quality', async ({
  page,
}) => {
  await installArtOracle(page);
  const results = await page.evaluate(() => {
    const { world, createCamera, paintAtmosphere } = window.worldArtOracle;
    const canvas = document.createElement('canvas');
    canvas.width = 240;
    canvas.height = 160;
    const c = canvas.getContext('2d')!;
    const camera = createCamera({ width: 240, height: 160 }, { x: 25, y: 25 });
    const atmosphere = {
      phase: 'noon' as const,
      weather: 'rain' as const,
      time: null,
      timezone: null,
    };
    const outdoor = { ...world, zones: [] };
    const indoor = {
      ...world,
      zones: [{ ...world.zones[0], x: 0, y: 0, width: 60, height: 60, covered: true }],
    };
    return (['low', 'balanced', 'high'] as const).map(quality => {
      const sample = (sheltered: boolean, reduced: boolean, time: number) => {
        c.clearRect(0, 0, 240, 160);
        paintAtmosphere(
          c,
          sheltered ? indoor : outdoor,
          camera,
          atmosphere,
          time,
          quality,
          reduced,
          null
        );
        const pixels = c.getImageData(0, 0, 240, 160).data;
        let painted = 0,
          hash = 2166136261;
        for (let i = 3; i < pixels.length; i += 4) {
          if (pixels[i]) painted++;
          hash = Math.imul(hash ^ pixels[i], 16777619) >>> 0;
        }
        return { painted, hash };
      };
      return {
        quality,
        outside: sample(false, false, 1),
        later: sample(false, false, 1.2),
        inside: sample(true, false, 1),
        reduced: sample(false, true, 1),
      };
    });
  });
  for (const row of results) {
    expect(row.outside.painted, row.quality).toBeGreaterThan(50);
    expect(row.later.hash, row.quality).not.toBe(row.outside.hash);
    expect(row.inside.painted, row.quality).toBe(0);
    expect(row.reduced.painted, row.quality).toBe(0);
  }
});
