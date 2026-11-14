/** Browser geometry and passive ambience: the real widget, with no provider calls. */
import type { Locator, Page } from '@playwright/test';
import {
  test,
  expect,
  chatRoutes,
  waitForClockedHydration,
  waitForMockGate,
  type MockRoute,
} from '../fixtures';
import { expectVolumeProjection } from '../fixtures/volume-projection';
import {
  BROWS_ALONE,
  CROWN_ALONE,
  DROP_ALONE,
  EYES_ALONE,
  FLAKE_ALONE,
  HEAD_ALONE,
  MOUTH_ALONE,
  paintedEyeHeights,
  shootPainted,
} from '../fixtures/organ-paint';

const styles = ['cozmo', 'capsules', 'billes', 'amande', 'traits', 'anneaux'] as const;

const climates = [
  {
    kind: 'cold',
    // A clear noon draws its sun; the freezing cold adds its breath to the frost.
    shows: ['sun', 'cold'],
    temperature: 6,
    condition: 'Clear',
    moving: '.lia-ambient-weather--cold',
    rest: [0, 0],
  },
  {
    kind: 'freezing',
    shows: ['sun', 'cold', 'freezing', 'freezing'],
    temperature: -4,
    condition: 'Clear',
    moving: '.lia-ambient-weather--freezing',
    rest: [0, 0],
  },
  {
    kind: 'snow',
    shows: ['cold', 'freezing', 'freezing', 'snow'],
    temperature: -1,
    condition: 'Snow',
    moving: '.lia-ambient-weather--snow',
    rest: [0, 0],
  },
  {
    kind: 'rain',
    shows: ['rain'],
    temperature: 18,
    condition: 'Rain',
    moving: '.lia-ambient-weather--rain',
    rest: [0, 0],
  },
  {
    kind: 'storm',
    shows: ['storm'],
    temperature: 18,
    condition: 'Thunderstorm',
    moving: '.lia-ambient-weather--storm',
    rest: [0, 0],
  },
  {
    kind: 'hot',
    shows: ['sun', 'hot'],
    temperature: 28,
    condition: 'Clear',
    moving: '.lia-ambient-weather-fan',
    rest: [0, 0],
  },
  {
    kind: 'heat',
    shows: ['sun', 'hot', 'heat'],
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
    await page.addInitScript(holdColdPose => {
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({ state: { visible: true, style: 'cozmo', size: 'md' }, version: 0 })
      );
      if (!holdColdPose) return;
      // Keep the host's spontaneous gestures outside the deliberate turn.
      let state = 0x12345678;
      Math.random = () => {
        state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
        return 0.99 + (state / 0x100000000) * 0.009;
      };
    }, climate.kind === 'cold');
    const now = Date.parse('2026-09-21T12:00:00Z');
    await page.clock.install({ time: now });
    if (climate.kind === 'cold') {
      await page.clock.pauseAt(new Date((await page.evaluate(() => Date.now())) + 100));
      // The native life stream gives the test a quiet interval before its first mimic.
      await page.clock.setFixedTime(new Date('2026-09-21T12:00:03.174Z'));
    }
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
    if (climate.kind === 'cold') await waitForClockedHydration(page, avatar);
    await expect(avatar).toBeVisible();
    await page.clock.runFor(1800);
    const expectedProps = climate.shows.map(kind => `lia-ambient-weather--${kind}`);
    const visibleProps = () =>
      avatar
        .locator('.lia-ambient-weather')
        .evaluateAll(elements =>
          elements
            .filter(e => Number.parseFloat(getComputedStyle(e).opacity) > 0.01)
            .map(e => e.classList[1])
        );
    await expect.poll(visibleProps).toEqual(expectedProps);
    const prop = avatar.locator(`.lia-ambient-weather--${climate.kind}`).first();
    // A shared .lia-weather class used to paint the weather card's opaque
    // surface behind the SVG and clip the prop to a rectangular box.
    await expect(prop).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
    await expect(prop).toHaveCSS('background-image', 'none');
    await expect(prop).toHaveCSS('overflow', 'visible');
    // Read the artwork actually painted by the current local raster renderer.
    // Transparent containers alone cannot prove that its bitmap has no rectangle.
    const painters = climate.kind === 'cold' ? '.lia-scarf-material > span' : '.lia-ambient-prop';
    const artwork = await prop.locator(painters).evaluateAll(
      (elements, pseudo) =>
        Promise.all(
          elements.map(async element => {
            const url = getComputedStyle(element, pseudo).backgroundImage.match(
              /url\(["']?(.*?)["']?\)/
            )?.[1];
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
        ),
      climate.kind === 'cold' ? '::before' : null
    );
    expect(artwork.length).toBeGreaterThan(0);
    for (const { transparent, painted } of artwork) {
      expect(transparent).toBeGreaterThan(0);
      expect(painted).toBeGreaterThan(0);
    }
    const moving =
      climate.kind === 'cold'
        ? prop.locator('.lia-scarf-tail')
        : ['freezing', 'rain', 'storm', 'snow'].includes(climate.kind)
          ? prop
          : prop.locator(climate.moving);
    const transform = () => moving.evaluate(e => getComputedStyle(e).transform);
    // A scarf the native cloth draws has no fallback to read: see below.
    const before = climate.kind === 'cold' ? null : await transform();
    await page.clock.runFor(450);
    if (climate.kind === 'cold') {
      await expect(avatar).toHaveAttribute('data-volume-scarf-ready', 'true');
      // While the native cloth is drawn, its fitted fallback is out of the
      // style tree. Kept invisible instead, it was restyled on every frame
      // for nothing (four elements here, thirty-eight on a closed collar).
      const fallbackInStyleTree = () => prop.evaluate(e => getComputedStyle(e).display !== 'none');
      expect(await fallbackInStyleTree()).toBe(false);
      const nativeDrape = () =>
        avatar.locator('[data-volume-canvas]').evaluate(node => {
          const gl = (node as HTMLCanvasElement).getContext('webgl');
          const program = gl?.getParameter(gl.CURRENT_PROGRAM);
          const location = program ? gl?.getUniformLocation(program, 'u_drape') : null;
          const drape = location ? gl?.getUniform(program, location) : null;
          if (!(drape instanceof Float32Array))
            throw new Error('The cold scarf draw must provide native drape');
          return [drape[0], drape[1]];
        });
      const trailing = () =>
        expect
          .poll(async () => {
            await page.clock.runFor(16);
            const [shear] = await nativeDrape();
            return Math.abs(shear);
          })
          .toBeGreaterThan(0.02);
      const [restShear, seam] = await nativeDrape();
      expect(Number.isFinite(seam)).toBe(true);
      expect(restShear).toBe(0);
      await page.mouse.move(5, 40);
      await trailing();
      expect((await nativeDrape())[1]).toBe(seam);
      await page.clock.runFor(1100);
      expect(await nativeDrape()).toEqual([0, seam]);
      // Lose the native cloth while it trails again: the fallback is back at
      // once, sheared exactly as the cloth was, on a band that stays attached.
      const viewport = page.viewportSize();
      if (!viewport) throw new Error('The cold scarf test requires a viewport');
      await page.mouse.move(viewport.width - 5, 40);
      await trailing();
      const [nativeShear] = await nativeDrape();
      await avatar.locator('[data-volume-canvas]').evaluate(canvas => {
        const gl = (canvas as HTMLCanvasElement).getContext('webgl');
        const extension = gl?.getExtension('WEBGL_lose_context');
        if (!extension) throw new Error('The test browser must support native context loss');
        extension.loseContext();
      });
      await expect(avatar).toHaveAttribute('data-volume-scarf-ready', 'false');
      expect(await fallbackInStyleTree()).toBe(true);
      const fallbackMatrix = () =>
        moving.evaluate(e => {
          const matrix = new DOMMatrix(getComputedStyle(e).transform);
          return [matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f];
        });
      const bandTransform = () =>
        prop.locator('.lia-scarf-band').evaluate(e => getComputedStyle(e).transform);
      expect((await fallbackMatrix())[2]).toBeCloseTo(nativeShear, 3);
      const attached = await bandTransform();
      await page.clock.runFor(1100);
      // Back at rest the free end carries no transform at all, not only no
      // shear: cold weather alone starts no movement of the garment.
      expect(await fallbackMatrix()).toEqual([1, 0, 0, 1, 0, 0]);
      expect(await bandTransform()).toBe(attached);
    } else if (climate.kind !== 'freezing') {
      expect(await transform()).not.toBe(before);
    }
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
    if (climate.kind === 'cold') {
      const viewport = page.viewportSize();
      if (!viewport) throw new Error('The cold scarf test requires a viewport');
      await page.mouse.move(viewport.width - 5, viewport.height - 5);
    }
    await page.clock.runFor(500);
    expect(await transform()).toBe(frozen);
    if (climate.kind === 'cold') {
      const trail = await avatar.evaluate(e =>
        Number((e as HTMLElement).style.getPropertyValue('--rig-scarf-trail'))
      );
      expect(trail).toBe(0);
    }
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
        const eyes = [...root.querySelectorAll('.lia-eye-shape')].map(eye => {
          const box = eye.getBoundingClientRect();
          return { top: box.top, bottom: box.bottom };
        });
        const em = Number.parseFloat(getComputedStyle(root).fontSize);
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
    expect(resting.gap).toBeLessThan(0.4);
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
    await expectVolumeProjection(avatar);
    expect(looking.gap, JSON.stringify(looking)).toBeLessThan(0.5);
    expect(looking.gap).toBeGreaterThan(0.02);
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
        state: { visible: true, style: 'cozmo', size: 'md' },
        version: 0,
      })
    )
  );
  await page.goto('/en/dashboard/chat');
  const avatar = page.locator('.lia-eyes[data-style="cozmo"]').last();
  await expect(avatar).toBeVisible();
  const opacity = (kind: string) =>
    avatar
      .locator(`.lia-ambient-weather--${kind}`)
      .evaluate(e => Number.parseFloat(getComputedStyle(e).opacity));
  // A prop is in the style tree only while its weather is announced: a slot
  // held at zero opacity is restyled on every frame the rig writes.
  const inStyleTree = (kind: string) =>
    avatar
      .locator(`.lia-ambient-weather--${kind}`)
      .evaluate(e => getComputedStyle(e).display !== 'none');
  await page.clock.runFor(1000);
  await expect.poll(() => opacity('rain')).toBeCloseTo(1, 1);
  expect(await opacity('night')).toBe(0);
  expect(await opacity('cold')).toBeCloseTo(1, 1); // Rain and a worn scarf compose.
  expect(await inStyleTree('rain')).toBe(true);
  expect(await inStyleTree('cold')).toBe(true);
  expect(await inStyleTree('night')).toBe(false);
  expect(await inStyleTree('snow')).toBe(false);
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
  // The weather expired: its props left the style tree with it.
  expect(await inStyleTree('rain')).toBe(false);
  expect(await inStyleTree('cold')).toBe(false);
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
        state: { visible: true, style: 'cozmo', size: 'md' },
        version: 0,
      })
    )
  );
  await page.goto('/en/dashboard/chat');
  const avatar = page.locator('.lia-eyes[data-style="cozmo"]').last();
  await expect(avatar).toBeVisible();
  await page.clock.runFor(1500);
  await expect(avatar).toHaveAttribute('data-expression', 'sleepy');
  expect(
    await avatar.evaluate(e =>
      Number.parseFloat((e as HTMLElement).style.getPropertyValue('--rig-light-cool'))
    )
  ).toBe(1);
});

