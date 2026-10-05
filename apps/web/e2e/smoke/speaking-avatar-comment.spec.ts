import { test, expect, loadedChatRoutes, waitForHydration } from '../fixtures';
import { avatarRoutes, installSimliPeer, spokenWave, encodedSpokenSample } from '../fixtures/simli';
import { scanPage } from '../a11y/scan';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

for (const [width, format] of [
  [320, 'pcm'],
  [390, 'pcm'],
  [1280, 'pcm'],
  [390, 'mp3'],
  [390, 'mp4'],
] as const) {
  test(`persistent speaking avatar, window movement and exclusive ${format} TTS at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    const starts: unknown[] = [];
    const releases: unknown[] = [];
    const pageErrors: string[] = [];
    page.on('pageerror', error => pageErrors.push(error.name));
    page.on('console', message => {
      if (message.type() !== 'error') return;
      const text = message.text();
      if (/content security|content-security|\bCSP\b/i.test(text))
        console.log('browser security policy error');
      if (/socket|WebSocket/.test(text)) console.log('browser websocket error');
    });
    page.on('console', message => {
      if (!/avatar_connection_(failed|phase)/.test(message.text())) return;
      console.log('avatar connection phase', message.text().match(/"phase":\s*"([a-z_]+)"/)?.[1]);
    });
    page.on('console', message => {
      if (!message.text().includes('avatar_unavailable')) return;
      console.log('avatar failure code', message.text().match(/"code":\s*"([a-z_]+)"/)?.[1]);
    });
    await page.setViewportSize({ width, height: 900 });
    const frames = await installSimliPeer(page);
    const user = await authenticate({ voice_enabled: true, speaking_avatar_enabled: true });
    await mockApi([
      ...loadedChatRoutes(),
      ...avatarRoutes(starts, releases),
      {
        url: '**/api/v1/auth/me/voice-preference',
        method: 'PATCH',
        handler: async route => {
          user.voice_enabled = false;
          await route.fulfill({ json: { voice_enabled: false } });
        },
      },
    ]);
    let response = 0;
    await page.route('**/api/v1/agents/chat/stream', async route => {
      const run = `synthetic-response-${++response}`;
      const chunks = [
        { type: 'voice_comment_start', content: '', metadata: { run_id: run } },
        { type: 'token', content: `Spoken response ${response}`, metadata: null },
        {
          type: 'voice_audio_chunk',
          content: {
            audio_base64: format === 'pcm' ? spokenWave() : encodedSpokenSample(format),
            phrase_index: 0,
            is_last: true,
            mime_type:
              format === 'pcm' ? 'audio/wav' : format === 'mp4' ? 'audio/mp4' : 'audio/mpeg',
          },
          metadata: { run_id: run },
        },
        { type: 'voice_complete', content: '', metadata: { chunk_count: 1 } },
        { type: 'done', content: '', metadata: {} },
      ];
      await route.fulfill({
        contentType: 'text/event-stream',
        body: chunks.map(chunk => `data: ${JSON.stringify(chunk)}\n\n`).join(''),
      });
    });
    await page.goto('/en/dashboard/chat');
    await waitForHydration(page);
    await awaitStyledPage(page, 'speaking avatar');
    const widget = page.getByRole('toolbar', { name: 'Move avatar: drag or use arrow keys' });
    await expect(widget).toBeVisible();
    expect(starts).toHaveLength(1);
    try {
      await expect
        .poll(() =>
          widget.locator('video').evaluate(video => (video as HTMLVideoElement).videoWidth)
        )
        .toBeGreaterThan(0);
      await widget.click();
      await widget.focus();
      await page.keyboard.press('Enter');
      await expect(widget.getByRole('button', { name: 'Enable audio' })).toHaveCount(0);
    } catch (error) {
      console.log(
        'synthetic avatar diagnostics',
        await page.evaluate(() => window.simliFixture.nativeDiagnostics())
      );
      throw error;
    }
    const resize = widget.getByRole('button', { name: 'Change size', exact: true });
    for (const size of ['Medium', 'Large', 'Small']) {
      await widget.focus();
      await resize.click();
      await expect(resize).toHaveAttribute('title', size);
      await expect
        .poll(async () => {
          const box = await widget.boundingBox();
          return box ? box.x >= 0 && box.x + box.width <= width : false;
        })
        .toBe(true);
      const box = await widget.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
    }
    // The label can precede Firefox's layout of the final Small size. Anchor
    // the keyboard assertion on its rendered geometry, then its actual focus.
    await expect(widget).toHaveCSS('width', '160px');
    await widget.focus();
    await expect(widget).toBeFocused();
    const before = await widget.boundingBox();
    await page.keyboard.press('ArrowUp');
    await expect.poll(async () => (await widget.boundingBox())!.y).toBeLessThan(before!.y);
    const box = await widget.locator('video').boundingBox();
    await page.mouse.move(box!.x + 30, box!.y + 20);
    await page.mouse.down();
    await page.mouse.move(10, 60);
    await page.mouse.up();
    await expect.poll(async () => (await widget.boundingBox())!.x).toBeLessThanOrEqual(10);
    await expectNoOverflow(page, `avatar ${width}`);
    await expect(widget.locator('video')).toHaveJSProperty('muted', true);
    const localStarts = await page.evaluate(() => window.simliFixture.localStarts);
    await page.locator('textarea').fill('Speak once');
    await page.locator('textarea').press('Enter');
    await expect
      .poll(() => frames.filter(frame => Buffer.isBuffer(frame)).length)
      .toBeGreaterThan(0);
    await expect(page.getByText('Spoken response 1', { exact: true })).toBeVisible();
    await expect.poll(() => page.evaluate(() => window.simliFixture.decoded.length)).toBe(1);
    const expected = await page.evaluate(() =>
      window.simliFixture.decoded.reduce(
        (bytes, buffer) => bytes + Math.floor((buffer.frames * 16000) / buffer.rate) * 2,
        0
      )
    );
    await expect
      .poll(() =>
        frames
          .filter(frame => Buffer.isBuffer(frame))
          .reduce((bytes, frame) => bytes + frame.length, 0)
      )
      .toBe(expected);
    await expect
      .poll(() => page.evaluate(() => window.simliFixture.renderedPeak))
      .toBeGreaterThan(0);
    // The queue returns to idle only after the actual remote tail.
    await page.waitForTimeout(1800);
    await page.locator('textarea').fill('Speak again');
    await page.locator('textarea').press('Enter');
    await expect.poll(() => page.evaluate(() => window.simliFixture.decoded.length)).toBe(2);
    await expect
      .poll(() =>
        frames
          .filter(frame => Buffer.isBuffer(frame))
          .reduce((bytes, frame) => bytes + frame.length, 0)
      )
      .toBe(expected * 2);
    expect(await page.evaluate(() => window.simliFixture.localStarts)).toBe(localStarts);
    expect(starts).toHaveLength(1);
    expect(releases).toHaveLength(0);
    expect(frames).not.toContain('DONE');
    const stored = await page.evaluate(() => localStorage.getItem('lia.avatarWindow'));
    expect(stored).toContain('position');
    expect(stored).not.toMatch(/hermetic-simli|face_id|enabled|fixture-version/);
    const { blocking, summary } = await scanPage(page, testInfo, `speaking-avatar-${width}`);
    expect(blocking, summary).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`avatar-${width}.png`) });
    await page.getByRole('button', { name: 'Disable voice', exact: true }).click();
    await expect(widget).toHaveCount(0);
    await expect.poll(() => releases.length).toBe(1);
    expect(frames).toContain('DONE');
    expect(pageErrors).toEqual([]);
  });
}
