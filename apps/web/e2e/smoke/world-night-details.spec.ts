import { test, expect } from '@playwright/test';
import { installArtOracle } from '../fixtures/world-art';

test('night lights brighten the source and ground without changing daylight', async ({ page }) => {
  await installArtOracle(page);
  const result = await page.evaluate(() => {
    const { world, createCamera, paintLampGlow, paintGroundLights, paintAtmosphere } =
      window.worldArtOracle;
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 320;
    const c = canvas.getContext('2d', { willReadFrequently: true })!;
    const lamp = world.props.find(p => p.kind === 'lamp')!;
    const camera = createCamera(
      { width: 320, height: 320 },
      { x: lamp.x + 0.21, y: lamp.y + 0.21 }
    );
    camera.zoom = 1;
    const sample = (phase: 'night' | 'noon') => {
      c.fillStyle = '#131d30';
      c.fillRect(0, 0, 320, 320);
      const atmosphere = { phase, weather: 'neutral' as const, time: null, timezone: null };
      const scene = { ...world, props: [lamp] },
        glow = paintLampGlow();
      paintGroundLights(c, scene, camera, atmosphere, glow);
      paintAtmosphere(c, scene, camera, atmosphere, 0, 'balanced', true, glow);
      const pixel = (x: number, y: number) => Array.from(c.getImageData(x, y, 1, 1).data);
      return {
        ground: pixel(160, 160),
        bulb: pixel(160, 99),
        halo: pixel(173, 99),
        distant: pixel(10, 10),
      };
    };
    return { day: sample('noon'), night: sample('night') };
  });
  expect(result.day.ground).toEqual([19, 29, 48, 255]);
  expect(result.night.ground[0]).toBeGreaterThan(120);
  expect(result.night.bulb[0]).toBeGreaterThan(200);
  expect(result.night.halo[0]).toBeGreaterThan(result.day.halo[0] + 20);
  expect(result.night.distant).toEqual(result.day.distant);
});

test('the star field is bounded, varied, stable, and absent by day', async ({ page }, info) => {
  await installArtOracle(page);
  const result = await page.evaluate(() => {
    const { paintStars, createCamera } = window.worldArtOracle;
    const canvas = document.createElement('canvas');
    canvas.width = 900;
    canvas.height = 600;
    document.body.append(canvas);
    const c = canvas.getContext('2d', { willReadFrequently: true })!;
    const camera = createCamera({ width: 900, height: 600 }, { x: 40, y: 40 });
    const pixels = (phase: 'noon' | 'night') => {
      c.clearRect(0, 0, 900, 600);
      paintStars(c, camera, phase, 'balanced');
      return Array.from(c.getImageData(0, 0, 900, 600).data).filter((_, i) => i % 4 === 3);
    };
    const day = pixels('noon'),
      night = pixels('night'),
      second = pixels('night');
    return {
      day: day.filter(Boolean).length,
      night: night.filter(Boolean).length,
      shades: new Set(night).size,
      stable: night.every((v, i) => v === second[i]),
    };
  });
  expect(result.day).toBe(0);
  expect(result.night).toBeGreaterThan(400);
  expect(result.night).toBeLessThan(2500);
  expect(result.shades).toBeGreaterThan(10);
  expect(result.stable).toBe(true);
  await page.locator('canvas').screenshot({ path: info.outputPath('night-stars.png') });
});

test('inspect tree families and the curved jukebox at native and enlarged scale', async ({
  page,
}, info) => {
  await installArtOracle(page);
  await page.evaluate(() => {
    const { world, propTextureKey, paintProp } = window.worldArtOracle;
    const canvas = document.createElement('canvas');
    canvas.width = 1100;
    canvas.height = 640;
    document.body.append(canvas);
    const c = canvas.getContext('2d', { willReadFrequently: true })!;
    c.fillStyle = '#e9e3d5';
    c.fillRect(0, 0, 1100, 640);
    const unique = new Map<string, (typeof world.props)[number]>();
    for (const prop of world.props.filter(p => p.kind === 'tree' || p.kind === 'jukebox'))
      unique.set(propTextureKey(prop, false, false), prop);
    [...unique.values()].forEach((prop, i) => {
      const sprite = paintProp(prop, 2);
      const x = 90 + i * 150,
        y = 200;
      for (const [yy, scale] of [
        [y, 1],
        [560, 2],
      ])
        c.drawImage(
          sprite.canvas,
          x - sprite.anchorX * scale,
          yy - sprite.anchorY * scale,
          sprite.width * scale,
          sprite.height * scale
        );
      c.font = '14px system-ui';
      c.fillStyle = '#253f43';
      c.fillText(prop.kind, x - 20, 235);
    });
  });
  await page.locator('canvas').screenshot({ path: info.outputPath('tree-jukebox-sheet.png') });
});
