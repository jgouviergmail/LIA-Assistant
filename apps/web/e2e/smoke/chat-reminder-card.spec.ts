/** A received recurring reminder remains complete across compact and enlarged layouts. */
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
  { width: 1280, theme: 'light', scale: 1 },
  { width: 1280, theme: 'dark', scale: 1 },
  { width: 390, theme: 'light', scale: 1 },
  { width: 390, theme: 'dark', scale: 1 },
  { width: 320, theme: 'oled', scale: 2 },
] as const) {
  test(`complete reminder ${sample.width} ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const reference = references.find(item => item.id === 'reminders' && item.language === 'fr');
    if (!reference) throw new Error('Missing actual backend reminder reference');
    await page.setViewportSize({ width: sample.width, height: 1000 });
    await prepareTheme(page, sample.theme);
    await authenticate({
      language: 'fr',
      theme: sample.theme,
      response_display_mode: 'html_cards',
    });
    await mockApi([
      ...loadedChatRoutes(),
      {
        url: '**/api/v1/conversations/me/messages*',
        json: {
          messages: [
            {
              id: '00000000-0000-4000-8000-00000000ed01',
              role: 'assistant',
              content: reference.html,
              created_at: '2026-11-08T12:00:00Z',
              metadata: null,
            },
          ],
          conversation_id: '00000000-0000-4000-8000-00000000ed02',
          total_count: 1,
          has_more: false,
          next_cursor: null,
        },
      },
    ]);
    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await awaitStyledPage(page, 'complete reminder');
    await page.evaluate(
      scale => document.documentElement.style.setProperty('--lia-text-scale', String(scale)),
      sample.scale
    );
    const card = page.locator('.lia-card.lia-reminder');
    await expect(card.getByText(/REMINDER_COMPLETE_CONTENT/)).toBeVisible();
    const paintedContent = await card.locator('.lia-reminder__label').evaluate(label => {
      const owner = label.closest('.lia-reminder');
      if (!owner) throw new Error('Missing reminder card');
      const labelBounds = label.getBoundingClientRect();
      const cardBounds = owner.getBoundingClientRect();
      const range = document.createRange();
      range.selectNodeContents(label);
      return [...range.getClientRects()].map(rect => ({
        left: rect.left - Math.max(labelBounds.left, cardBounds.left),
        right: Math.min(labelBounds.right, cardBounds.right) - rect.right,
        top: rect.top - Math.max(labelBounds.top, cardBounds.top),
        bottom: Math.min(labelBounds.bottom, cardBounds.bottom) - rect.bottom,
      }));
    });
    expect(paintedContent.length).toBeGreaterThan(0);
    for (const fragment of paintedContent)
      for (const inset of Object.values(fragment)) expect(inset).toBeGreaterThanOrEqual(-1);
    for (const fact of ['2027', '09:30', '14:15', 'Europe/Paris'])
      await expect(card).toContainText(fact);
    await expectNoOverflow(page, `reminder ${sample.width} ${sample.theme} ${sample.scale}`);
    const scan = await new AxeBuilder({ page })
      .include('.lia-reminder')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    expect(scan.violations).toEqual([]);
    const height = await card.evaluate(element => {
      const scrollport = element.closest('.chat-scrollbar');
      if (!scrollport) throw new Error('Missing chat scroll viewport');
      return Math.ceil(
        element.getBoundingClientRect().height + window.innerHeight - scrollport.clientHeight + 2
      );
    });
    const viewport = page.viewportSize();
    if (!viewport) throw new Error('Missing fixed review viewport');
    // Capture only: retain the interaction width and keep sticky chat chrome
    // from covering the first or last facts in a vertically enlarged image.
    try {
      await page.setViewportSize({ width: viewport.width, height: Math.max(1000, height) });
      // A real reader gesture releases the chat's initial bottom pin before
      // measuring the capture. Otherwise its next frame can move the card
      // between Playwright's clip calculation and the browser's screenshot.
      await card.hover();
      await page.mouse.wheel(0, -1);
      await card.scrollIntoViewIfNeeded();
      await expect
        .poll(() =>
          card.evaluate(element => {
            const scrollport = element.closest('.chat-scrollbar');
            if (!scrollport) throw new Error('Missing chat scroll viewport');
            const bounds = element.getBoundingClientRect();
            const visible = scrollport.getBoundingClientRect();
            return Math.min(
              bounds.top - visible.top,
              visible.bottom - bounds.bottom,
              bounds.left - visible.left,
              visible.right - bounds.right
            );
          })
        )
        .toBeGreaterThanOrEqual(-1);
      await card.screenshot({
        path: test.info().outputPath(`reminder-${sample.width}-${sample.theme}.png`),
        style:
          'body * { visibility: hidden !important; } .lia-multi-domain, .lia-multi-domain * { visibility: visible !important; }',
      });
    } finally {
      await page.setViewportSize(viewport);
    }
  });
}
