import type { Browser, BrowserContext, BrowserContextOptions } from '@playwright/test';

export interface WorldDevice {
  context: BrowserContext;
  close(): Promise<void>;
}

/**
 * A person has an independent cookie jar and transport pool. WebKit's shared
 * browser process can exhaust its HTTP/1 connection pool when several simulated
 * people each retain native SSE and a world socket; use a separate process there.
 */
export async function createWorldDevice(
  browser: Browser,
  options: BrowserContextOptions
): Promise<WorldDevice> {
  const owned =
    browser.browserType().name() === 'webkit' ? await browser.browserType().launch() : null;
  try {
    const context = await (owned ?? browser).newContext(options);
    return {
      context,
      async close() {
        try {
          await context.close();
        } finally {
          await owned?.close();
        }
      },
    };
  } catch (error) {
    await owned?.close();
    throw error;
  }
}

/** Close every owned process even if another context has already disconnected. */
export async function closeWorldDevices(devices: readonly WorldDevice[]): Promise<void> {
  const results = await Promise.allSettled(devices.map(device => device.close()));
  const errors: unknown[] = [];
  for (const result of results) {
    if (result.status === 'rejected') errors.push(result.reason);
  }
  if (errors.length) throw new AggregateError(errors, 'World test devices did not close cleanly');
}
