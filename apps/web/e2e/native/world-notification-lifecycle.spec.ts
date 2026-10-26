/** Real browser/BFF aborts must not strand a Redis Pub/Sub connection. */
import { test, expect } from './fixtures';

test('notification lifecycle: repeated native stream aborts keep the transport usable', async ({
  browser,
  baseURL,
}) => {
  if (!baseURL) throw new Error('Isolated native proof required');
  const context = await browser.newContext({ baseURL, serviceWorkers: 'block' });
  try {
    const login = await context.request.post('/api/v1/world-proof/session', {
      headers: { Origin: new URL(baseURL).origin },
      data: { index: 8 },
    });
    expect(login.status()).toBe(200);
    const page = await context.newPage();
    // A same-origin static document avoids mounting another notification receiver.
    await page.goto('/robots.txt');
    const results = await page.evaluate(async () => {
      const samples: string[] = [];
      for (let index = 0; index < 24; index++) {
        await new Promise<void>((resolve, reject) => {
          const source = new EventSource('/api/v1/notifications/stream', { withCredentials: true });
          const timeout = window.setTimeout(() => {
            source.close();
            reject(new Error('Native notification handshake timed out'));
          }, 5000);
          source.addEventListener(
            'connected',
            () => {
              clearTimeout(timeout);
              samples.push('connected');
              source.close();
              resolve();
            },
            { once: true }
          );
          source.onerror = () => {
            clearTimeout(timeout);
            source.close();
            reject(new Error('Native notification stream unavailable'));
          };
        });
      }
      return samples;
    });
    expect(results).toEqual(Array.from({ length: 24 }, () => 'connected'));
  } finally {
    await context.close();
  }
});
