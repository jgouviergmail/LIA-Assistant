/** Real companion + mocked SSE: no tool plan or prepared draft earns an action gesture. */
import { test, expect, chatRoutes } from '../fixtures';
import { scanPage } from '../a11y/scan';
import { MAX_FRAME_MS } from '../../src/components/eyes/rig/scheduler';

for (const outcome of ['prepared', 'succeeded', 'failed', 'unknown'] as const) {
  test(`companion distinguishes ${outcome}, then forgets it on reload`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await page.setViewportSize({ width: 375, height: 812 });
    await page.addInitScript(() => {
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({ state: { visible: true, style: 'smiley', size: 'md' }, version: 0 })
      );
    });
    await mockApi(chatRoutes([]));
    await page.route('**/api/v1/agents/chat/stream', async route => {
      const activity = {
        version: 1,
        run_id: 'e2e',
        invocation_id: 'actual',
        family: 'communicating',
        intent: outcome === 'prepared' ? 'prepare' : 'act',
        phase: 'finished',
        outcome,
      };
      const chunks = [
        { type: 'execution_step', content: '', metadata: { step_type: 'activity', activity } },
        { type: 'token', content: 'Voici la réponse de contrôle.', metadata: null },
        {
          type: 'done',
          content: '',
          metadata: { expressivity: { register: 'warm', intensity: 0.5, accent: 'none' } },
        },
      ];
      await route.fulfill({
        contentType: 'text/event-stream',
        body: chunks.map(chunk => `data: ${JSON.stringify(chunk)}\n\n`).join(''),
      });
    });
    await page.goto('/en/dashboard/chat');
    const avatar = page.locator('.lia-eyes[data-style="smiley"]').last();
    await expect(avatar).toBeVisible();
    await page.locator('textarea').fill('Contrôle du compagnon');
    await page.locator('textarea').press('Enter');
    await expect(page.getByText('Voici la réponse de contrôle.', { exact: true })).toBeVisible();
    await expect(avatar).toHaveAttribute('data-accomplished', String(outcome === 'succeeded'));
    await expect(avatar).toHaveAttribute('data-expression', 'tender');
    const bounds = await avatar.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(375);
    expect(await avatar.getAttribute('aria-hidden')).toBe('true');
    await page.reload();
    await expect(avatar).toBeVisible();
    await expect(avatar).toHaveAttribute('data-accomplished', 'false');
    await expect(avatar).not.toHaveAttribute('data-expression', 'tender');
  });
}

test('drawn eyes respect reduced motion and the widget remains keyboard operable', async ({
  page,
  authenticate,
  mockApi,
}, testInfo) => {
  await authenticate();
  await mockApi(chatRoutes([]));
  await page.addInitScript(() =>
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({ state: { visible: true, style: 'anneaux', size: 'md' }, version: 0 })
    )
  );
  await page.goto('/en/dashboard/chat');
  const avatar = page.locator('.lia-eyes[data-style="anneaux"]').last();
  await expect(avatar).toBeVisible();
  const widget = page.getByRole('group', { name: /LIA's expressive eyes/ });
  await widget.focus();
  const before = await widget.boundingBox();
  await page.keyboard.press('ArrowLeft');
  await expect.poll(async () => (await widget.boundingBox())!.x).toBeLessThan(before!.x);
  const path = avatar.locator('[data-rig-mouth]');
  const shape = await path.getAttribute('d');
  await page.waitForTimeout(1100); // Observe a full host heartbeat under reduced motion.
  expect(await path.getAttribute('d')).toBe(shape);
  await page.getByRole('button', { name: 'Hide the eyes', exact: true }).click();
  await expect(avatar).not.toBeVisible();
  await page.getByRole('button', { name: 'Show the eyes', exact: true }).click();
  await expect(avatar).toBeVisible();
  const { blocking, summary } = await scanPage(page, testInfo, 'chat-avatar');
  expect(blocking, summary).toEqual([]);
});

test.describe('living smiley', () => {
  test.use({ contextOptions: { reducedMotion: 'no-preference' } });

  test('fits phone and desktop viewports and actually performs a spontaneous scene', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await authenticate();
    await mockApi(chatRoutes([]));
    await page.addInitScript(() =>
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({ state: { visible: true, style: 'smiley', size: 'md' }, version: 0 })
      )
    );
    const clockStart = new Date('2026-09-21T12:00:00Z');
    await page.clock.install({ time: clockStart });
    // Pause before navigation so layout, snapshots and screenshots cannot move
    // the rig's timeline between the advances we explicitly observe.
    await page.clock.pauseAt(new Date(clockStart.getTime() + 1000));
    await page.goto('/en/dashboard/chat');
    const avatar = page.locator('.lia-eyes[data-style="smiley"]').last();
    await expect(avatar).toBeVisible();
    for (const width of [320, 375, 768, 1440]) {
      await page.setViewportSize({ width, height: 812 });
      await page.clock.runFor(500);
      const box = await avatar.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      expect(box!.y).toBeGreaterThanOrEqual(0);
      expect(box!.y + box!.height).toBeLessThanOrEqual(812);
    }
    const restingMouth = await avatar.locator('[data-rig-mouth]').getAttribute('d');
    // Sample resting time sparsely, carrying every millisecond through the
    // rig's frame cap. runFor executes and yields after every 16 ms rAF;
    // under WebKit tracing, idle frames can consume the test's 90 s.
    const advanceRestingBeat = async () => {
      for (let remaining = 500; remaining > 0; ) {
        // runFor may end between rAFs; leave room for that first remainder.
        const cap = remaining === 500 ? MAX_FRAME_MS / 2 : MAX_FRAME_MS;
        const step = Math.min(remaining, cap);
        await page.clock.fastForward(step);
        remaining -= step;
      }
    };
    let scene = '';
    for (let beat = 0; beat < 120 && !scene; beat++) {
      await advanceRestingBeat();
      scene = (await avatar.getAttribute('data-scene')) ?? '';
    }
    expect(scene).not.toBe('');
    await page.clock.runFor(1000);
    expect(await avatar.locator('[data-rig-mouth]').getAttribute('d')).not.toBe(restingMouth);
    const capture = testInfo.outputPath('smiley-scene.png');
    await avatar.screenshot({ path: capture });
    await testInfo.attach('smiley-scene', { path: capture, contentType: 'image/png' });
    // Keep every active scene frame. Only use sparse sampling after its end
    // is observed, while still advancing the full 12 seconds before the oracle.
    for (let remaining = 12_000; remaining > 0; remaining -= 500) {
      if ((await avatar.getAttribute('data-scene')) === '') {
        await advanceRestingBeat();
      } else {
        await page.clock.runFor(500);
      }
    }
    await expect(avatar).toHaveAttribute('data-scene', '');
  });
});