/**
 * Elements under the default avatar that have a box when there is no weather:
 * the measure of what the avatar costs. The rig's channels are inherited
 * custom properties on its root, so every write restyles the tree below it,
 * and what is under a `display: none` is all the browser skips. Measured on
 * the public page (2026-11-11): 100 elements mounted, 94 of them with a box,
 * ~375 ms of style recalculation per second; 59 were props with no weather.
 * A ceiling that only ever goes DOWN: raising it means the avatar got heavier,
 * and takes a measurement of its frame cost first.
 */
const AVATAR_RENDERED_ELEMENTS_MAX = 35;

/**
 * What the sky of an ordinary day adds, at most: the sun, its turning rays and
 * a cloud passing before it (ADR-294, follow-up of 2026-11-13). It is there
 * most days, so it is drawn on as few boxes as it can. Measured before it was
 * allowed (dev server, BIP, median of three 20 s windows): 132.5 ms/s of style
 * recalculation with no weather, 133.7 under a clear sky, 138.3 under a cloudy
 * one.
 */
const ORDINARY_SKY_ELEMENTS = 3;

/** What is in the style tree under the avatar: its weather slots, and every
 * element with a box (neither `display: none` nor under one). */
const styleTreeCensus = (avatar: Locator) =>
  avatar.evaluate(root => {
    const mounted = [...root.querySelectorAll('*')];
    return {
      slots: [...root.querySelectorAll('.lia-ambient-weather')].map(
        slot => getComputedStyle(slot).display
      ),
      mounted: mounted.length,
      rendered: mounted.filter(element => element.checkVisibility()).length,
    };
  });

