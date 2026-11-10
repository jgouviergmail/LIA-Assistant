/** The deployed app serves the real historical icon font; no asset route is mocked. */
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Response } from '@playwright/test';
import { test, expect, waitForHydration } from '../fixtures';
import { loadedChatRoutes } from '../fixtures/chat';

const FONT_PATH = '/fonts/material-symbols/MaterialSymbolsOutlined.woff2';
const FONT_BYTES = readFileSync(resolve(__dirname, '../../public', `.${FONT_PATH}`));
const FONT_HASH = createHash('sha256').update(FONT_BYTES).digest('hex');

test('loads an archived ligature from the real self-hosted variable font', async ({
  page,
  context,
  baseURL,
  authenticate,
  mockApi,
  apiNetworkGuard,
}, testInfo) => {
  if (!baseURL) throw new Error('The real app origin is required');
  const origin = new URL(baseURL).origin;
  const external: string[] = [];
  const assets = new Map<string, Response>();
  const stylesheets: Response[] = [];
  context.on('request', request => {
    const url = new URL(request.url());
    if (/^https?:$/.test(url.protocol) && url.origin !== origin) external.push(url.href);
  });
  page.on('response', response => {
    const url = new URL(response.url());
    if (url.origin === origin && url.pathname === FONT_PATH) {
      assets.set(url.pathname, response);
    }
    if (url.origin === origin && response.request().resourceType() === 'stylesheet') {
      stylesheets.push(response);
    }
  });
  await authenticate({ icon_style: 'fluent' });
  await mockApi([
    ...loadedChatRoutes(),
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: [
          {
            id: '00000000-0000-4000-8000-00000000f001',
            role: 'assistant',
            content:
              '<p>Historical symbol: <span class="material-symbols-outlined">account_balance</span></p>',
            created_at: '2026-11-08T09:00:00Z',
          },
        ],
        conversation_id: '00000000-0000-4000-8000-00000000c0h1',
        total_count: 1,
        has_more: false,
        next_cursor: null,
      },
    },
  ]);
  await page.goto('/fr/dashboard/chat');
  await waitForHydration(page);
  const glyph = page.locator('.material-symbols-outlined').filter({ hasText: 'account_balance' });
  await expect(glyph).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() =>
        Array.from(document.fonts).some(
          face =>
            face.family.replaceAll('"', '').replaceAll("'", '') === 'Material Symbols Outlined' &&
            face.status === 'loaded'
        )
      )
    )
    .toBe(true);
  const box = await glyph.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return {
      width: rect.width,
      height: rect.height,
      family: style.fontFamily,
      variation: style.fontVariationSettings,
    };
  });
  expect(box.family).toContain('Material Symbols Outlined');
  expect(box.variation).toMatch(/["']FILL["'] 0/);
  expect(box.height).toBeGreaterThan(0);
  // A real ligature occupies one glyph, not the width of "account_balance" text.
  expect(box.width).toBeGreaterThan(0);
  expect(box.width).toBeLessThanOrEqual(box.height * 1.5);
  const font = assets.get(FONT_PATH);
  if (!font) throw new Error('The browser must request the real font asset');
  const deliveredCss = await Promise.all(stylesheets.map(response => response.text()));
  expect(
    deliveredCss.some(css => css.includes('Material Symbols Outlined') && css.includes(FONT_PATH))
  ).toBe(true);
  expect(font.status()).toBe(200);
  expect(
    createHash('sha256')
      .update(await font.body())
      .digest('hex')
  ).toBe(FONT_HASH);
  expect(external, 'the page needs no external font service').toEqual([]);
  await testInfo.attach('font-network-isolation.json', {
    body: JSON.stringify({ external, blockedTransport: apiNetworkGuard.blockedRequests }),
    contentType: 'application/json',
  });
  // The same native probes documented by meeting-timeline remain DENIED.
  // Application page/worker requests fail independently; no font CDN is exempt.
  const browserRefusals = new Set([
    'CONNECT www.google.com:443',
    'CONNECT content-autofill.googleapis.com:443',
  ]);
  expect(apiNetworkGuard.blockedRequests.filter(request => !browserRefusals.has(request))).toEqual(
    []
  );
});
