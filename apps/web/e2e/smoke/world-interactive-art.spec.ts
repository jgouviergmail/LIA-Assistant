import { test, expect } from '../fixtures';
import { installArtOracle } from '../fixtures/world-art';

test('hover marks only the ground footprint and leaves every opaque furniture pixel unchanged', async ({
  page,
}) => {
  await installArtOracle(page);
  const result = await page.evaluate(() => {
    const a = window.worldArtOracle,
      source = a.world.props.find(p => p.kind === 'chair');
    if (!source) throw new Error('No chair');
    const failures: string[] = [];
    let changed = 0;
    for (const facing of [0, 1, 2, 3] as const) {
      const prop = { ...source, x: 2, y: 2, facing };
      const sprite = a.paintProp(prop, 1, false);
      const canvas = document.createElement('canvas');
      canvas.width = 256;
      canvas.height = 256;
      const c = canvas.getContext('2d', { willReadFrequently: true });
      if (!c) throw new Error('No canvas');
      c.fillStyle = '#254437';
      c.fillRect(0, 0, 256, 256);
      c.save();
      c.translate(128, 60);
      a.paintHoverFootprint(c, prop);
      c.restore();
      const marked = c.getImageData(0, 0, 256, 256).data;
      for (let py = 0; py < 256; py++)
        for (let px = 0; px < 256; px++) {
          const i = (py * 256 + px) * 4;
          if (marked[i] === 37 && marked[i + 1] === 68 && marked[i + 2] === 55) continue;
          changed++;
          const sx = (px - 128) / 32,
            sy = (py - 60) / 16,
            wx = (sx + sy) / 2,
            wy = (sy - sx) / 2;
          if (wx < 1.94 || wx > 3.06 || wy < 1.94 || wy > 3.06) failures.push('outside footprint');
        }
      const x = 128 - sprite.anchorX,
        y = 124 - sprite.anchorY;
      c.drawImage(sprite.canvas, x, y);
      const final = c.getImageData(0, 0, 256, 256).data;
      const pixels = sprite.canvas
        .getContext('2d')
        ?.getImageData(0, 0, sprite.canvas.width, sprite.canvas.height).data;
      if (!pixels) throw new Error('No sprite');
      for (let py = 0; py < sprite.canvas.height; py++)
        for (let px = 0; px < sprite.canvas.width; px++) {
          const i = (py * sprite.canvas.width + px) * 4;
          if (pixels[i + 3] !== 255) continue;
          const at = ((py + y) * 256 + px + x) * 4;
          if (
            final[at] !== pixels[i] ||
            final[at + 1] !== pixels[i + 1] ||
            final[at + 2] !== pixels[i + 2]
          )
            failures.push('furniture tint');
        }
    }
    return { failures: [...new Set(failures)], changed };
  });
  expect(result.failures).toEqual([]);
  expect(result.changed).toBeGreaterThan(100);
});

test('the crystal has a steady magical halo with reduced motion, and a slow animated breath otherwise', async ({
  page,
}) => {
  await installArtOracle(page);
  const result = await page.evaluate(() => {
    const a = window.worldArtOracle,
      prop = a.world.props.find(p => p.kind === 'crystal');
    if (!prop) throw new Error('No crystal');
    const sprite = a.crystalAura();
    const frame = (time: number, reduced: boolean) => {
      const canvas = document.createElement('canvas');
      canvas.width = 200;
      canvas.height = 200;
      const c = canvas.getContext('2d', { willReadFrequently: true });
      if (!c) throw new Error('No canvas');
      a.paintCrystalAura(c, { ...prop, x: 0, y: 0 }, sprite, time, reduced);
      return Array.from(c.getImageData(0, 0, 200, 200).data);
    };
    const stable = frame(0, true),
      later = frame(10, true),
      animated = frame(2, false);
    return {
      stable: stable.every((v, i) => v === later[i]),
      moving: stable.some((v, i) => v !== animated[i]),
      pixels: stable.filter((v, i) => i % 4 === 3 && v > 0).length,
    };
  });
  expect(result.stable).toBe(true);
  expect(result.moving).toBe(true);
  expect(result.pixels).toBeGreaterThan(300);
});

test('inspect each chair facing after the backrest assembly correction', async ({ page }, info) => {
  await installArtOracle(page);
  await page.evaluate(() => {
    const a = window.worldArtOracle,
      source = a.world.props.find(p => p.kind === 'chair' && p.activity === 'routines');
    if (!source) throw new Error('No oracle chair');
    const sheet = document.createElement('canvas');
    sheet.width = 960;
    sheet.height = 520;
    sheet.id = 'chair-detail';
    const c = sheet.getContext('2d');
    if (!c) throw new Error('No canvas');
    c.fillStyle = '#765ba1';
    c.fillRect(0, 0, 960, 520);
    for (const facing of [0, 1, 2, 3] as const) {
      const sprite = a.paintProp(
        { ...source, facing, tone: facing % 2 ? 'clay' : 'violet' },
        2,
        false
      );
      c.drawImage(
        sprite.canvas,
        90 + facing * 230 - sprite.anchorX * 2,
        360 - sprite.anchorY * 2,
        sprite.width * 2,
        sprite.height * 2
      );
    }
    document.body.append(sheet);
  });
  await page
    .locator('#chair-detail')
    .screenshot({ path: info.outputPath('chairs-all-directions.png') });
});