test('a prop with no weather is out of the style tree, and the avatar stays light', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate();
  // Noon, no weather: no prop has anything to show.
  await page.clock.install({ time: new Date('2026-09-21T12:00:00Z') });
  await mockApi([
    ...chatRoutes([]),
    {
      url: '**/api/v1/briefing/companion-context',
      json: { timezone: 'UTC', weather: null },
    },
  ]);
  await page.addInitScript(() =>
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({ state: { visible: true, style: 'bip', size: 'md' }, version: 0 })
    )
  );
  await page.goto('/en/dashboard/chat');
  const avatar = page.locator('[data-character="bip"] .lia-eyes').last();
  await expect(avatar).toBeVisible();
  await page.clock.runFor(1500);
  const census = await styleTreeCensus(avatar);
  expect(census.slots.length).toBeGreaterThan(0);
  expect([...new Set(census.slots)]).toEqual(['none']);
  expect(census.rendered, JSON.stringify(census)).toBeLessThanOrEqual(AVATAR_RENDERED_ELEMENTS_MAX);
});

test('a scarf the native cloth draws costs the avatar nothing more', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate();
  // The native cloth only runs with motion on.
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  const now = Date.parse('2026-09-21T12:00:00Z');
  await page.clock.install({ time: now });
  await mockApi([
    ...chatRoutes([]),
    {
      url: '**/api/v1/briefing/companion-context',
      json: {
        timezone: 'UTC',
        weather: {
          temperature_c: 6,
          condition_code: 'Clear',
          wind_speed_kmh: 5,
          observed_at: new Date(now - 1000).toISOString(),
          expires_at: new Date(now + 120_000).toISOString(),
        },
      },
    },
  ]);
  await page.addInitScript(() =>
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({ state: { visible: true, style: 'bip', size: 'md' }, version: 0 })
    )
  );
  await page.goto('/en/dashboard/chat');
  const avatar = page.locator('[data-character="bip"] .lia-eyes').last();
  await expect(avatar).toBeVisible();
  await page.clock.runFor(1500);
  // The closed collar is worn, and it is the native cloth that draws it; a
  // clear noon draws its sun beside it.
  await expect(avatar).toHaveAttribute('data-weather-props', 'cold sun');
  await expect(avatar).toHaveAttribute('data-volume-scarf-ready', 'true');
  // Its fitted fallback — thirty-eight elements on this collar: thirty-two
  // facets, the knot, the tail and their wrappers — is out of the style
  // tree: the avatar is as light as with no weather at all.
  const census = await styleTreeCensus(avatar);
  expect([...new Set(census.slots)].sort()).toEqual(['block', 'none']);
  // The sun and its rays; no cloud passes on a clear day.
  expect(census.rendered, JSON.stringify(census)).toBeLessThanOrEqual(
    AVATAR_RENDERED_ELEMENTS_MAX + ORDINARY_SKY_ELEMENTS - 1
  );
});

/** When the reading of the journeys is observed, from the start of the clock. */
const START = Date.parse('2026-09-21T12:00:00Z');

/** The chat, a living companion at rest, and one observed weather — observed
 * from `observedAt`, so a journey can see the same face before and after it. */
