/** Complete provider venue details through archived Markdown and Docker UI. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { test, expect, waitForHydration } from '../fixtures';
import { loadedChatRoutes } from '../fixtures/chat';
import { awaitStyledPage, expectNoOverflow, prepareTheme } from './overflow-report';

interface Reference {
  id: string;
  language: string;
  html: string;
}
const references: Reference[] = JSON.parse(
  readFileSync(
    path.join(
      __dirname,
      '../../../api/tests/unit/domains/agents/display/card_reference_corpus.json'
    ),
    'utf8'
  )
);
const samples = [
  { width: 1280, language: 'fr', theme: 'light' },
  { width: 390, language: 'en', theme: 'dark' },
  { width: 320, language: 'fr', theme: 'oled' },
] as const;

for (const sample of samples) {
  test(`complete venue data at ${sample.width}px in ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const reference = references.find(
      item => item.id === 'place_details' && item.language === sample.language
    );
    if (!reference) throw new Error('Missing backend place-details reference');
    let avatarRequests = 0;
    await page.setViewportSize({ width: sample.width, height: 1800 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await prepareTheme(page, sample.theme);
    await authenticate({
      language: sample.language,
      response_display_mode: 'html_cards',
      theme: sample.theme,
    });
    await mockApi([
      ...loadedChatRoutes(),
      {
        url: '**/api/v1/conversations/me/messages*',
        json: {
          messages: [
            {
              id: '00000000-0000-4000-8000-00000000c405',
              role: 'assistant',
              content: reference.html,
              created_at: '2026-10-03T09:30:00Z',
              metadata: null,
            },
          ],
          conversation_id: '00000000-0000-4000-8000-00000000c0h1',
          total_count: 1,
          has_more: false,
          next_cursor: null,
        },
      },
    ]);
    await page.route('**/api/v1/connectors/google-places/photo/**', async route => {
      avatarRequests += 1;
      await route.fulfill({
        contentType: 'image/svg+xml',
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><rect width="24" height="24" fill="#88aaa2"/></svg>',
        headers: {
          'Access-Control-Allow-Origin': 'https://localhost:3000',
          'Access-Control-Allow-Credentials': 'true',
        },
      });
    });
    await page.goto(`/${sample.language}/dashboard/chat`);
    await waitForHydration(page);
    await awaitStyledPage(page, 'complete venue details');
    const html = page.locator('html');
    const dark = sample.theme !== 'light';
    await expect(html).toHaveClass(dark ? /\bdark\b/ : /\blight\b/);
    await expect(html).not.toHaveClass(dark ? /\blight\b/ : /\bdark\b/);
    await expect(html).toHaveCSS('color-scheme', dark ? 'dark' : 'light');
    await expect(page.locator('html[data-oled]')).toHaveCount(sample.theme === 'oled' ? 1 : 0);
    const card = page.locator('.lia-card.lia-place');
    await expect(card).toContainText('Europe/Paris');
    expect(avatarRequests).toBe(0);
    for (const summary of await card.locator('summary').all()) {
      await summary.focus();
      await summary.press('Enter');
      await expect(summary).toBeFocused();
      // Firefox can report 43.999969 for a 44px box; compare at subpixel precision.
      const height = (await summary.boundingBox())?.height ?? 0;
      expect(Math.round(height * 1000)).toBeGreaterThanOrEqual(44_000);
    }
    await expect(card.getByText('A warm welcome.', { exact: false })).toBeVisible();
    await expect(card.getByRole('link', { name: 'Camille', exact: true })).toHaveAttribute(
      'href',
      'https://example.test/author'
    );
    await expect(card.locator('a[href="https://example.test/review"]')).toBeVisible();
    await expect(card.locator('a[href="https://example.test/report"]')).toBeVisible();
    await expect(card.locator('[data-availability="false"]')).toHaveCount(4);
    await expect(card.locator('[data-availability="true"]')).toHaveCount(4);
    await expect(card.locator('img.lia-review__avatar')).toHaveJSProperty('naturalWidth', 24);
    expect(avatarRequests).toBe(1);
    // Reduced motion must remove the reveal, including its initial transparent frame.
    const readableDetails = card.locator('.lia-collapsible[open] > .lia-collapsible__content');
    expect(await readableDetails.count()).toBeGreaterThan(0);
    for (const detail of await readableDetails.all()) {
      await expect(detail).toHaveCSS('animation-name', 'none');
    }
    await expectNoOverflow(page, `venue ${sample.width} ${sample.theme}`);
    const accessibility = await new AxeBuilder({ page })
      .include('.lia-multi-domain')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    expect(accessibility.violations).toEqual([]);
    await page.setViewportSize({ width: sample.width, height: 4000 });
    await card.screenshot({
      path: test.info().outputPath(`venue-${sample.theme}.png`),
      style: 'nextjs-portal { display: none !important; }',
    });
  });
}
