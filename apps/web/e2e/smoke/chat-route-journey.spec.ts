/** Provider formatter + archived registry/card HTML, read in the Docker UI. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { test, expect, waitForHydration } from '../fixtures';
import { loadedChatRoutes } from '../fixtures/chat';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

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

for (const sample of [
  { width: 1280, language: 'fr', theme: 'light' },
  { width: 390, language: 'en', theme: 'dark' },
  { width: 320, language: 'fr', theme: 'oled' },
]) {
  test(`received journey at ${sample.width}px in ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const reference = references.find(
      item => item.id === 'route_details' && item.language === sample.language
    );
    if (!reference) throw new Error('Missing backend route reference');
    await page.setViewportSize({ width: sample.width, height: 1200 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await authenticate({ language: sample.language, response_display_mode: 'cards' });
    await mockApi([
      ...loadedChatRoutes(),
      {
        url: '**/api/v1/conversations/me/messages*',
        json: {
          messages: [
            {
              id: '00000000-0000-4000-8000-00000000c406',
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
    let mapRequests = 0;
    await page.route('**/api/v1/connectors/google-routes/static-map*', async route => {
      mapRequests += 1;
      await route.fulfill({ status: 429, json: { detail: 'quota_exceeded' } });
    });
    await page.goto(`/${sample.language}/dashboard/chat`);
    await waitForHydration(page);
    await awaitStyledPage(page, 'received route journey');
    await page.evaluate(theme => {
      document.documentElement.classList.toggle('dark', theme !== 'light');
      document.documentElement.toggleAttribute('data-oled', theme === 'oled');
    }, sample.theme);
    const card = page.locator('.lia-card.lia-route');
    await expect(card.locator('.lia-card-image-fallback')).toBeVisible();
    expect(mapRequests).toBe(1);
    await expect(card).toContainText('Place Bellecour');
    for (const summary of await card.locator('summary').all()) {
      await summary.focus();
      await summary.press('Enter');
      await expect(summary).toBeFocused();
      expect((await summary.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    }
    await expect(card.getByText('M D', { exact: true })).toBeVisible();
    await expect(card.getByText('OTHER_RECEIVED_JOURNEY', { exact: true })).toBeVisible();
    await expect(card.getByText('350 m · 4 min', { exact: true })).toBeVisible();
    await expect(page.locator('.lia-action-btn[href*="travelmode=transit"]').first()).toBeVisible();
    await expectNoOverflow(page, `route ${sample.width} ${sample.theme}`);
    const accessibility = await new AxeBuilder({ page })
      .include('.lia-multi-domain')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    expect(accessibility.violations).toEqual([]);
    await page.setViewportSize({ width: sample.width, height: 4000 });
    await card.screenshot({
      path: test.info().outputPath(`route-${sample.theme}.png`),
      style: 'nextjs-portal { display: none !important; }',
    });
  });
}