async function openUnder(
  page: Page,
  mockApi: (routes: MockRoute[]) => Promise<void>,
  weather: { temperature_c: number; condition_code: string; wind_speed_kmh: number },
  {
    style = 'bip',
    size = 'md',
    variant = 'female',
    observedAt = START - 1000,
    timezone = 'UTC',
  }: {
    style?: string;
    size?: string;
    variant?: 'male' | 'female';
    observedAt?: number;
    timezone?: string;
  } = {}
): Promise<Locator> {
  const now = START;
  await page.addInitScript(
    ({ variant, ...chosen }) => {
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({ state: { visible: true, ...chosen }, version: 0 })
      );
      // The companion's gender is the account's LIA gender, kept in a cookie.
      if (variant === 'male') document.cookie = 'lia_gender=male; path=/';
      // Keep the host's own wandering looks out of a journey about ONE look.
      Math.random = () => 0.995;
    },
    { style, size, variant }
  );
  await page.clock.install({ time: now });
  await page.clock.pauseAt(new Date(now + 1000));
  await mockApi([
    ...chatRoutes([]),
    {
      url: '**/api/v1/briefing/companion-context',
      json: {
        timezone,
        weather: {
          ...weather,
          observed_at: new Date(observedAt).toISOString(),
          expires_at: new Date(now + 600_000).toISOString(),
        },
      },
    },
  ]);
  await page.goto('/en/dashboard/chat');
  const avatar = page.locator('.lia-eyes-widget .lia-eyes').last();
  await waitForClockedHydration(page, avatar);
  await expect(avatar).toBeVisible();
  return avatar;
}

const props = async (page: Page, avatar: Locator) => {
  await page.clock.runFor(96);
  return avatar.getAttribute('data-weather-props');
};

