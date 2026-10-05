/** Actual provider -> archived registry -> keyboard weather selection. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { test, expect, waitForHydration } from '../fixtures';
import { loadedChatRoutes } from '../fixtures/chat';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

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
  { width: 390, language: 'en', theme: 'dark' },
  { width: 320, language: 'fr', theme: 'oled' },
]) {
  test.describe(`weather input at ${sample.width}px`, () => {
    test.use({ hasTouch: sample.width < 500 });
    test(`weather reading at ${sample.width}px in ${sample.theme}`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      const reference = references.find(
        item => item.id === 'weather_details' && item.language === sample.language
      );
      if (!reference) throw new Error('Missing backend weather reference');
      await page.setViewportSize({ width: sample.width, height: 1200 });
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await authenticate({ language: sample.language, response_display_mode: 'cards' });
      await mockApi([
        ...loadedChatRoutes(),
        {
          url: '**/api/v1/conversations/me/messages*',
          json: {
            messages: [1, 2].map(index => ({
              id: `00000000-0000-4000-8000-00000000c40${index}`,
              role: 'assistant',
              content: reference.html,
              created_at: '2026-10-03T09:30:00Z',
              metadata: null,
            })),
            conversation_id: '00000000-0000-4000-8000-00000000c0h1',
            total_count: 2,
            has_more: false,
            next_cursor: null,
          },
        },
      ]);
      const providerRequests: string[] = [];
      page.on('request', request => {
        if (
          /\/connectors\/(?:google-weather|google-places|google-routes|weather)(?:\/|\?)/.test(
            request.url()
          )
        )
          providerRequests.push(request.url());
      });
      await page.goto(`/${sample.language}/dashboard/chat`);
      await waitForHydration(page);
      await awaitStyledPage(page, 'weather slots');
      await page.evaluate(theme => {
        document.documentElement.classList.toggle('dark', theme !== 'light');
        document.documentElement.toggleAttribute('data-oled', theme === 'oled');
      }, sample.theme);
      const series = page.locator('.lia-weather-series');
      await expect(series).toHaveCount(2);
      const first = series.first().locator('details.lia-weather-slot');
      // A missing icon font renders the ligature names as clipped prose and
      // changes both the layout and the contrast scan. A FontFaceSet check can
      // succeed when no face was declared, so also require actual glyph widths.
      await expect
        .poll(
          () =>
            first
              .locator('.lia-weather-slot__icon .material-symbols-outlined')
              .evaluateAll(
                symbols =>
                  document.fonts.check('18px "Material Symbols Outlined"') &&
                  symbols.every(
                    symbol =>
                      symbol.getBoundingClientRect().width <=
                      1.5 * Number.parseFloat(getComputedStyle(symbol).fontSize)
                  )
              ),
          { message: 'Weather symbols must render as loaded font glyphs, not ligature names' }
        )
        .toBe(true);
      // Each provider observation keeps its own day/night glyph and condition
      // color after markdown sanitization, including the collapsed selectors.
      expect(
        await first.locator('.lia-weather-slot__icon .material-symbols-outlined').allTextContents()
      ).toEqual(['light_mode', 'partly_cloudy_night', 'thunderstorm']);
      expect(
        await first
          .locator('.lia-weather-slot__icon .lia-icon')
          .evaluateAll(symbols => symbols.map(symbol => getComputedStyle(symbol).color))
      ).toEqual(['rgb(245, 158, 11)', 'rgb(129, 140, 248)', 'rgb(99, 102, 241)']);
      await expect(first.first()).toHaveAttribute('open', '');
      const secondSummary = first.nth(1).locator('summary').first();
      await secondSummary.focus();
      await secondSummary.press('Enter');
      await expect(secondSummary).toBeFocused();
      await expect(first.nth(1)).toHaveAttribute('open', '');
      await expect(
        first.nth(1).locator('.lia-weather__icon .material-symbols-outlined')
      ).toHaveText('partly_cloudy_night');
      await expect(first.nth(1).locator('.lia-weather__icon .lia-icon')).toHaveCSS(
        'color',
        'rgb(129, 140, 248)'
      );
      await expect(first.first()).not.toHaveAttribute('open', '');
      await expect(series.nth(1).locator('details.lia-weather-slot').first()).toHaveAttribute(
        'open',
        ''
      );
      expect((await secondSummary.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      if (sample.width < 500) {
        await page.addStyleTag({ content: 'nextjs-portal { display: none !important; }' });
        await first.nth(2).locator('summary').first().tap();
        await expect(first.nth(2)).toHaveAttribute('open', '');
        await expect(first.nth(1)).not.toHaveAttribute('open', '');
        await secondSummary.tap();
      }
      const details = first.nth(1).locator('details.lia-collapsible summary');
      await expect(first.nth(1).locator('.lia-weather__stat-label').first()).toBeVisible();
      await details.focus();
      await details.press('Enter');
      await expect(first.nth(1).getByText(/1008 hPa/)).toBeVisible();
      await expect(first.nth(1).getByText(/2.4 m\/s/)).toBeVisible();
      const card = page.locator('.lia-card.lia-weather').first();
      await card.scrollIntoViewIfNeeded();
      await page.screenshot({ path: test.info().outputPath(`weather-${sample.theme}.png`) });
      const compare = card.locator(':scope > .lia-collapsible-wrapper summary');
      await compare.focus();
      await compare.press('Enter');
      await expect(card.locator('table tbody tr')).toHaveCount(3);
      const caption = card.locator('table caption');
      await expect(caption).toBeVisible();
      await expect(caption).toHaveCSS(
        'color',
        await card.evaluate(element => getComputedStyle(element).color)
      );
      const region = card.locator('.lia-weather-comparison');
      await region.focus();
      await expect(region).toBeFocused();
      await expectNoOverflow(page, `weather ${sample.width} ${sample.theme}`);
      const accessibility = await new AxeBuilder({ page })
        .include('.lia-multi-domain')
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze();
      expect(accessibility.violations).toEqual([]);
      expect(providerRequests).toEqual([]);
    });
  });
}
