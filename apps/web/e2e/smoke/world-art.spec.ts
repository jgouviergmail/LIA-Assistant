import { writeFile } from 'node:fs/promises';
import { test, expect } from '../fixtures';
import { installArtOracle } from '../fixtures/world-art';
import { installInertWorldAdmission } from '../fixtures/world-session';
import fr from '../../locales/fr/translation.json';
import { POND } from '../../src/features/world/house-layout';
import { WORLD, onSite } from '../../src/features/world/definition';

test('world artwork: complete silhouettes and exact solid foreground masks', async ({ page }) => {
  await installArtOracle(page);
  const findings = await page.evaluate(() => {
    const { paintProp, propTextureKey, world } = window.worldArtOracle;
    const checked = new Set<string>(),
      failures: string[] = [];
    const home = world.zones.find(zone => zone.id === 'home');
    if (!home) throw new Error('Missing private home');
    const privateProps = world.props
      .filter(
        prop =>
          prop.x >= home.x &&
          prop.x < home.x + home.width &&
          prop.y >= home.y &&
          prop.y < home.y + home.height
      )
      .flatMap(prop =>
        (['sage', 'teal', 'clay', 'violet', 'amber', 'cream'] as const).map(tone => ({
          ...prop,
          tone,
        }))
      );
    for (const prop of [...world.props, ...privateProps]) {
      const key = propTextureKey(prop, false, false);
      if (checked.has(key)) continue;
      checked.add(key);
      const solid = paintProp(prop, 1.5, false),
        colour = paintProp(prop, 1.5, true);
      const ctx = solid.canvas.getContext('2d'),
        coloured = colour.canvas.getContext('2d');
      if (!ctx || !coloured) throw new Error('Missing actual canvas');
      const { width: w, height: h } = solid.canvas;
      const a = ctx.getImageData(0, 0, w, h).data,
        b = coloured.getImageData(0, 0, w, h).data;
      let pixels = 0;
      for (let y = 0; y < h; y++)
        for (let x = 0; x < w; x++) {
          const i = (y * w + x) * 4,
            alpha = a[i + 3];
          if (alpha > 0) pixels++;
          if (alpha > 0 && (x === 0 || y === 0 || x === w - 1 || y === h - 1))
            failures.push('clipped ' + prop.kind);
          if (alpha > b[i + 3]) failures.push('mask exceeds colour ' + prop.kind);
          if (alpha === 255 && (a[i] !== b[i] || a[i + 1] !== b[i + 1] || a[i + 2] !== b[i + 2]))
            failures.push('opaque mask mismatch ' + prop.kind);
        }
      if (!pixels) failures.push('empty ' + prop.kind);
      solid.canvas.width = 0;
      colour.canvas.width = 0;
    }
    return { families: checked.size, failures: [...new Set(failures)] };
  });
  expect(findings.families).toBeGreaterThan(30);
  expect(findings.failures).toEqual([]);
});

for (const phase of ['day', 'night'] as const)
  test(
    'world artwork: inspect every place through the real camera at play and inspection zoom (' +
      phase +
      ')',
    async ({ page, authenticate, mockApi }, info) => {
      // This is a full authoring tour (two screenshots and six zoom clicks
      // per place), not a frame-time benchmark. WebKit needs about 8s per
      // place on the local runner; keep the entire capture bounded separately.
      test.setTimeout(240000);
      const user = await authenticate();
      await installInertWorldAdmission(page, user.id);
      const instant = Date.parse(
        phase === 'night' ? '2026-10-25T01:00:00Z' : '2026-10-25T11:00:00Z'
      );
      await mockApi([
        {
          url: '**/api/v1/world/environment',
          json: {
            server_time: instant / 1000,
            timezone: 'Europe/Paris',
            weather: null,
          },
        },
      ]);
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto('/fr/dashboard/world');
      await page.locator('.world-admission input[type="checkbox"]').check();
      await page.locator('.world-admission button[type="submit"]').click();
      const canvas = page.locator('canvas.world-canvas');
      await expect(canvas).toBeVisible();
      const position = async () =>
        page
          .locator('.world-minimap circle')
          .last()
          .evaluate(el => [el.getAttribute('cx'), el.getAttribute('cy')]);
      const start = await position();
      const map = page.getByRole('button', { name: /^Carte du monde/ });
      const places = [
        ...WORLD.zones,
        { ...onSite(POND), id: 'pond' },
        { ...onSite({ x: 5, y: 57 }), width: 8, height: 20, id: 'vegetable-garden' },
      ];
      for (const zone of places) {
        const bounds = await map.boundingBox();
        if (!bounds) throw new Error('Missing map bounds');
        const x = zone.x + zone.width / 2,
          y = zone.y + zone.height / 2;
        await map.click({
          position: {
            x: ((x - y + WORLD.height + 4) / (WORLD.width + WORLD.height + 8)) * bounds.width,
            y: (((x + y) / 2 + 4) / ((WORLD.width + WORLD.height) / 2 + 8)) * bounds.height,
          },
        });
        await expect(page.getByRole('button', { name: 'Suivre mon personnage' })).toHaveAttribute(
          'aria-pressed',
          'false'
        );
        await page.evaluate(
          () =>
            new Promise<void>(resolve =>
              requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
            )
        );
        expect(await position()).toEqual(start);
        await page.screenshot({ path: info.outputPath(`art-${zone.id}.png`) });
        for (let i = 0; i < 3; i++)
          await page.getByRole('button', { name: 'Zoomer', exact: true }).click();
        await page.screenshot({ path: info.outputPath(`detail-${zone.id}.png`) });
        for (let i = 0; i < 3; i++)
          await page.getByRole('button', { name: fr.world.zoom_out, exact: true }).click();
      }
      for (const label of ['Zoomer', 'D\u00e9zoomer']) {
        for (let i = 0; i < (label === 'Zoomer' ? 3 : 6); i++)
          await page.getByRole('button', { name: label, exact: true }).click();
        await page.screenshot({
          path: info.outputPath(`art-${label === 'Zoomer' ? 'near' : 'far'}.png`),
        });
        expect(await position()).toEqual(start);
      }
      // The native HUD samples decoded textures on its bounded notification tick.
      await page.waitForTimeout(250);
      await page.getByRole('button', { name: fr.world.metrics, exact: true }).click();
      const textures = await page.locator('.world-metrics dd').nth(3).innerText();
      const textureMiB = Number(textures.split(' ')[0].replace(',', '.'));
      expect(textureMiB).toBeGreaterThan(0);
      expect(textureMiB).toBeLessThanOrEqual(128);
      const path = info.outputPath('art-cache-budget.json');
      await writeFile(
        path,
        JSON.stringify({
          textureMiB,
          ceilingMiB: 128,
          places: WORLD.zones.length,
          after: 'all authored places plus far zoom',
        })
      );
      await info.attach('art-cache-budget', { path, contentType: 'application/json' });
    }
  );