test.describe('weather the character plays', () => {
  test.use({ contextOptions: { reducedMotion: 'no-preference' }, deviceScaleFactor: 4 });

  const channel = (avatar: Locator, name: string) =>
    avatar.evaluate(
      (root, property) => parseFloat((root as HTMLElement).style.getPropertyValue(property) || '0'),
      name
    );

  // Owner report (2026-11-13): the face kept the weather its page opened with until
  // the page was reloaded. LIA reads the person's place many times a day; each newer
  // read is now said on their channel, and the open page takes it (ADR-294).
  test('takes the weather LIA just read, with no reload', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    const NL = String.fromCharCode(10);
    const now = START;
    const reading = (condition: string, observedAt: number) => ({
      timezone: 'UTC',
      weather: {
        temperature_c: 14,
        condition_code: condition,
        wind_speed_kmh: 5,
        observed_at: new Date(observedAt).toISOString(),
        expires_at: new Date(observedAt + 3_600_000).toISOString(),
      },
    });
    let served = reading('Clear', now - 60_000);
    let reads = 0;
    let release!: () => void;
    const said = new Promise<void>(resolve => (release = resolve));
    let signalled = false;
    await page.addInitScript(() => {
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({ state: { visible: true, style: 'bip', size: 'md' }, version: 0 })
      );
      Math.random = () => 0.995;
    });
    await page.clock.install({ time: now });
    await page.clock.pauseAt(new Date(now + 1000));
    await mockApi([
      ...chatRoutes([]),
      {
        url: '**/api/v1/briefing/companion-context',
        handler: async route => {
          reads += 1;
          await route.fulfill({ json: served });
        },
      },
      {
        url: '**/api/v1/notifications/stream',
        handler: async (route, signal) => {
          if (signalled) {
            await route.fulfill({
              status: 200,
              contentType: 'text/event-stream',
              body: ': idle' + NL + NL,
            });
            return;
          }
          if (!(await waitForMockGate(said, signal))) return;
          signalled = true;
          await route.fulfill({
            status: 200,
            contentType: 'text/event-stream',
            body: 'event: notification' + NL + 'data: {"type":"companion_weather"}' + NL + NL,
          });
        },
      },
    ]);
    await page.goto('/en/dashboard/chat');
    const avatar = page.locator('.lia-eyes-widget .lia-eyes').last();
    await waitForClockedHydration(page, avatar);
    await page.evaluate(() => Object.assign(window, { __samePage: true }));
    await expect.poll(() => props(page, avatar)).toBe('sun');
    const readsBefore = reads;

    // It rains now. Read by the heartbeat, say — nothing is said yet: the page waits.
    served = reading('Rain', now);
    await page.clock.runFor(2000);
    expect(await avatar.getAttribute('data-weather-props')).toBe('sun');
    expect(reads).toBe(readsBefore);

    // Said on the person's channel: the same page reads it, at once.
    release();
    await expect.poll(() => props(page, avatar)).toContain('rain');
    expect(reads).toBe(readsBefore + 1);
    expect(await page.evaluate(() => (window as { __samePage?: boolean }).__samePage)).toBe(true);
  });

  test('looks up when the rain arrives, once, then goes back to the person', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // Twelve seconds of the face's own time, a frame at a time: WebKit takes
    // more than the default budget over it on a slow machine.
    test.slow();
    await authenticate();
    const avatar = await openUnder(page, mockApi, {
      temperature_c: 18,
      condition_code: 'Rain',
      wind_speed_kmh: 5,
    });
    // The reading arrives a moment after the face: the look follows it.
    let highest = 0;
    let lookedAt = -1;
    for (let elapsed = 0; elapsed < 6000 && lookedAt < 0; elapsed += 48) {
      await page.clock.runFor(48);
      highest = Math.min(highest, await channel(avatar, '--rig-gaze-y'));
      if (highest < -0.45) lookedAt = elapsed;
    }
    expect(lookedAt, 'the face looks up at the rain').toBeGreaterThanOrEqual(0);
    await expect(avatar).toHaveAttribute('data-weather-props', /rain/);
    await page.clock.runFor(2500);
    expect(Math.abs(await channel(avatar, '--rig-gaze-y'))).toBeLessThan(0.1);
    // The rain goes on; the look does not come back.
    for (let elapsed = 0; elapsed < 8000; elapsed += 96) {
      await page.clock.runFor(96);
      expect(await channel(avatar, '--rig-gaze-y'), `${elapsed} ms later`).toBeGreaterThan(-0.3);
    }
  });

  // A sculpted face and a drawn one: a squash that moved the channel left a
  // sculpted eye untouched in paint (measured: all of its height kept). The
  // POSE is photographed — reduced motion, so no blink, gesture or mimic of
  // the face's own life moves the paint between the two pictures — at the
  // largest size and finely: a 14 % squint is two pixels of a 13 px eye.
  for (const style of ['bip', 'cozmo'] as const) {
    test(`${style} narrows its painted eyes in the wind`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate();
      await page.emulateMedia({ reducedMotion: 'reduce' });
      const avatar = await openUnder(
        page,
        mockApi,
        { temperature_c: 18, condition_code: 'Clear', wind_speed_kmh: 55 },
        { style, size: 'xl', observedAt: START + 30_000 }
      );
      // The reading exists but is not observed yet: the same face, calm.
      await page.clock.runFor(500);
      expect(await avatar.getAttribute('data-weather-props')).toBeNull();
      const calm = await paintedEyeHeights(page, avatar);
      await page.clock.fastForward(30_000);
      await expect
        .poll(async () => {
          await page.clock.runFor(96);
          return avatar.getAttribute('data-weather-props');
        })
        .toMatch(/wind/);
      await page.clock.runFor(500);
      const windy = await paintedEyeHeights(page, avatar);
      for (const side of [0, 1] as const) {
        const kept = windy[side] / calm[side];
        expect(calm[side], `${style}: an eye is painted`).toBeGreaterThan(8);
        expect(kept, `${style}: the painted eye narrows (${side ? 'right' : 'left'})`).toBeLessThan(
          0.9
        );
        expect(kept, `${style}: and stays open (${side ? 'right' : 'left'})`).toBeGreaterThan(0.6);
      }
    });
  }

  /** How many warm, sunlit pixels the browser paints in an element's box. */
  async function warmPixels(page: Page, element: Locator): Promise<number> {
    const box = await element.boundingBox();
    if (!box) throw new Error('The element must be drawn');
    const shot = (await page.screenshot({ clip: box })).toString('base64');
    return page.evaluate(async encoded => {
      const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
      const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
      const canvas = document.createElement('canvas');
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('No 2D context to read the picture with');
      context.drawImage(bitmap, 0, 0);
      const { data } = context.getImageData(0, 0, bitmap.width, bitmap.height);
      let warm = 0;
      for (let i = 0; i < data.length; i += 4)
        if (data[i] > 200 && data[i + 1] > 140 && data[i + 2] < 130) warm += 1;
      return warm;
    }, shot);
  }

  test('draws the sky of an ordinary day — a sun, a cloud passing before it — on three boxes', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    const avatar = await openUnder(page, mockApi, {
      temperature_c: 18,
      condition_code: 'Clouds',
      wind_speed_kmh: 5,
    });
    await expect.poll(() => props(page, avatar)).toBe('sun cloud');
    await page.clock.runFor(1500);
    expect(await warmPixels(page, avatar.locator('.lia-ambient-weather--sun'))).toBeGreaterThan(40);
    // The cloud passes before the sun, on the face's own clock.
    const cloud = avatar.locator('.lia-ambient-weather--cloud');
    const before = await cloud.boundingBox();
    await page.clock.runFor(1200);
    const after = await cloud.boundingBox();
    expect(Math.abs((after?.x ?? 0) - (before?.x ?? 0))).toBeGreaterThan(0.5);
    const census = await styleTreeCensus(avatar);
    expect(census.rendered, JSON.stringify(census)).toBeLessThanOrEqual(
      AVATAR_RENDERED_ELEMENTS_MAX + ORDINARY_SKY_ELEMENTS
    );
  });

  test('keeps the sky for the day: the night has its crescent, and no sun', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    const avatar = await openUnder(
      page,
      mockApi,
      { temperature_c: 14, condition_code: 'Clear', wind_speed_kmh: 5 },
      // Noon in UTC is one in the morning there.
      { timezone: 'Pacific/Auckland' }
    );
    await expect.poll(() => props(page, avatar)).toBe('night');
  });

  for (const fall of [
    { condition: 'Rain', temperature: 14, particle: '.lia-ambient-drop', art: /drop\.svg/ },
    { condition: 'Snow', temperature: -1, particle: '.lia-ambient-flake', art: /snow\.webp/ },
  ] as const)
    test(`lets the ${fall.condition.toLowerCase()} fall from its cloud, and stands it still under reduced motion`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate();
      const avatar = await openUnder(page, mockApi, {
        temperature_c: fall.temperature,
        condition_code: fall.condition,
        wind_speed_kmh: 5,
      });
      await expect
        .poll(() => props(page, avatar))
        .toMatch(new RegExp(fall.condition.toLowerCase()));
      await page.clock.runFor(1500);
      await expect(
        avatar.locator(`.lia-ambient-weather--${fall.condition.toLowerCase()} .lia-ambient-cloud`)
      ).toBeVisible();
      const particles = avatar.locator(fall.particle);
      expect(await particles.first().evaluate(e => getComputedStyle(e).backgroundImage)).toMatch(
        fall.art
      );
      const tops = () =>
        particles.evaluateAll(elements => elements.map(e => e.getBoundingClientRect().top));
      const first = await tops();
      await page.clock.runFor(120);
      const then = await tops();
      // Each one falls, but for the one that wrapped to the top meanwhile.
      const fell = then.filter((top, index) => top > first[index] + 0.3).length;
      expect(fell, JSON.stringify({ first, then })).toBeGreaterThanOrEqual(then.length - 1);
      // What only exists by moving is not drawn standing still.
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await expect
        .poll(async () => {
          await page.clock.runFor(64);
          return particles.evaluateAll(
            elements => elements.filter(e => e.checkVisibility()).length
          );
        })
        .toBe(0);
      await expect(
        avatar.locator(`.lia-ambient-weather--${fall.condition.toLowerCase()} .lia-ambient-cloud`)
      ).toBeVisible();
    });
});

