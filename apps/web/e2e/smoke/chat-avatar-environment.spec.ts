/** Browser geometry and passive ambience: the real widget, with no provider calls. */
import { test, expect, chatRoutes } from '../fixtures';

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
    moving: '.lia-ambient-weather-breath',
    rest: [4, 0],
  },
  {
    kind: 'snow',
    temperature: -1,
    condition: 'Snow',
    moving: '.lia-ambient-weather-fall',
    rest: [0, 13],
  },
  {
    kind: 'rain',
    temperature: 18,
    condition: 'Rain',
    moving: '.lia-ambient-weather-fall',
    rest: [0, 8],
  },
  {
    kind: 'storm',
    temperature: 18,
    condition: 'Thunderstorm',
    moving: '.lia-ambient-weather-fall',
    rest: [-4, 9],
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
    const visibleProps = () =>
      avatar
        .locator('.lia-ambient-weather')
        .evaluateAll(elements =>
          elements
            .filter(e => Number.parseFloat(getComputedStyle(e).opacity) > 0.01)
            .map(e => e.classList[1])
        );
    await expect.poll(visibleProps).toEqual([`lia-ambient-weather--${climate.kind}`]);
    const prop = avatar.locator(`.lia-ambient-weather--${climate.kind}`);
    // A shared .lia-weather class used to paint the weather card's opaque
    // surface behind the SVG and clip the prop to a rectangular box.
    await expect(prop).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
    await expect(prop).toHaveCSS('background-image', 'none');
    await expect(prop).toHaveCSS('overflow', 'visible');
    await expect(prop.locator('svg')).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
    if (climate.kind === 'hot') {
      // Inspect the actual inline artwork, including the inactive props. A
      // transparent wrapper cannot rescue an opaque rectangle inside an SVG.
      const artwork = await avatar.locator('.lia-ambient-weather svg').evaluateAll(async svgs => {
        return Promise.all(
          svgs.map(async element => {
            const svg = element as SVGSVGElement;
            const { width, height } = svg.viewBox.baseVal;
            const source = svg.cloneNode(true) as SVGSVGElement;
            source.setAttribute('width', String(width));
            source.setAttribute('height', String(height));
            source.style.color = getComputedStyle(svg).color;
            const image = new Image();
            image.src = `data:image/svg+xml,${encodeURIComponent(new XMLSerializer().serializeToString(source))}`;
            await image.decode();
            const canvas = document.createElement('canvas');
            canvas.width = width;
            canvas.height = height;
            const context = canvas.getContext('2d')!;
            context.drawImage(image, 0, 0);
            const pixels = context.getImageData(0, 0, width, height).data;
            let transparent = 0;
            let painted = 0;
            for (let i = 3; i < pixels.length; i += 4) {
              if (pixels[i] === 0) transparent++;
              else painted++;
            }
            return { kind: svg.parentElement!.classList[1], transparent, painted };
          })
        );
      });
      expect(artwork).toHaveLength(10);
      for (const { kind, transparent, painted } of artwork) {
        expect(transparent, `${kind} has transparent space around its silhouette`).toBeGreaterThan(
          0
        );
        expect(painted, `${kind} contains visible artwork`).toBeGreaterThan(0);
      }
    }
    const moving = climate.kind === 'cold' ? prop : prop.locator(climate.moving);
    const transform = () => moving.evaluate(e => getComputedStyle(e).transform);
    const before = await transform();
    await page.clock.runFor(450);
    expect(await transform()).not.toBe(before);
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
          return [matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f];
        });
      })
      .toEqual([1, 0, 0, 1, ...climate.rest]);
    const frozen = await transform();
    await page.clock.runFor(500);
    expect(await transform()).toBe(frozen);
    expect(await visibleProps()).toEqual([`lia-ambient-weather--${climate.kind}`]);
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
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({
          state: { visible: true, style: model, size: 'md' },
          version: 0,
        })
      );
    }, style);
    await page.clock.install({ time: new Date('2026-09-21T12:00:00Z') });
    await page.goto('/en/dashboard/chat');
    const avatar = page.locator(`.lia-eyes[data-style="${style}"]`).last();
    await expect(avatar).toBeVisible();
    // The actual painted mouth contour, not its empty layout anchor.
    const measure = () =>
      avatar.evaluate(root => {
        const mouth = root.querySelector('[data-rig-mouth]')!.getBoundingClientRect();
        const eyes = [...root.querySelectorAll('.lia-eye-shape')].map(e =>
          e.getBoundingClientRect()
        );
        const em = Number.parseFloat(getComputedStyle(root).fontSize);
        const head = root.querySelector<HTMLElement>('.lia-head')!;
        const pair = root.querySelector<HTMLElement>('.lia-eyes-gaze')!;
        const origin = getComputedStyle(head).transformOrigin.split(' ').map(Number.parseFloat);
        const turn = new DOMMatrix(getComputedStyle(head).transform);
        const travel = new DOMMatrix(getComputedStyle(pair).transform);
        // The sphere's counter-rotation leaves its front plane at z=0.
        // Every eye corner must remain in front; otherwise the far eye is sliced.
        const depths = [...root.querySelectorAll<HTMLElement>('.lia-eye')].flatMap(eye =>
          [0, eye.offsetWidth].flatMap(x =>
            [0, eye.offsetHeight].map(y => {
              const moved = travel.transformPoint(
                new DOMPoint(x + eye.offsetLeft, y + eye.offsetTop, 0)
              );
              return turn.transformPoint(
                new DOMPoint(
                  moved.x + pair.offsetLeft - origin[0],
                  moved.y + pair.offsetTop - origin[1],
                  moved.z
                )
              ).z;
            })
          )
        );
        return {
          blink: Math.max(
            ...['--rig-blink-l', '--rig-blink-r'].map(key =>
              Number.parseFloat((root as HTMLElement).style.getPropertyValue(key))
            )
          ),
          gap: (mouth.top - Math.max(...eyes.map(e => e.bottom))) / em,
          mouthHeight: mouth.height / em,
          minEyeDepth: Math.min(...depths) / em,
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
    expect(resting.mouthHeight).toBeLessThan(0.22);
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
    expect(looking.transform).toMatch(/^matrix3d\(/);
    expect(looking.gap, JSON.stringify(looking)).toBeLessThan(0.5);
    expect(looking.gap).toBeGreaterThan(0.02);
    if (style === 'smiley') {
      const widget = page.getByRole('group', { name: /LIA's expressive eyes/ });
      await widget.focus();
      for (let move = 0; move < 20; move++) await page.keyboard.press('ArrowLeft');
      const box = await avatar.boundingBox();
      await page.mouse.move(370, box!.y + box!.height / 2);
      await page.clock.runFor(32);
      await expect
        .poll(async () => Number(await avatar.getAttribute('data-gaze-x')))
        .toBeGreaterThan(0.9);
      await page.clock.runFor(1300);
      const turned = await measure();
      expect(turned.yaw).toBeGreaterThan(0.9);
      expect(turned.minEyeDepth).toBeGreaterThan(0.02);
    }
  });
}

test('weather yields to the answer, expires, and keeps the account clock', async ({
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
  await expect.poll(() => opacity('rain')).toBeCloseTo(0.7, 1);
  expect(await opacity('night')).toBe(0);
  expect(await opacity('cold')).toBe(0); // Rain owns the single ornament slot.
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
    .toBe(0);
  await page.clock.runFor(1500);
  expect(await opacity('rain')).toBe(0);
  await page.clock.runFor(12_000);
  expect(await opacity('rain')).toBeCloseTo(0.7, 1);
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
