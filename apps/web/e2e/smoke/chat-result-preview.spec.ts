/** Legacy preview frames remain invisible while the ordinary answer streams. */
import { test, expect, chatRoutes, idleNotificationStream } from '../fixtures';
import { scanPage } from '../a11y/scan';

declare global {
  interface Window {
    jevTestStream?: ReadableStreamDefaultController<Uint8Array>;
  }
}

for (const width of [390, 1280]) {
  test(`JEV first-results panel stays hidden during streaming at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ language: 'fr' });
    await mockApi([
      ...chatRoutes([]),
      { url: '**/api/v1/habits/presence', json: {} },
      { url: '**/api/v1/telephony/calls*', json: { calls: [], total: 0 } },
      { url: '**/api/v1/conversations/me', json: { id: '00000000-0000-4000-8000-0000000000ff' } },
      { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
      idleNotificationStream,
      { url: '**/api/v1/briefing/companion-context', json: { timezone: 'UTC', weather: null } },
      { url: '**/api/v1/psyche/settings', json: { enabled: false } },
      { url: '**/api/v1/skills*', json: { skills: [] } },
      { url: '**/api/v1/chat/shortcuts*', json: { shortcuts: [] } },
      { url: '**/api/v1/chat/suggestions*', json: { suggestions: [] } },
      {
        url: '**/api/v1/system-settings/debug-panel-status',
        json: { enabled: false, user_access_available: false },
      },
    ]);
    await page.addInitScript(() => {
      const original = window.fetch.bind(window);
      window.fetch = async (input, init) => {
        const url = input instanceof Request ? input.url : String(input);
        if (!url.includes('/agents/chat/stream')) return original(input, init);
        return new Response(
          new ReadableStream<Uint8Array>({
            start(controller) {
              window.jevTestStream = controller;
            },
          }),
          { status: 200, headers: { 'Content-Type': 'text/event-stream' } }
        );
      };
    });
    await page.goto('/fr/dashboard/chat');
    const composer = page.getByRole('textbox').first();
    await composer.fill('Quels emails attendent une réponse ?');
    await composer.press('Enter');
    await expect.poll(() => page.evaluate(() => Boolean(window.jevTestStream))).toBe(true);
    await page.evaluate(() => {
      const frames = [
        { type: 'token', content: 'Je prépare la synthèse.' },
        {
          type: 'result_preview',
          content: '',
          metadata: {
            collection: {
              kind: 'EMAIL',
              candidate_count: 3,
              evaluated_count: 2,
              omitted_count: 0,
              items: [
                {
                  id: '1',
                  title: 'Contrat à signer',
                  excerpt: '<script>window.jevInjected=true</script>',
                  verdict: 'match',
                },
                {
                  id: '2',
                  title: 'Pièce jointe indisponible',
                  excerpt: 'À vérifier dans la réponse finale.',
                  verdict: 'unknown',
                },
                {
                  id: '3',
                  title: 'Bulletin promotionnel',
                  excerpt: 'Aucune réponse demandée.',
                  verdict: 'non_match',
                },
              ],
            },
          },
        },
      ];
      for (const kind of ['REMINDER', 'TICKET', 'MCP_RESULT', 'NOTE']) {
        frames.push({
          type: 'result_preview',
          content: '',
          metadata: {
            collection: {
              kind,
              candidate_count: 1,
              evaluated_count: 1,
              omitted_count: 0,
              items: [
                {
                  id: kind,
                  title: `Source ${kind}`,
                  excerpt: 'Preuve conservée',
                  verdict: 'unknown',
                },
              ],
            },
          },
        });
      }
      frames.push({ type: 'token', content: ' La réponse arrive.' });
      window.jevTestStream?.enqueue(
        new TextEncoder().encode(frames.map(frame => `data: ${JSON.stringify(frame)}\n\n`).join(''))
      );
    });
    const preview = page.getByRole('complementary', { name: 'Premiers résultats' });
    await expect(
      page.getByText('Je prépare la synthèse. La réponse arrive.', { exact: false })
    ).toBeVisible();
    await expect(preview).not.toBeAttached();
    await expect(page.getByText('Contrat à signer')).not.toBeAttached();
    await expect(page.getByText('Pièce jointe indisponible')).not.toBeAttached();
    for (const kind of ['REMINDER', 'TICKET', 'MCP_RESULT', 'NOTE']) {
      await expect(page.getByText(`Source ${kind}`)).not.toBeAttached();
    }
    await expect(page.getByText('Bulletin promotionnel')).not.toBeAttached();
    expect(await page.evaluate(() => 'jevInjected' in window)).toBe(false);
    const { blocking, summary: report } = await scanPage(
      page,
      testInfo,
      `jev-hidden-preview-${width}`
    );
    expect(blocking, report).toEqual([]);
    await page.evaluate(() => {
      window.jevTestStream?.enqueue(
        new TextEncoder().encode('data: {"type":"done","content":"","metadata":null}\n\n')
      );
      window.jevTestStream?.close();
    });
    await expect(preview).not.toBeAttached();
    expect(errors).toEqual([]);
  });
}
