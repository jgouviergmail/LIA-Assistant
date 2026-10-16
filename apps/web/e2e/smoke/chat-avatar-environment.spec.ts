/** Browser geometry and passive ambience: the real widget, with no provider calls. */
import { test, expect, chatRoutes, waitForClockedHydration } from '../fixtures';
import { expectSmileyProjection } from '../fixtures/smiley-projection';
import { expectVolumeProjection } from '../fixtures/volume-projection';

const styles = ['cozmo', 'capsules', 'billes', 'amande', 'traits', 'anneaux', 'smiley'] as const;

const climates = [
  {
    kind: 'cold',
    temperature: 6,
    condition: 'Clear',
    moving: '.lia-ambient-weather--cold',
    rest: [0, 0],
  },
  {
    kind: 'freezing',
    temperature: -4,
    condition: 'Clear',
    moving: '.lia-ambient-weather--freezing',
    rest: [0, 0],
  },
  {
    kind: 'snow',
    temperature: -1,
    condition: 'Snow',
    moving: '.lia-ambient-weather-fall',
    rest: [0, 5.4],
  },
  {
    kind: 'rain',
    temperature: 18,
    condition: 'Rain',
    moving: '.lia-ambient-weather--rain',
    rest: [0, 0],
  },
  {
    kind: 'storm',
    temperature: 18,
    condition: 'Thunderstorm',
    moving: '.lia-ambient-weather--storm',
    rest: [0, 0],
  },
  {
    kind: 'hot',
    temperature: 28,
    condition: 'Clear',
    moving: '.lia-ambient-weather-fan',
    rest: [0, 0],
  },
  {
    kind: 'heat',
    temperature: 34,
    condition: 'Clear',
    moving: '.lia-ambient-weather-sweat',
    rest: [0, 4],
  },
] as const;

