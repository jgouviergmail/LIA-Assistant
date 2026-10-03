/** Geometry oracle for every real producer family, all locales and long labels. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
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
const samples = [
  { language: 'fr', width: 1280, theme: 'light' },
  { language: 'en', width: 390, theme: 'dark' },
  { language: 'de', width: 320, theme: 'oled' },
  { language: 'es', width: 320, theme: 'light' },
  { language: 'it', width: 1280, theme: 'dark' },
  { language: 'zh-CN', width: 390, theme: 'oled' },
];

for (const sample of samples) {
  test(`card alignment ${sample.language} ${sample.width} ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const html = references
      .filter(value => value.language === sample.language)
      .map(value => value.html)
      .join('\n');
    expect(html.length).toBeGreaterThan(0);
    await page.setViewportSize({ width: sample.width, height: 1400 });
    await authenticate({
      language: sample.language === 'zh-CN' ? 'zh' : sample.language,
      response_display_mode: 'html_cards',
    });
    await mockApi([
      ...loadedChatRoutes(),
      {
        url: '**/api/v1/conversations/me/messages*',
        json: {
          messages: [
            {
              id: '00000000-0000-4000-8000-00000000ca11',
              role: 'assistant',
              content: html,
              created_at: '2026-10-03T10:00:00Z',
              metadata: null,
            },
          ],
          conversation_id: '00000000-0000-4000-8000-000000000011',
          total_count: 1,
          has_more: false,
          next_cursor: null,
        },
      },
    ]);
    await page.goto(`/${sample.language === 'zh-CN' ? 'zh' : sample.language}/dashboard/chat`, {
      waitUntil: 'domcontentloaded',
    });
    await waitForHydration(page);
    await awaitStyledPage(page, 'all producer card alignment');
    await page.evaluate(theme => {
      document.documentElement.classList.toggle('dark', theme !== 'light');
      document.documentElement.toggleAttribute('data-oled', theme === 'oled');
      document.querySelectorAll<HTMLDetailsElement>('.lia-card details').forEach(value => {
        value.open = true;
      });
    }, sample.theme);
    const geometry = await page.evaluate(() => {
      const issues: string[] = [];
      let measured = 0;
      const selector =
        '.lia-card-top, .lia-chip, .lia-pill, .lia-tbadge, .lia-d-item, .lia-d-row, .lia-route__endpoint, .lia-route-step > summary, .lia-action-btn';
      for (const row of document.querySelectorAll<HTMLElement>(
        `.lia-response-wrapper[data-card-version="2"] :is(${selector})`
      )) {
        const symbol = row.querySelector<HTMLElement>(
          ':scope > .material-symbols-outlined, :scope > .lia-illus'
        );
        if (!symbol || !symbol.getClientRects().length || !row.getClientRects().length) continue;
        const rect = row.getBoundingClientRect();
        const style = getComputedStyle(row);
        const top = parseFloat(style.borderTopWidth) + parseFloat(style.paddingTop);
        const bottom = parseFloat(style.borderBottomWidth) + parseFloat(style.paddingBottom);
        const center = rect.top + top + (rect.height - top - bottom) / 2;
        const iconRect = symbol.getBoundingClientRect();
        const delta = Math.abs(iconRect.top + iconRect.height / 2 - center);
        measured++;
        if (delta > 1)
          issues.push(
            `${row.className}: ${symbol.textContent?.trim()} delta=${delta.toFixed(2)} text=${row.textContent?.trim().slice(0, 70)}`
          );
      }
      return { measured, issues };
    });
    expect(geometry.measured).toBeGreaterThan(100);
    expect(geometry.issues).toEqual([]);
    await expectNoOverflow(page, `all producer alignment ${sample.language}`);
  });
}
