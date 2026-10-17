/** Native producer facts survive storage, sanitizer, touch and all three themes. */
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
const samples = [
  { width: 1280, language: 'fr', theme: 'light' },
  { width: 390, language: 'en', theme: 'dark' },
  { width: 320, language: 'fr', theme: 'oled' },
];
test.use({ hasTouch: true });

for (const sample of samples) {
  test(`native supplemental details at ${sample.width}px in ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const reference = references.find(
      item => item.id === 'native_details' && item.language === sample.language
    );
    if (!reference) throw new Error('Missing native details reference');
    const auditedViewport = { width: sample.width, height: 1400 };
    await page.setViewportSize(auditedViewport);
    await authenticate({ language: sample.language, response_display_mode: 'html_cards' });
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
    await page.goto(`/${sample.language}/dashboard/chat`, { waitUntil: 'domcontentloaded' });
    await waitForHydration(page);
    await awaitStyledPage(page, 'native supplemental details');
    await page.addStyleTag({ content: 'nextjs-portal { display: none !important; }' });
    await page.evaluate(theme => {
      document.documentElement.classList.toggle('dark', theme !== 'light');
      document.documentElement.toggleAttribute('data-oled', theme === 'oled');
    }, sample.theme);
    const summaries = page.locator('.lia-card summary');
    for (const summary of await summaries.all()) {
      if (sample.width === 320) await summary.tap();
      else {
        await summary.focus();
        await summary.press('Enter');
      }
      expect((await summary.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    }
    await expect(page.locator('meter')).toHaveAttribute('value', '0');
    expect(await page.locator('meter').getAttribute('aria-label')).toBeTruthy();
    await expect(page.locator('.lia-hues')).toContainText('4000 K');
    await expect(page.locator('.lia-hues')).toContainText('0.3');
    await expect(page.locator('.lia-hues')).toContainText('0.4');
    await expect(page.locator('.lia-calendar')).toContainText('My garden');
    await expect(page.locator('.lia-calendar')).toContainText('Original garden');
    await expect(page.locator('.lia-calendar')).toContainText('22 Garden Street');
    await expect(page.locator('.lia-calendar')).toContainText('garden@example.test');
    await expect(page.locator('.lia-contact')).toContainText('Received pronunciation');
    await expect(page.locator('.lia-contact time').first()).toHaveAttribute(
      'datetime',
      '2021-04-05'
    );
    await expect(page.locator('.lia-event')).toContainText('Alternate video');
    await expect(page.locator('.lia-event')).toContainText('123456');
    await expect(page.locator('.lia-event')).not.toContainText('PROVIDER_ID_NOT_DISPLAYED');
    for (const fact of ['LAST_DESCRIPTION', 'LAST_COMMENT', 'Step one', '0 €'])
      await expect(page.locator('.lia-tickets')).toContainText(fact);
    for (const link of await page.locator('.lia-conference-point').all())
      expect((await link.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    await expectNoOverflow(page, `native details ${sample.width} ${sample.theme}`);
    const accessibility = await new AxeBuilder({ page })
      .include('.lia-multi-domain')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    expect(accessibility.violations).toEqual([]);
    // A fixed 4000px WebKit backing surface exhausted the budget after axe passed.
    // Size capture-only expansion from the card and its actual scrollport: tall
    // mobile tickets must fit without clipping, while short cards keep the
    // audited viewport. Locator screenshots already scroll the card into view.
    for (const domain of ['hues', 'contact', 'calendar', 'event', 'tickets']) {
      const card = page.locator(`.lia-${domain}`);
      const captureHeight = await card.evaluate(element => {
        const scrollport = element.closest('.chat-scrollbar');
        if (!scrollport) throw new Error('Missing chat scroll viewport');
        return Math.ceil(
          element.getBoundingClientRect().height + window.innerHeight - scrollport.clientHeight
        );
      });
      const expandCapture = captureHeight > auditedViewport.height;
      if (expandCapture) await page.setViewportSize({ ...auditedViewport, height: captureHeight });
      await card.screenshot({
        path: test.info().outputPath(`native-${domain}-${sample.theme}.png`),
        // Isolate the card's image from sticky chrome and the floating companion.
        // This is applied only during capture, after every functional/axe check.
        style:
          'body * { visibility: hidden !important; } .lia-card, .lia-card * { visibility: visible !important; }',
      });
      if (expandCapture) await page.setViewportSize(auditedViewport);
    }
  });
}
