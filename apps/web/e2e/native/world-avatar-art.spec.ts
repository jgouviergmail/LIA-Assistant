import { test, expect } from './fixtures';
import { installArtOracle } from '../fixtures/world-art';
test('appearance artwork: inspect all headings, hair, outfits and accessories without clipping', async ({
  page,
}, info) => {
  await installArtOracle(page);
  const result = await page.evaluate(() => {
    const { paintActor, avatar } = window.worldArtOracle;
    const sheet = document.createElement('canvas');
    sheet.width = 1024;
    sheet.height = 1200;
    document.body.append(sheet);
    document.body.style.margin = '0';
    document.body.style.background = '#e4e9e7';
    const ctx = sheet.getContext('2d');
    if (!ctx) throw new Error('Missing real canvas');
    ctx.fillStyle = '#e4e9e7';
    ctx.fillRect(0, 0, sheet.width, sheet.height);
    const variants = [
      ...(['bald', 'short', 'long', 'curly', 'ponytail', 'mohawk'] as const).map(hair => ({
        ...avatar,
        hair,
      })),
      ...(['casual', 'suit', 'dress'] as const).map(outfit => ({
        ...avatar,
        outfit,
        skin: 'espresso' as const,
        hair_color: 'gold' as const,
      })),
      ...(['cap', 'beanie', 'hat'] as const).map(headwear => ({
        ...avatar,
        headwear,
        glasses: true,
        outfit: 'suit' as const,
      })),
    ];
    const failures: string[] = [];
    variants.forEach((appearance, row) => {
      for (let heading = 0; heading < 8; heading++) {
        const sprite = paintActor(
          false,
          Math.floor(heading / 2),
          2,
          1.5,
          'teal',
          heading,
          null,
          appearance
        );
        const c = sprite.canvas.getContext('2d');
        if (!c) throw new Error('Missing actor canvas');
        const { width, height } = sprite.canvas,
          pixels = c.getImageData(0, 0, width, height).data;
        let occupied = 0;
        for (let y = 0; y < height; y++)
          for (let x = 0; x < width; x++) {
            if (pixels[(y * width + x) * 4 + 3] === 0) continue;
            occupied++;
            if (x === 0 || y === 0 || x === width - 1 || y === height - 1)
              failures.push('clipped ' + row + ':' + heading);
          }
        if (!occupied) failures.push('empty');
        ctx.drawImage(
          sprite.canvas,
          heading * 128 + 64 - sprite.anchorX,
          row * 100 + 95 - sprite.anchorY,
          width / 1.5,
          height / 1.5
        );
        sprite.canvas.width = 0;
        sprite.canvas.height = 0;
      }
    });
    return { failures, count: variants.length * 8 };
  });
  expect(result.count).toBe(96);
  expect(result.failures).toEqual([]);
  await page.setViewportSize({ width: 1024, height: 1200 });
  await page.screenshot({ path: info.outputPath('appearance-eight-headings.png') });
});
