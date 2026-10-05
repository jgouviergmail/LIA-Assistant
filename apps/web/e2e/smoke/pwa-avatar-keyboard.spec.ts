import { test, expect, loadedChatRoutes, waitForHydration } from '../fixtures';
import { avatarRoutes, installSimliPeer } from '../fixtures/simli';

for (const savedEyes of [false, true]) {
  test(`PWA keyboard pan preserves the chat with saved eyes=${savedEyes}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.setViewportSize({ width: 390, height: 844 });
    await page.addInitScript(saved => {
      Object.defineProperty(navigator, 'standalone', { value: true });
      const match = window.matchMedia.bind(window);
      window.matchMedia = query => {
        const result = match(query);
        if (query.includes('display-mode: standalone'))
          Object.defineProperty(result, 'matches', { value: true });
        return result;
      };
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({
          state: {
            visible: true,
            position: saved ? { xPct: 20, yPct: 20 } : null,
          },
          version: 0,
        })
      );
      localStorage.setItem(
        'lia.avatarWindow',
        JSON.stringify({ state: { size: 'lg', position: { xPct: 20, yPct: 90 } }, version: 0 })
      );
      // Subpixel layout can change between reads while keyboard/media layout settles.
      // An external-store snapshot must remain cached across React's render reads.
      const measure = HTMLElement.prototype.getBoundingClientRect;
      let reads = 0;
      HTMLElement.prototype.getBoundingClientRect = function () {
        const rect = measure.call(this);
        return this.matches('[role="toolbar"]') && this.querySelector('video')
          ? new DOMRect(rect.x, rect.y, rect.width, rect.height + ++reads / 1000)
          : rect;
      };
    }, savedEyes);
    // Geometry is independent of ICE negotiation. Hold signalling pending
    // without asynchronous peer work surviving the end of this layout test.
    await page.routeWebSocket('**/api/v1/avatars/ws?ticket=*', () => {});
    const starts: unknown[] = [];
    const releases: unknown[] = [];
    await authenticate({ voice_enabled: true, speaking_avatar_enabled: true });
    await mockApi([...loadedChatRoutes(), ...avatarRoutes(starts, releases)]);
    await page.goto('/en/dashboard/chat');
    await waitForHydration(page);
    await expect(
      page.getByRole('toolbar', { name: 'Move avatar: drag or use arrow keys' })
    ).toBeVisible();
    // This regression qualifies layout during connection; media qualification
    // uses the separate real loopback journeys and physical device trials.
    await page.locator('textarea').focus();
    for (const offsetTop of [150, 350, 550, 0]) {
      await page.evaluate(top => {
        Object.defineProperty(window, 'innerHeight', { value: 320, configurable: true });
        Object.defineProperty(window.visualViewport!, 'height', { value: 320, configurable: true });
        Object.defineProperty(window.visualViewport!, 'offsetTop', {
          value: top,
          configurable: true,
        });
        window.visualViewport!.dispatchEvent(new Event('resize'));
        window.visualViewport!.dispatchEvent(new Event('scroll'));
        window.dispatchEvent(new Event('resize'));
      }, offsetTop);
      await page.locator('textarea').fill(`Keyboard offset ${offsetTop}`);
      await expect(page.locator('textarea')).toHaveValue(`Keyboard offset ${offsetTop}`);
      await expect(page.getByText('Something went wrong', { exact: true })).toHaveCount(0);
    }
    const position = await page.evaluate(
      () => JSON.parse(localStorage.getItem('lia_eyes_widget_prefs')!).state.position
    );
    expect(position).toEqual(savedEyes ? { xPct: 20, yPct: 20 } : null);
    expect(
      await page.evaluate(
        () => JSON.parse(localStorage.getItem('lia.avatarWindow')!).state.position
      )
    ).toEqual({ xPct: 20, yPct: 90 });
    await expect(
      page.getByRole('toolbar', { name: 'Move avatar: drag or use arrow keys' })
    ).toBeVisible();
    await expect.poll(() => starts.length).toBe(1);
    expect(errors).toEqual([]);
  });
}

test('explicit stop remains reachable and acknowledges closure', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const starts: unknown[] = [];
  const releases: unknown[] = [];
  const frames = await installSimliPeer(page);
  await authenticate({ voice_enabled: true, speaking_avatar_enabled: true });
  await mockApi([...loadedChatRoutes(), ...avatarRoutes(starts, releases)]);
  await page.goto('/en/dashboard/chat');
  await waitForHydration(page);
  const widget = page.getByRole('toolbar', { name: 'Move avatar: drag or use arrow keys' });
  await expect(widget).toBeVisible();
  await expect
    .poll(() => widget.locator('video').evaluate(video => (video as HTMLVideoElement).videoWidth))
    .toBeGreaterThan(0);
  await widget.click();
  await widget.getByRole('button', { name: 'Stop avatar session', exact: true }).click();
  await expect(widget.getByText('Session stopped', { exact: true })).toBeVisible();
  await expect.poll(() => releases.length).toBe(1);
  expect(starts).toHaveLength(1);
  expect(frames).toContain('DONE');
});

test('a reloaded PWA can stop its previous generation and states unconfirmed closure honestly', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const identity = {
    owner_id: '11111111-1111-4111-8111-111111111111',
    lease_id: '22222222-2222-4222-8222-222222222222',
  };
  const releases: unknown[] = [];
  let admitted = 0;
  let closed = false;
  await authenticate({ voice_enabled: true, speaking_avatar_enabled: true });
  await mockApi([
    ...loadedChatRoutes(),
    ...avatarRoutes([], []),
    {
      url: '**/api/v1/avatars/sessions/current',
      handler: route =>
        route.fulfill({
          json: closed
            ? null
            : { ...identity, controlled: true, phase: 'ready', control_phase: 'open' },
        }),
    },
    {
      url: '**/api/v1/avatars/sessions',
      method: 'POST',
      handler: async route => {
        admitted++;
        await route.fulfill({ status: 409, json: { detail: 'avatar_already_active' } });
      },
    },
    {
      url: '**/api/v1/avatars/sessions/release',
      method: 'POST',
      handler: async route => {
        releases.push(route.request().postDataJSON());
        closed = releases.length === 2;
        await route.fulfill({ json: { released: closed } });
      },
    },
  ]);
  await page.goto('/en/dashboard/chat');
  await waitForHydration(page);
  const widget = page.getByRole('toolbar', { name: 'Move avatar: drag or use arrow keys' });
  await expect(widget.getByRole('button', { name: 'Retry', exact: true })).toBeVisible();
  const stop = widget.getByRole('button', { name: 'Stop avatar session', exact: true });
  await stop.click();
  await expect(
    widget.getByText('Closure not confirmed yet. Wait, then try again.', { exact: true })
  ).toBeVisible();
  await stop.click();
  await expect(widget.getByText('Session stopped', { exact: true })).toBeVisible();
  expect(releases).toEqual([identity, identity]);
  expect(admitted).toBe(1);
});
