/** MCP's received snapshots survive native disclosures and the Markdown boundary. */
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
  { width: 1280, language: 'fr', theme: 'light' },
  { width: 390, language: 'en', theme: 'dark' },
  { width: 320, language: 'fr', theme: 'oled' },
]) {
  test.describe(`MCP at ${sample.width}px`, () => {
    test.use({ hasTouch: sample.width < 500 });
    test(`full received data in ${sample.theme}`, async ({ page, authenticate, mockApi }) => {
      const reference = references.find(
        item => item.id === 'mcp_details' && item.language === sample.language
      );
      if (!reference) throw new Error('Missing backend MCP reference');
      await page.setViewportSize({ width: sample.width, height: 1200 });
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await prepareTheme(page, sample.theme);
      await authenticate({
        language: sample.language,
        theme: sample.theme as 'light' | 'dark' | 'oled',
        response_display_mode: 'cards',
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
      await page.goto(`/${sample.language}/dashboard/chat`);
      await waitForHydration(page);
      await awaitStyledPage(page, 'MCP details');
      await page.addStyleTag({ content: 'nextjs-portal { display: none !important; }' });
      const card = page.locator('.lia-mcp');
      await expect(card).toHaveCount(1);
      await expect(card).not.toContainText('SECRET_NOT_DISPLAYED');
      const result = card.locator('details').first();
      const resultTrigger = result.locator(':scope > summary');
      await expect(result).not.toHaveAttribute('open', '');
      await expect(card.locator('.lia-mcp__metadata a')).toHaveAttribute(
        'href',
        'https://mcp.example.test'
      );
      await expect(card.locator('.lia-mcp__metadata a')).toBeVisible();
      await expect(card.locator('.lia-mcp__metadata code')).toHaveText('list_items');
      await expect(card.locator('.lia-mcp__metadata code')).toBeVisible();
      await expect(card.getByText('Received field 8', { exact: true })).toBeHidden();
      await resultTrigger.focus();
      await resultTrigger.press('Enter');
      await expect(result).toHaveAttribute('open', '');
      const description = result.locator('details').first().locator(':scope > summary');
      await description.focus();
      await description.press('Enter');
      await expect(
        card.locator('.lia-card-text').filter({ hasText: 'MCP_LAST_DESCRIPTION' })
      ).toBeVisible();
      const fields = result.locator('details').nth(1).locator(':scope > summary');
      if (sample.width < 500) await fields.tap();
      else {
        await fields.focus();
        await fields.press('Enter');
      }
      await expect(card.getByText('Received field 8', { exact: true })).toBeVisible();
      const nested = card.locator('dd details > summary').first();
      await nested.focus();
      await nested.press('Enter');
      await expect(card.locator('.lia-raw-block')).toContainText('MCP_LAST_NESTED');
      await expect(card.locator('.lia-raw-block')).toBeVisible();
      expect((await fields.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      expect((await resultTrigger.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      await expectNoOverflow(page, `MCP ${sample.width}`);
      const accessibility = await new AxeBuilder({ page })
        .include('.lia-mcp')
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze();
      expect(accessibility.violations).toEqual([]);
      await page.screenshot({ path: test.info().outputPath(`mcp-${sample.theme}.png`) });
      if (sample.width < 500) await resultTrigger.tap();
      else await resultTrigger.press('Space');
      await expect(result).not.toHaveAttribute('open', '');
      await expect(card.locator('.lia-raw-block')).toBeHidden();
      await expect(card.locator('.lia-mcp__metadata code')).toBeVisible();
      await resultTrigger.press('Enter');
      await expect(card.locator('.lia-raw-block')).toBeVisible();
      await expect(card.locator('.lia-raw-block')).toContainText('MCP_LAST_NESTED');
    });
  });
}