/**
 * Where the frost crown sits on the head the browser paints, in ems of the avatar.
 *
 * Each band is read at its foot, the lowest pixel it paints: `feet` is how deep that
 * pixel is in the painted head, its distance to the nearest pixel that is not head
 * (negative: in the air, that far from the head; null: no head within reach). A
 * distance, not a column: on a steep side a pixel's column says little, and a leaf
 * overhanging it is not the skull. `band` is the bands' thickness, read on the
 * painted artwork; `clearance` is how far above the face (eyes and brows) it ends.
 */
async function crownSeat(page: Page, avatar: Locator) {
  const frame = await avatar.evaluate(root => {
    const box = root.getBoundingClientRect();
    return { ...box.toJSON(), em: parseFloat(getComputedStyle(root).fontSize) };
  });
  // The crystals rise above the frame: the picture takes half a frame more above it.
  const clip = {
    x: frame.x - frame.width * 0.2,
    y: frame.y - frame.height * 0.5,
    width: frame.width * 1.4,
    height: frame.height * 1.5,
  };
  const shots = {
    crown: await shootPainted(page, CROWN_ALONE, clip),
    head: await shootPainted(page, HEAD_ALONE, clip),
    eyes: await shootPainted(page, EYES_ALONE, clip),
    brows: await shootPainted(page, BROWS_ALONE, clip),
  };
  return page.evaluate(
    async ({ shots, cssWidth, em, centre }) => {
      const read = async (encoded: string) => {
        const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
        const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
        const canvas = document.createElement('canvas');
        canvas.width = bitmap.width;
        canvas.height = bitmap.height;
        const context = canvas.getContext('2d');
        if (!context) throw new Error('No 2D context to read the picture with');
        context.drawImage(bitmap, 0, 0);
        return context.getImageData(0, 0, bitmap.width, bitmap.height);
      };
      const [crown, head, eyes, brows] = await Promise.all(
        [shots.crown, shots.head, shots.eyes, shots.brows].map(read)
      );
      const { width, height } = crown;
      const density = width / cssWidth;
      const lit = (picture: ImageData, x: number, y: number) =>
        picture.data[(y * width + x) * 4] >= 128;
      const face = (x: number, y: number) => lit(eyes, x, y) || lit(brows, x, y);
      let left = width;
      let right = -1;
      let bottom = -1;
      let faceTop = height;
      let painted = 0;
      let overHead = 0;
      let overFace = 0;
      for (let y = 0; y < height; y++)
        for (let x = 0; x < width; x++) {
          if (face(x, y)) faceTop = Math.min(faceTop, y);
          if (!lit(crown, x, y)) continue;
          painted += 1;
          left = Math.min(left, x);
          right = Math.max(right, x);
          bottom = y;
          if (lit(head, x, y)) overHead += 1;
          if (face(x, y)) overFace += 1;
        }
      if (painted === 0) throw new Error('No crown is painted');
      const reach = Math.round(0.6 * em * density);
      const depth = (x: number, y: number) => {
        const inside = lit(head, x, y);
        let nearest = Infinity;
        for (let dy = -reach; dy <= reach; dy++)
          for (let dx = -reach; dx <= reach; dx++) {
            const px = x + dx;
            const py = y + dy;
            if (px < 0 || py < 0 || px >= width || py >= height) continue;
            if (lit(head, px, py) !== inside) nearest = Math.min(nearest, Math.hypot(dx, dy));
          }
        if (nearest === Infinity) return inside ? 0.6 : null;
        return (inside ? nearest : -nearest) / density / em;
      };
      const middle = Math.round((left + right) / 2);
      const feet = [
        [left, middle],
        [middle, right + 1],
      ].map(([from, to]) => {
        let lowest = -1;
        let columns: number[] = [];
        for (let x = from; x < to; x++)
          for (let y = height - 1; y >= 0; y--) {
            if (!lit(crown, x, y)) continue;
            if (y > lowest) {
              lowest = y;
              columns = [x];
            } else if (y === lowest) columns.push(x);
            break;
          }
        const x = Math.round(columns.reduce((sum, column) => sum + column, 0) / columns.length);
        return depth(x, lowest);
      });
      return {
        feet,
        // The artwork's band is an eighth of its painted width.
        band: ((right - left + 1) * 0.124) / density / em,
        clearance: (faceTop - bottom) / density / em,
        overHead: overHead / painted,
        overFace,
        offCentre: ((left + right) / 2 / density - centre) / em,
      };
    },
    {
      shots,
      cssWidth: clip.width,
      em: frame.em,
      centre: frame.x + frame.width / 2 - clip.x,
    }
  );
}

/**
 * The frost crown is WORN (owner report 2026-11-13: miscalibrated on the heads of
 * the different models). Measured before (xl, Chromium): its feet sank 0.17 to
 * 0.78 em into sixteen heads of eighteen — two horns on a forehead — and hung in
 * the air beside a tuft on two. Every head now has its own fitted laurel, and the
 * PAINT is the oracle: the head, the crown and the face photographed apart, a
 * static pose (reduced motion), the largest size.
 */