test('world artwork: all human directions, walk phases and palettes stay distinct and unclipped', async ({
  page,
}, info) => {
  await installArtOracle(page);
  const result = await page.evaluate(() => {
    const { paintActor } = window.worldArtOracle;
    const sheet = document.createElement('canvas');
    sheet.id = 'world-actor-sheet';
    sheet.width = 600;
    sheet.height = 820;
    const c = sheet.getContext('2d');
    if (!c) throw new Error('Missing canvas');
    c.fillStyle = '#f1eee6';
    c.fillRect(0, 0, 600, 820);
    const failures: string[] = [],
      directions: number[] = [],
      palettes: number[] = [];
    for (const tone of ['sage', 'teal', 'clay', 'violet', 'amber', 'cream'] as const) {
      for (let facing = 0; facing < 4; facing++) {
        const phases = new Set<number>();
        for (let phase = 0; phase < 8; phase++) {
          const sprite = paintActor(false, facing, phase, 1.5, tone);
          const ctx = sprite.canvas.getContext('2d');
          if (!ctx) throw new Error('Missing actor canvas');
          const { width: w, height: h } = sprite.canvas,
            pixels = ctx.getImageData(0, 0, w, h).data;
          let hash = 2166136261,
            painted = 0;
          for (let y = 0; y < h; y++)
            for (let x = 0; x < w; x++) {
              const i = (y * w + x) * 4,
                alpha = pixels[i + 3];
              if (alpha) painted++;
              if (alpha && (x === 0 || y === 0 || x === w - 1 || y === h - 1))
                failures.push('clipped actor');
              for (let k = 0; k < 4; k++) hash = Math.imul(hash ^ pixels[i + k], 16777619) >>> 0;
            }
          if (!painted) failures.push('empty actor');
          phases.add(hash);
          if (tone === 'violet' && phase === 0) directions.push(hash);
          if (facing === 1 && phase === 0) palettes.push(hash);
          const row = [0, 1, 2, 5, 6].indexOf(phase);
          if (tone === 'violet' && row >= 0) {
            const x = facing * 150 + 75,
              y = row * 160 + 140;
            c.fillStyle = '#344a4d';
            c.font = '12px system-ui';
            c.textAlign = 'center';
            c.fillText(`Direction ${facing} / phase ${phase}`, x, y - 120);
            c.drawImage(
              sprite.canvas,
              x - sprite.anchorX,
              y - sprite.anchorY,
              sprite.width,
              sprite.height
            );
          }
          sprite.canvas.width = 0;
        }
        if (phases.size < 4) failures.push('walk cycle collapsed');
      }
    }
    document.body.appendChild(sheet);
    return {
      failures: [...new Set(failures)],
      directions: new Set(directions).size,
      palettes: new Set(palettes).size,
    };
  });
  expect(result).toEqual({ failures: [], directions: 4, palettes: 6 });
  await page.locator('#world-actor-sheet').screenshot({ path: info.outputPath('actor-sheet.png') });
});

