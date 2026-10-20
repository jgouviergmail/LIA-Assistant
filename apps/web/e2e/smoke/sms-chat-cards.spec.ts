/** Actual backend SMS renderer through stored chat and the production sanitizer. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { test, expect, waitForHydration } from '../fixtures';
import { loadedChatRoutes } from '../fixtures/chat';
import { prepareTheme, awaitStyledPage, expectNoOverflow } from './overflow-report';
const [{ html }] = JSON.parse(
  readFileSync(
    path.join(__dirname, '../../../api/tests/unit/domains/agents/sms/card_reference_corpus.json'),
    'utf8'
  )
) as { html: string }[];
for (const mode of ['cards', 'html_cards'] as const) {
  test(`SMS plaintext card in ${mode}`, async ({ page, authenticate, mockApi }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await prepareTheme(page, 'light');
    await authenticate({ language: 'fr', theme: 'light', response_display_mode: mode });
    await mockApi([
      ...loadedChatRoutes(),
      {
        url: '**/api/v1/conversations/me/messages*',
        json: {
          messages: [
            {
              id: '10000000-0000-4000-8000-000000000008',
              role: 'assistant',
              content: html,
              created_at: '2026-10-19T12:30:00Z',
              metadata: null,
            },
          ],
          conversation_id: '10000000-0000-4000-8000-000000000009',
          total_count: 1,
          has_more: false,
          next_cursor: null,
        },
      },
    ]);
    await page.goto('/fr/dashboard/chat', { waitUntil: 'domcontentloaded' });
    await waitForHydration(page);
    await awaitStyledPage(page, 'SMS card');
    await expect(page.locator('.lia-sms')).toContainText(
      'Oui. <script>window.smsLeak=true</script>'
    );
    await expect(page.locator('.lia-sms script')).toHaveCount(0);
    await expect(page.locator('.lia-sms a')).toHaveCount(1);
    await expect(page.locator('.lia-sms a')).toHaveAttribute(
      'href',
      '/fr/dashboard/sms?message=10000000-0000-4000-8000-000000000006'
    );
    await expectNoOverflow(page, `sms ${mode}`);
    const audit = await new AxeBuilder({ page }).include('.lia-sms').analyze();
    expect(
      audit.violations.filter(item => ['serious', 'critical'].includes(item.impact ?? ''))
    ).toEqual([]);
  });
}
