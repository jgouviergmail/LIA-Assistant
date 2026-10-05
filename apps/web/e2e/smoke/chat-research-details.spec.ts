/** Actual archived research contracts through Docker's chat and native controls. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { test, expect, waitForHydration } from '../fixtures';
import { loadedChatRoutes } from '../fixtures/chat';
import { prepareTheme, awaitStyledPage, expectNoOverflow } from './overflow-report';

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
  { width: 1280, language: 'fr', theme: 'light', font: '16px' },
  { width: 390, language: 'en', theme: 'dark', font: '16px' },
  { width: 320, language: 'fr', theme: 'oled', font: '20px' },
] as const) {
  test.describe(`research input at ${sample.width}px`, () => {
    test.use({ hasTouch: sample.width < 500 });
    test(`complete research in ${sample.theme}`, async ({ page, authenticate, mockApi }) => {
      const reference = references.find(
        item => item.id === 'research_details' && item.language === sample.language
      );
      if (!reference) throw new Error('Missing backend research reference');
      await page.setViewportSize({ width: sample.width, height: 1200 });
      await page.emulateMedia({ reducedMotion: 'reduce' });
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
                id: '00000000-0000-4000-8000-00000000c404',
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
      await awaitStyledPage(page, 'research details');
      await page.addStyleTag({ content: 'nextjs-portal { display: none !important; }' });
      // The startup preference and account agree: switching the DOM theme
      // after hydration leaves WebKit with mixed light/dark inherited colors.
      if (sample.theme === 'light') {
        await expect(page.locator('html')).not.toHaveClass(/\bdark\b/);
      } else {
        await expect(page.locator('html')).toHaveClass(/\bdark\b/);
      }
      await expect(page.locator('html[data-oled]')).toHaveCount(sample.theme === 'oled' ? 1 : 0);
      await page.evaluate(font => {
        document.documentElement.style.fontSize = font;
      }, sample.font);
      await expect(page.locator('.lia-card')).toHaveCount(4);
      const article = page.locator('.lia-article');
      const articleToggle = article.locator('details').first().locator(':scope > summary');
      await articleToggle.focus();
      await articleToggle.press('Enter');
      await expect(article.getByText('LAST_ARTICLE_FACT', { exact: true })).toBeVisible();
      const categories = article.locator('details').last().locator(':scope > summary');
      if (sample.width < 500) await categories.tap();
      else await categories.press('Enter');
      await expect(article.getByText('Category 6', { exact: true })).toBeVisible();
      const answer = page.locator('.lia-search--answer');
      const sourceToggle = answer.locator('details').last().locator(':scope > summary');
      await sourceToggle.focus();
      await sourceToggle.press('Enter');
      const lastSource = answer.locator('li[value="9"] a');
      await expect(lastSource).toBeVisible();
      await expect(lastSource).toHaveAttribute(
        'href',
        'https://source8.example.test/received-article-8'
      );
      await expect(answer.locator('.lia-citation')).toHaveAttribute(
        'href',
        'https://source8.example.test/received-article-8'
      );
      expect((await lastSource.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      await expectNoOverflow(page, `research ${sample.width} ${sample.font}`);
      const accessibility = await new AxeBuilder({ page })
        .include('.lia-multi-domain')
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze();
      expect(accessibility.violations).toEqual([]);
      await page.screenshot({ path: test.info().outputPath(`research-${sample.theme}.png`) });
    });
  });
}
