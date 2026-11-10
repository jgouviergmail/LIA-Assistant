/** Received air quality and pollen are readable before opening weather details. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { test, expect, waitForHydration } from '../fixtures';
import { loadedChatRoutes } from '../fixtures/chat';
import { awaitStyledPage, expectNoOverflow, prepareTheme } from './overflow-report';

const references: { id: string; language: string; html: string }[] = JSON.parse(
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
  { width: 1280, language: 'fr', theme: 'dark' },
  { width: 390, language: 'fr', theme: 'light' },
  { width: 390, language: 'en', theme: 'dark' },
  { width: 320, language: 'fr', theme: 'oled' },
] as const) {
  test(`weather environment visible at ${sample.width}px in ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const reference = references.find(
      item => item.id === 'weathers' && item.language === sample.language
    );
    if (!reference) throw new Error('Missing backend current weather reference');
    await page.setViewportSize({ width: sample.width, height: 1200 });
    await prepareTheme(page, sample.theme);
    await authenticate({
      language: sample.language,
      theme: sample.theme,
      response_display_mode: 'cards',
    });
    await mockApi([
      ...loadedChatRoutes(),
      {
        url: '**/api/v1/conversations/me/messages*',
        json: {
          messages: [
            {
              id: '00000000-0000-4000-8000-00000000e001',
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
    await page.goto(`/${sample.language}/dashboard/chat`);
    await waitForHydration(page);
    await awaitStyledPage(page, 'current weather environment');
    const card = page.locator('.lia-card.lia-weather');
    const environment = card.locator('.lia-weather__environment');
    const details = card.locator('details.lia-collapsible');
    await expect(details).not.toHaveAttribute('open', '');
    await expect(environment).toHaveCount(1);
    await expect(environment.getByText(/Moyen.*IQA \(FR\)/)).toBeVisible();
    await expect(environment.getByText(/Graminées Élevé, Ambroisie Modéré/)).toBeVisible();
    await expect(details.locator('.lia-weather__environment')).toHaveCount(0);
    await expect(details.getByText(/10 km/)).not.toBeVisible();
    await expect(environment.locator('[data-icon-name="Flower2"]')).toBeVisible();
    const temperature = card.locator('.lia-weather__temp');
    await expect(temperature).toHaveText('18°C');
    expect(
      await temperature.evaluate(element => {
        const range = document.createRange();
        range.selectNodeContents(element);
        return range.getClientRects().length;
      })
    ).toBe(1);
    await expectNoOverflow(page, `weather environment ${sample.width} ${sample.theme}`);
    const accessibility = await new AxeBuilder({ page })
      .include('.lia-weather')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    expect(accessibility.violations).toEqual([]);
    await card.scrollIntoViewIfNeeded();
    await card.screenshot({
      path: test.info().outputPath(`weather-environment-${sample.width}-${sample.theme}.png`),
      style:
        'body * { visibility: hidden !important; } .lia-weather, .lia-weather * { visibility: visible !important; }',
    });

    // Existing extra measurements remain available with keyboard disclosure.
    await details.locator('summary').focus();
    await details.locator('summary').press('Enter');
    await expect(details.getByText(/10 km/)).toBeVisible();
    await expect(environment.getByText(/Moyen.*IQA \(FR\)/)).toBeVisible();
  });
}