for (const climate of climates) {
  test(`${climate.kind} has its own visible weather performance and respects reduced motion`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await page.addInitScript(() => {
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({ state: { visible: true, style: 'smiley', size: 'md' }, version: 0 })
      );
    });
    const now = Date.parse('2026-09-21T12:00:00Z');
    await page.clock.install({ time: now });
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await mockApi([
      ...chatRoutes([]),
      {
        url: '**/api/v1/briefing/companion-context',
        json: {
          timezone: 'UTC',
          weather: {
            temperature_c: climate.temperature,
            condition_code: climate.condition,
            wind_speed_kmh: 5,
            observed_at: new Date(now - 1000).toISOString(),
            expires_at: new Date(now + 120_000).toISOString(),
          },
        },
      },
    ]);
    await page.goto('/en/dashboard/chat');
    const avatar = page.locator('.lia-eyes').last();
    await expect(avatar).toBeVisible();
    await page.clock.runFor(1800);
    const expectedProps = (
      climate.kind === 'snow'
        ? ['cold', 'freezing', 'snow']
        : climate.kind === 'freezing'
          ? ['cold', 'freezing']
          : climate.kind === 'heat'
            ? ['hot', 'heat']
            : [climate.kind]
    ).map(kind => `lia-ambient-weather--${kind}`);
    const visibleProps = () =>
      avatar
        .locator('.lia-ambient-weather')
        .evaluateAll(elements =>
          elements
            .filter(e => Number.parseFloat(getComputedStyle(e).opacity) > 0.01)
            .map(e => e.classList[1])
        );
    await expect.poll(visibleProps).toEqual(expectedProps);
    const prop = avatar.locator(`.lia-ambient-weather--${climate.kind}`);
    // A shared .lia-weather class used to paint the weather card's opaque
    // surface behind the SVG and clip the prop to a rectangular box.
    await expect(prop).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
    await expect(prop).toHaveCSS('background-image', 'none');
    await expect(prop).toHaveCSS('overflow', 'visible');
    // Read the artwork actually painted by the current local raster renderer.
    // Transparent containers alone cannot prove that its bitmap has no rectangle.
    const artwork = await prop.locator('.lia-ambient-prop').evaluateAll(elements =>
      Promise.all(
        elements.map(async element => {
          const url =
            getComputedStyle(element).backgroundImage.match(/url\(["']?(.*?)["']?\)/)?.[1];
          if (!url) throw new Error('The effective weather must load its own artwork');
          const image = new Image();
          image.src = url;
          await image.decode();
          const canvas = document.createElement('canvas');
          canvas.width = image.naturalWidth;
          canvas.height = image.naturalHeight;
          const context = canvas.getContext('2d')!;
          context.drawImage(image, 0, 0);
          const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
          let transparent = 0;
          let painted = 0;
          for (let i = 3; i < pixels.length; i += 4) {
            if (pixels[i] === 0) transparent++;
            else painted++;
          }
          return { transparent, painted };
        })
      )
    );
    expect(artwork.length).toBeGreaterThan(0);
    for (const { transparent, painted } of artwork) {
      expect(transparent).toBeGreaterThan(0);
      expect(painted).toBeGreaterThan(0);
    }
    const moving = ['cold', 'freezing', 'rain', 'storm'].includes(climate.kind)
      ? prop
      : prop.locator(climate.moving);
    const transform = () => moving.evaluate(e => getComputedStyle(e).transform);
    const before = await transform();
    await page.clock.runFor(450);
    // The winter hat follows the head; it has no independent breath animation.
    if (climate.kind !== 'freezing') expect(await transform()).not.toBe(before);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.clock.runFor(64);
    // MediaQueryList change is a browser task, independent of the mocked clock.
    // Observe the whole stationary pose: sway can already be zero while the
    // breath/particles still carry the preceding frame's fall and pulse.
    await expect
      .poll(async () => {
        await page.clock.runFor(64);
        return avatar.evaluate(e => {
          const style = (e as HTMLElement).style;
          return ['sway', 'fall', 'pulse'].map(channel =>
            Number(style.getPropertyValue(`--rig-ambient-${channel}`))
          );
        });
      })
      .toEqual([0, 0.5, 1]);
    // SVG descendants may paint inherited properties after the rig wrote
    // them. Two identical stale frames prove nothing: await the actual rest
    // position (no rotation, particles halfway through their travel).
    await expect
      .poll(async () => {
        await page.clock.runFor(64);
        return moving.evaluate(e => {
          const matrix = new DOMMatrix(getComputedStyle(e).transform);
          // Firefox serialises the matrix in single precision (5.4 reads
          // 5.400000095367432): the rest position is compared at 1e-4 px.
          return [matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f].map(
            // `+ 0` folds a rounded -0 into 0, which toEqual tells apart.
            value => Math.round(value * 1e4) / 1e4 + 0
          );
        });
      })
      .toEqual([1, 0, 0, 1, ...climate.rest]);
    const frozen = await transform();
    await page.clock.runFor(500);
    expect(await transform()).toBe(frozen);
    expect(await visibleProps()).toEqual(expectedProps);
    if (climate.kind === 'hot') {
      const capture = test.info().outputPath('transparent-fan.png');
      await page.screenshot({ path: capture });
      await test.info().attach('transparent-fan', {
        path: capture,
        contentType: 'image/png',
      });
    }
  });
}

for (const style of styles) {
  test(`${style} keeps a compact face and carries its gaze in depth`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(chatRoutes([]));
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.setViewportSize({ width: 375, height: 812 });
    await page.addInitScript(model => {
      // Keep spontaneous gestures/blinks outside this geometry interval.
      // Their random 1.9–5.6s cadence otherwise competes with the gaze oracle.
      // React also uses randomness for renderer/listener identity. Keep these
      // identifiers distinct while pinning avatar gestures to the late range.
      let randomState = 0x12345678;
      Math.random = () => {
        randomState = (Math.imul(randomState, 1664525) + 1013904223) >>> 0;
        return 0.99 + (randomState / 0x100000000) * 0.009;
      };
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({
          state: { visible: true, style: model, size: 'md' },
          version: 0,
        })
      );
    }, style);
    const geometryTime = new Date('2026-09-21T12:00:00Z');
    await page.clock.install({ time: geometryTime });
    // This oracle measures the resting pose and pointer spring, before the
    // spontaneous mouth mimics. Loading a slow page must not age the face.
    await page.clock.pauseAt(new Date((await page.evaluate(() => Date.now())) + 100));
    await page.goto('/en/dashboard/chat');
    const avatar = page.locator(`.lia-eyes[data-style="${style}"]`).last();
    await waitForClockedHydration(page, avatar);
    await expect(avatar).toBeVisible();
    // The actual painted mouth contour, not its empty layout anchor.
    const measure = () =>
      avatar.evaluate(async root => {
        const mouth = root.querySelector('[data-rig-mouth]')!.getBoundingClientRect();
        const textured = root.classList.contains('lia-smiley');
        const eyes = await Promise.all(
          [...root.querySelectorAll('.lia-eye-shape')].map(async eye => {
            const box = eye.getBoundingClientRect();
            if (!textured) return { top: box.top, bottom: box.bottom };
            // The sculpt lives inside a transparent canvas. Measure its painted
            // alpha extent, not that canvas's empty lower margin (15/128px).
            const source =
              getComputedStyle(eye).backgroundImage.match(/^url\(["']?(.*?)["']?\)$/)?.[1];
            if (!source) throw new Error('The real sculpted eye texture is required');
            const image = new Image();
            image.src = source;
            await image.decode();
            const canvas = document.createElement('canvas');
            canvas.width = image.naturalWidth;
            canvas.height = image.naturalHeight;
            const context = canvas.getContext('2d')!;
            context.drawImage(image, 0, 0);
            const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
            let top = canvas.height;
            let bottom = 0;
            for (let y = 0; y < canvas.height; y++) {
              for (let x = 0; x < canvas.width; x++) {
                if (pixels[(y * canvas.width + x) * 4 + 3] <= 8) continue;
                top = Math.min(top, y);
                bottom = Math.max(bottom, y + 1);
              }
            }
            if (bottom <= top) throw new Error('The eye artwork must contain visible alpha');
            return {
              top: box.top + (top / canvas.height) * box.height,
              bottom: box.top + (bottom / canvas.height) * box.height,
            };
          })
        );
        const em = Number.parseFloat(getComputedStyle(root).fontSize);
        const head = root.querySelector<HTMLElement>('.lia-head')!;
        const pair = root.querySelector<HTMLElement>('.lia-eyes-gaze')!;
        const travel = new DOMMatrix(getComputedStyle(pair).transform);
        const jaw = new DOMMatrix(getComputedStyle(root.querySelector('.lia-mouth')!).transform);
        const body = root.querySelector('.lia-avatar-body');
        const boundary = root.querySelector('.lia-raster-face-mask');
        const containment =
          body && boundary
            ? {
                image: getComputedStyle(body).backgroundImage,
                mask: getComputedStyle(boundary).maskImage,
                maskMode: getComputedStyle(boundary).maskMode,
                clip: getComputedStyle(boundary).clipPath,
                sphereReady: body.getAttribute('data-sphere-ready'),
                canvasWidth: body.querySelector('canvas')?.width,
                canvasHeight: body.querySelector('canvas')?.height,
                // smileySphereResolution: the buffer follows the screen's density,
                // clamped to [1, 2] — Desktop Safari renders at 2.
                density: Math.max(1, Math.min(2, devicePixelRatio)),
                sharedHead: boundary.parentElement === head && body.parentElement === head,
                bodyTransform: getComputedStyle(body).transform,
                eyesInside: boundary.contains(pair),
                mouthInside: boundary.contains(root.querySelector('.lia-mouth')),
                browsOutside: !boundary.querySelector('[data-rig-brow]'),
                pairX: travel.m41,
                pairY: travel.m42,
                mouthX: jaw.m41,
                mouthY: jaw.m42,
              }
            : null;
        return {
          expression: root.getAttribute('data-expression'),
          gesture: root.getAttribute('data-gesture'),
          blink: Math.max(
            ...['--rig-blink-l', '--rig-blink-r'].map(key =>
              Number.parseFloat((root as HTMLElement).style.getPropertyValue(key))
            )
          ),
          gap: (mouth.top - Math.max(...eyes.map(e => e.bottom))) / em,
          mouthHeight: mouth.height / em,
          halfPixel: 0.5 / em,
          containment,
          yaw: Number.parseFloat((root as HTMLElement).style.getPropertyValue('--rig-head-yaw')),
          transform: getComputedStyle(root.querySelector('.lia-head')!).transform,
        };
      });
    const measureOpen = async () => {
      let frame = await measure();
      // A closed eyelid's lower edge is not the face's resting eye baseline.
      for (let attempt = 0; frame.blink > 0.01 && attempt < 30; attempt++) {
        await page.clock.runFor(32);
        frame = await measure();
      }
      expect(frame.blink).toBeLessThanOrEqual(0.01);
      return frame;
    };
    await page.clock.runFor(1200);
    const resting = await measureOpen();
    expect(resting.gap).toBeGreaterThan(0.12); // Visible breathing room below the painted eyes.
    expect(resting.gap).toBeLessThan(style === 'smiley' ? 0.26 : 0.4);
    // Native depth/breathing can move the contour by a fraction of a pixel.
    expect(resting.mouthHeight).toBeLessThan(0.22 + resting.halfPixel);
    await page.mouse.move(5, 40);
    // Pointer input is sampled in a frame, then committed by React. Advancing
    // the entire spring interval before that commit races WebKit's task queue.
    await page.clock.runFor(32);
    await expect
      .poll(async () => Number(await avatar.getAttribute('data-gaze-x')))
      .toBeLessThan(-0.1);
    await page.clock.runFor(1800);
    const looking = await measureOpen();
    expect(Math.abs(looking.yaw)).toBeGreaterThan(0.05);
    if (style === 'smiley') await expectSmileyProjection(avatar);
    else await expectVolumeProjection(avatar);
    expect(looking.gap, JSON.stringify(looking)).toBeLessThan(0.5);
    expect(looking.gap).toBeGreaterThan(0.02);
    if (style === 'smiley') {
      const widget = page.getByRole('group', { name: /LIA's expressive eyes/ });
      await widget.focus();
      for (let move = 0; move < 20; move++) await page.keyboard.press('ArrowLeft');
      await page.clock.runFor(232);
      const box = await avatar.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x + box!.width / 2).toBeLessThan(200);
      await page.mouse.move(370, box!.y + box!.height / 2);
      await page.clock.runFor(32);
      await expect
        .poll(async () => Number(await avatar.getAttribute('data-gaze-x')))
        .toBeGreaterThan(0.9);
      await page.clock.runFor(1300);
      const turned = await measure();
      expect(turned.yaw).toBeGreaterThan(0.9);
      // The real analytic sphere and organs share the projected head. Its
      // exact circular silhouette replaces the fallback bitmap alpha mask.
      expect(turned.containment).not.toBeNull();
      expect(turned.containment!.image).toContain('radial-gradient');
      expect(turned.containment!.sphereReady).toBe('true');
      // The md face (30 px font, 2.6 em sphere) at the page's own density.
      const buffer = Math.min(192, Math.ceil(30 * 2.6 * turned.containment!.density));
      expect(turned.containment!.canvasWidth).toBe(buffer);
      expect(turned.containment!.canvasHeight).toBe(buffer);
      expect(turned.containment!.mask).toBe('none');
      expect(['circle(49%)', 'circle(49% at 50% 50%)']).toContain(turned.containment!.clip);
      expect(turned.containment!.sharedHead).toBe(true);
      expect(turned.containment!.bodyTransform).toBe('none');
      expect(turned.containment!.eyesInside).toBe(true);
      expect(turned.containment!.mouthInside).toBe(true);
      expect(turned.containment!.browsOutside).toBe(true);
      expect(turned.containment!.pairX).toBeCloseTo(turned.containment!.mouthX, 3);
      expect(turned.containment!.pairY).toBeCloseTo(turned.containment!.mouthY, 3);
    }
  });
}

test('weather persists through the answer, expires, and keeps the account clock', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate();
  const now = Date.parse('2026-09-21T12:00:00Z');
  await page.clock.install({ time: now });
  await mockApi([
    ...chatRoutes([]),
    {
      url: '**/api/v1/briefing/companion-context',
      json: {
        timezone: 'Australia/Perth', // Evening, though the test device is at noon UTC.
        weather: {
          temperature_c: 8,
          condition_code: 'Rain',
          wind_speed_kmh: 20,
          observed_at: new Date(now - 1000).toISOString(),
          expires_at: new Date(now + 120_000).toISOString(),
        },
      },
    },
  ]);
  await page.addInitScript(() =>
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({
        state: { visible: true, style: 'smiley', size: 'md' },
        version: 0,
      })
    )
  );
  await page.goto('/en/dashboard/chat');
  const avatar = page.locator('.lia-eyes[data-style="smiley"]').last();
  await expect(avatar).toBeVisible();
  const opacity = (kind: string) =>
    avatar
      .locator(`.lia-ambient-weather--${kind}`)
      .evaluate(e => Number.parseFloat(getComputedStyle(e).opacity));
  await page.clock.runFor(1000);
  await expect.poll(() => opacity('rain')).toBeCloseTo(1, 1);
  expect(await opacity('night')).toBe(0);
  expect(await opacity('cold')).toBeCloseTo(1, 1); // Rain and a worn scarf compose.
  // Freeze wall time after loading so a slow renderer cannot consume the whole
  // answer hold before the test sees the completed message.
  await page.clock.pauseAt(new Date((await page.evaluate(() => Date.now())) + 100));
  await page.locator('textarea').fill('Contrôle de la réponse');
  await page.locator('textarea').press('Enter');
  await expect
    .poll(async () => {
      await page.clock.runFor(32);
      return page.getByText('Voici le point.', { exact: true }).isVisible();
    })
    .toBe(true);
  await expect
    .poll(async () => {
      await page.clock.runFor(32);
      return opacity('rain');
    })
    .toBeCloseTo(1, 1);
  await page.clock.runFor(1500);
  expect(await opacity('rain')).toBeCloseTo(1, 1);
  await page.clock.runFor(12_000);
  expect(await opacity('rain')).toBeCloseTo(1, 1);
  await page.clock.runFor(130_000);
  expect(await opacity('rain')).toBe(0);
  expect(await opacity('night')).toBe(0);
  expect(
    await avatar.evaluate(e =>
      Number.parseFloat((e as HTMLElement).style.getPropertyValue('--rig-light-warm'))
    )
  ).toBeCloseTo(0.65, 1);
});

test('night-time attitude and lighting follow the account rather than the device', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate();
  await page.clock.install({ time: new Date('2026-09-21T12:00:00Z') });
  await mockApi([
    ...chatRoutes([]),
    {
      url: '**/api/v1/briefing/companion-context',
      json: { timezone: 'Pacific/Auckland', weather: null },
    },
  ]);
  await page.addInitScript(() =>
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({
        state: { visible: true, style: 'smiley', size: 'md' },
        version: 0,
      })
    )
  );
  await page.goto('/en/dashboard/chat');
  const avatar = page.locator('.lia-eyes[data-style="smiley"]').last();
  await expect(avatar).toBeVisible();
  await page.clock.runFor(1500);
  await expect(avatar).toHaveAttribute('data-expression', 'sleepy');
  expect(
    await avatar.evaluate(e =>
      Number.parseFloat((e as HTMLElement).style.getPropertyValue('--rig-light-cool'))
    )
  ).toBe(1);
});