/** Every head: eight characters in two genders, and the monitor (its six drawn
 * faces share one screen, and its two genders one layout). */
const HEADS = [
  ...(['spirit', 'moss', 'lumen', 'nimbo', 'orbit', 'bip', 'boulon', 'oscar'] as const).flatMap(
    style => (['male', 'female'] as const).map(variant => ({ style, variant }))
  ),
  { style: 'cozmo', variant: 'male' } as const,
];

test.describe('the frost crown is worn on every head', () => {
  test.use({ deviceScaleFactor: 2 });

  for (const { style, variant } of HEADS)
    test(`${style} (${variant}) wears its frost crown on its head`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate();
      await page.emulateMedia({ reducedMotion: 'reduce' });
      const avatar = await openUnder(
        page,
        mockApi,
        { temperature_c: -6, condition_code: 'Fog', wind_speed_kmh: 3 },
        { style, variant, size: 'xl' }
      );
      await expect.poll(() => props(page, avatar)).toMatch(/freezing/);
      await page.clock.runFor(500);
      const seat = await crownSeat(page, avatar);
      const told = `${style} (${variant}) ${JSON.stringify(seat)}`;
      for (const [side, sink] of seat.feet.entries()) {
        const band = side ? 'right' : 'left';
        expect(sink, `${told}: the ${band} band stands on the head`).not.toBeNull();
        // Rests ON the edge: not in the air beside the head, and no deeper in it
        // than the band is thick, so the band still crosses the edge at its foot.
        expect(sink, `${told}: the ${band} band is not in the air`).toBeGreaterThanOrEqual(-0.02);
        expect(sink, `${told}: the ${band} band does not dive in`).toBeLessThanOrEqual(
          seat.band + 0.02
        );
      }
      expect(seat.overFace, `${told}: never on an eye or a brow`).toBe(0);
      expect(seat.clearance, `${told}: worn above the face`).toBeGreaterThanOrEqual(0.04);
      expect(seat.overHead, `${told}: its crystals stand above the head`).toBeLessThanOrEqual(0.45);
      expect(Math.abs(seat.offCentre), `${told}: centred on the head`).toBeLessThanOrEqual(0.03);
    });
});

/** Steps the paused clock a frame at a time until `--rig-<channel>` reaches 1: the
 * prop a scene carries has landed. Returns how long it took. */
async function landed(page: Page, avatar: Locator, property: string): Promise<number> {
  for (let elapsed = 0; elapsed <= 8000; elapsed += 16) {
    const value = await avatar.evaluate(
      (root, name) => parseFloat((root as HTMLElement).style.getPropertyValue(name) || '0'),
      property
    );
    if (value >= 1) return elapsed;
    await page.clock.runFor(16);
  }
  throw new Error(`${property} never landed`);
}

/**
 * What a scene carries, where it is painted: the prop alone, the head and the face's
 * organs photographed apart. `gap` is how far above the head the prop's foot is, on
 * its own column (negative: in the head); `overFace` its pixels on an eye, a brow or
 * the mouth; `onFace` whether its centre is on the painted head.
 */
async function propSeat(page: Page, avatar: Locator, kind: 'drop' | 'flake') {
  const frame = await avatar.evaluate(root => {
    const box = root.getBoundingClientRect();
    return { ...box.toJSON(), em: parseFloat(getComputedStyle(root).fontSize) };
  });
  const clip = {
    x: frame.x - frame.width * 0.2,
    y: frame.y - frame.height * 0.5,
    width: frame.width * 1.4,
    height: frame.height * 1.5,
  };
  const shots = {
    prop: await shootPainted(page, kind === 'drop' ? DROP_ALONE : FLAKE_ALONE, clip),
    head: await shootPainted(page, HEAD_ALONE, clip),
    eyes: await shootPainted(page, EYES_ALONE, clip),
    brows: await shootPainted(page, BROWS_ALONE, clip),
    mouth: await shootPainted(page, MOUTH_ALONE, clip),
  };
  return page.evaluate(
    async ({ shots, cssWidth, em, centre }) => {
      const read = async (encoded: string) => {
        const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
        const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
        const canvas = document.createElement('canvas');
        canvas.width = bitmap.width;
        canvas.height = bitmap.height;
        const context = canvas.getContext('2d');
        if (!context) throw new Error('No 2D context to read the picture with');
        context.drawImage(bitmap, 0, 0);
        return context.getImageData(0, 0, bitmap.width, bitmap.height);
      };
      const [prop, head, eyes, brows, mouth] = await Promise.all(
        [shots.prop, shots.head, shots.eyes, shots.brows, shots.mouth].map(read)
      );
      const { width, height } = prop;
      const density = width / cssWidth;
      const lit = (picture: ImageData, x: number, y: number) =>
        picture.data[(y * width + x) * 4] >= 128;
      let left = width;
      let right = -1;
      let top = height;
      let bottom = -1;
      let painted = 0;
      let overFace = 0;
      for (let y = 0; y < height; y++)
        for (let x = 0; x < width; x++) {
          if (!lit(prop, x, y)) continue;
          painted += 1;
          left = Math.min(left, x);
          right = Math.max(right, x);
          top = Math.min(top, y);
          bottom = Math.max(bottom, y);
          if (lit(eyes, x, y) || lit(brows, x, y) || lit(mouth, x, y)) overFace += 1;
        }
      if (painted === 0) throw new Error('Nothing is painted');
      const middle = Math.round((left + right) / 2);
      // What it falls on: the head's highest pixel under any column it paints.
      let headTop = height;
      for (let x = left; x <= right; x++)
        for (let y = 0; y < height; y++)
          if (lit(head, x, y)) {
            headTop = Math.min(headTop, y);
            break;
          }
      return {
        painted,
        gap: (headTop - bottom - 1) / density / em,
        overFace,
        onFace: lit(head, middle, Math.round((top + bottom) / 2)),
        offCentre: ((left + right) / 2 / density - centre) / em,
      };
    },
    {
      shots,
      cssWidth: clip.width,
      em: frame.em,
      centre: frame.x + frame.width / 2 - clip.x,
    }
  );
}