for (const condition of [null, 'Rain', 'Snow', 'Fog'] as const) {
  test(`world artwork: native private clock and weather remain readable at night (${condition ?? 'clear'})`, async ({
    page,
    authenticate,
    mockApi,
  }, info) => {
    const user = await authenticate();
    await installInertWorldAdmission(page, user.id);
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    const now = Date.parse('2026-10-23T00:00:00Z');
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.name));
    await mockApi([
      {
        url: '**/api/v1/world/environment',
        json: {
          server_time: now / 1000,
          timezone: 'Europe/Paris',
          weather: condition
            ? {
                temperature_c: 4,
                condition_code: condition,
                wind_speed_kmh: 3,
                observed_at: new Date(now - 60000).toISOString(),
                expires_at: new Date(now + 3600000).toISOString(),
              }
            : null,
        },
      },
    ]);
    await page.goto('/fr/dashboard/world');
    await page.locator('.world-admission input[type="checkbox"]').check();
    await page.locator('.world-admission button[type="submit"]').click();
    await expect(page.locator('canvas.world-canvas')).toBeVisible();
    await expect(
      page.locator('.world-heading').getByText(fr.world.atmosphere.night, { exact: true })
    ).toBeVisible();
    await page.getByRole('button', { name: fr.world.metrics, exact: true }).click();
    await expect
      .poll(async () =>
        Number((await page.locator('[data-world-fps]').innerText()).replace(',', '.'))
      )
      .toBeGreaterThan(0);
    await page.getByRole('button', { name: fr.world.close_metrics, exact: true }).click();
    await page.screenshot({ path: info.outputPath(`art-night-${condition ?? 'clear'}.png`) });
    const map = page.getByRole('button', { name: /^Carte du monde/ });
    const bounds = await map.boundingBox();
    if (!bounds) throw new Error('Missing minimap');
    const target = onSite({ x: POND.x + POND.width / 2, y: POND.y + POND.height / 2 });
    await map.click({
      position: {
        x:
          ((target.x - target.y + WORLD.height + 4) / (WORLD.width + WORLD.height + 8)) *
          bounds.width,
        y:
          (((target.x + target.y) / 2 + 4) / ((WORLD.width + WORLD.height) / 2 + 8)) *
          bounds.height,
      },
    });
    await expect(page.getByRole('button', { name: 'Suivre mon personnage' })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    await page.screenshot({ path: info.outputPath(`garden-night-${condition ?? 'clear'}.png`) });

    expect(errors).toEqual([]);
  });
}

test('world lighting: night gently dims indoor floors and every outdoor silhouette alpha', async ({
  page,
}) => {
  await installArtOracle(page);
  const result = await page.evaluate(() => {
    const { world, paintGroundShade, createCamera, shadeSprite, nightStrength, paintProp } =
      window.worldArtOracle;
    const canvas = document.createElement('canvas');
    canvas.width = 200;
    canvas.height = 200;
    const c = canvas.getContext('2d')!;
    const camera = createCamera({ width: 200, height: 200 }, { x: 0.5, y: 0.5 });
    camera.zoom = 1;
    const atmosphere = {
      phase: 'night' as const,
      weather: 'neutral' as const,
      time: null,
      timezone: null,
    };
    const sample = (covered: boolean) => {
      c.fillStyle = '#f0d8b0';
      c.fillRect(0, 0, 200, 200);
      paintGroundShade(
        c,
        {
          ...world,
          zones: covered
            ? [{ ...world.zones[0], x: -20, y: -20, width: 40, height: 40, covered: true }]
            : [],
        },
        camera,
        atmosphere
      );
      return Array.from(c.getImageData(100, 100, 1, 1).data);
    };
    const indoor = sample(true),
      outdoor = sample(false);
    const faults: string[] = [];
    for (const kind of ['parasol', 'tree', 'lamp', 'chair'] as const) {
      const prop = world.props.find(p => p.kind === kind)!;
      const sprite = paintProp(prop, 1.5, false),
        ctx = sprite.canvas.getContext('2d')!;
      const before = ctx.getImageData(0, 0, sprite.canvas.width, sprite.canvas.height).data;
      shadeSprite(sprite, nightStrength('night'));
      const after = ctx.getImageData(0, 0, sprite.canvas.width, sprite.canvas.height).data;
      let darker = 0;
      for (let i = 0; i < before.length; i += 4) {
        if (before[i + 3] !== after[i + 3]) faults.push('alpha ' + kind);
        if (
          before[i + 3] === 255 &&
          before[i] + before[i + 1] + before[i + 2] > after[i] + after[i + 1] + after[i + 2]
        )
          darker++;
      }
      if (!darker) faults.push('no night ' + kind);
      sprite.canvas.width = 0;
    }
    return { indoor, outdoor, faults: [...new Set(faults)] };
  });
  expect(result.indoor[0]).toBeLessThan(240);
  expect(result.indoor[0]).toBeGreaterThan(195);
  expect(result.indoor[3]).toBe(255);
  expect(result.outdoor[0]).toBeLessThan(result.indoor[0] * 0.6);
  expect(result.outdoor[3]).toBe(255);
  expect(result.faults).toEqual([]);
});