/** Has the page load an artwork, in real time, before the clock moves on: a scene's
 * bitmap is installed only once its prop is announced, while a paused clock plays its
 * fall in a few real milliseconds — a photograph taken before the file arrives is
 * blank. (The resource timeline cannot say it: a dev page fills its 250 entries.) */
async function loaded(page: Page, file: string): Promise<void> {
  const decoded = await page.evaluate(
    url =>
      new Promise<boolean>(resolve => {
        const image = new Image();
        image.onload = () => resolve(true);
        image.onerror = () => resolve(false);
        image.src = url;
      }),
    file
  );
  expect(decoded, `${file} loads`).toBe(true);
}

/** Steps the paused clock until the face plays `scene`; fails when it never does. */
async function playing(page: Page, avatar: Locator, scene: string): Promise<void> {
  for (let elapsed = 0; elapsed <= 6000; elapsed += 16) {
    if ((await avatar.getAttribute('data-scene')) === scene) return;
    await page.clock.runFor(16);
  }
  throw new Error(`the face never played ${scene}`);
}

/**
 * The weather LIVED (owner's choice on the bench, wired 2026-11-13): the first drop of
 * a rain lands ON the head — then only the umbrella opens — and the first flake of a
 * snow settles on the root of the nose, the one place on every face where it covers
 * no eye, brow or mouth. The PAINT is the oracle, on every head, at the largest size,
 * the moment the prop has landed.
 */
test.describe('the first drop and the first flake land where they should', () => {
  test.use({ contextOptions: { reducedMotion: 'no-preference' }, deviceScaleFactor: 2 });

  for (const { style, variant } of HEADS)
    test(`the first drop of a rain lands on ${style} (${variant})'s head`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate();
      const avatar = await openUnder(
        page,
        mockApi,
        { temperature_c: 12, condition_code: 'Rain', wind_speed_kmh: 5 },
        { style, variant, size: 'xl' }
      );
      await playing(page, avatar, 'weather-first-drop');
      await page.clock.runFor(48);
      await loaded(page, '/avatars/sky/v1/drop.svg');
      await landed(page, avatar, '--rig-weather-drop');
      // The face feels it before the rain shows: no cloud, no umbrella yet.
      expect(await avatar.getAttribute('data-weather-props')).toBe('drop');
      const seat = await propSeat(page, avatar, 'drop');
      const told = `${style} (${variant}) ${JSON.stringify(seat)}`;
      expect(seat.gap, `${told}: not in the air above the head`).toBeLessThanOrEqual(0.05);
      expect(seat.gap, `${told}: not sunk in the head`).toBeGreaterThanOrEqual(-0.05);
      expect(Math.abs(seat.offCentre), `${told}: down the middle`).toBeLessThanOrEqual(0.04);
      expect(seat.overFace, `${told}: never on the face`).toBe(0);
      // ...then the umbrella opens, and the drop is gone.
      await page.clock.runFor(2500);
      await expect.poll(() => props(page, avatar)).toBe('rain');
    });

  for (const { style, variant } of [
    ...HEADS,
    // The monitor's other drawn faces: the same screen, eyes of their own.
    ...(['capsules', 'billes', 'amande', 'traits', 'anneaux'] as const).map(face => ({
      style: face,
      variant: 'male' as const,
    })),
  ])
    test(`the first flake of a snow settles on ${style} (${variant})'s nose`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate();
      const avatar = await openUnder(
        page,
        mockApi,
        { temperature_c: -1, condition_code: 'Snow', wind_speed_kmh: 5 },
        { style, variant, size: 'xl' }
      );
      await playing(page, avatar, 'weather-catch-flake');
      await page.clock.runFor(48);
      await loaded(page, '/avatars/context/v1/snow.webp');
      await landed(page, avatar, '--rig-weather-flake');
      const seat = await propSeat(page, avatar, 'flake');
      const told = `${style} (${variant}) ${JSON.stringify(seat)}`;
      expect(seat.onFace, `${told}: on the face`).toBe(true);
      expect(seat.overFace, `${told}: on no eye, brow or mouth`).toBe(0);
      expect(Math.abs(seat.offCentre), `${told}: at the middle of the face`).toBeLessThanOrEqual(
        0.06
      );
      // It melts: the snow stays, the caught flake is gone.
      await page.clock.runFor(1500);
      expect(await avatar.getAttribute('data-weather-props')).not.toMatch(/\bflake\b/);
    });

  test('carries nothing under reduced motion: the weather is simply there', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const avatar = await openUnder(
      page,
      mockApi,
      { temperature_c: 12, condition_code: 'Rain', wind_speed_kmh: 5 },
      { size: 'xl' }
    );
    await expect.poll(() => props(page, avatar)).toBe('rain');
    for (let beat = 0; beat < 40; beat++) {
      await page.clock.runFor(100);
      expect(await avatar.getAttribute('data-scene')).toBe('');
      expect(await avatar.getAttribute('data-weather-props')).toBe('rain');
    }
  });
});
