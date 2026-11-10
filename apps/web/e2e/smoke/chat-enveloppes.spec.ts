/** Approved compact envelopes and invitations through real stored card HTML. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import type { Locator, Page } from '@playwright/test';
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
  { width: 1280, language: 'fr', theme: 'light', textScale: 1 },
  { width: 1280, language: 'fr', theme: 'dark', textScale: 1 },
  { width: 390, language: 'fr', theme: 'light', textScale: 1 },
  { width: 390, language: 'en', theme: 'dark', textScale: 1 },
  { width: 320, language: 'fr', theme: 'oled', textScale: 2 },
] as const;

test.use({ hasTouch: true });

async function captureCards(page: Page, area: Locator, filename: string): Promise<void> {
  const captureHeight = await area.evaluate(element => {
    const scrollport = element.closest('.chat-scrollbar');
    if (!scrollport) throw new Error('Missing chat scroll viewport');
    return Math.ceil(
      element.getBoundingClientRect().height + window.innerHeight - scrollport.clientHeight
    );
  });
  const viewport = page.viewportSize();
  if (!viewport) throw new Error('Missing fixed review viewport');
  const height = Math.max(1400, captureHeight + 2);
  // Firefox caps a screenshot dimension at 32767 physical pixels. Split the
  // evidence before resizing the viewport; keep every card and its full text.
  const maximumHeight = Math.floor(32767 / (await page.evaluate(() => window.devicePixelRatio)));
  if (height > maximumHeight) {
    const cards = area.locator('.lia-card');
    const count = await cards.count();
    if (!count) throw new Error(`A single review card exceeds the screenshot limit: ${filename}`);
    const stem = filename.replace(/\.png$/, '');
    for (let index = 0; index < count; index++)
      await captureCards(
        page,
        cards.nth(index),
        `${stem}-${String(index + 1).padStart(2, '0')}.png`
      );
    return;
  }
  try {
    await page.setViewportSize({ width: viewport.width, height });
    await area.screenshot({
      path: test.info().outputPath(filename),
      scale: 'css',
      style:
        'body * { visibility: hidden !important; } .lia-multi-domain, .lia-multi-domain * { visibility: visible !important; }',
    });
  } finally {
    await page.setViewportSize(viewport);
  }
}

async function expectCompletePaintedText(element: Locator): Promise<void> {
  const geometry = await element.evaluate(node => {
    const bounds = node.getBoundingClientRect();
    const range = document.createRange();
    range.selectNodeContents(node);
    return {
      text: node.textContent,
      fragments: [...range.getClientRects()].map(rect => ({
        left: rect.left - bounds.left,
        right: bounds.right - rect.right,
        top: rect.top - bounds.top,
        bottom: bounds.bottom - rect.bottom,
      })),
    };
  });
  expect(geometry.fragments.length, geometry.text ?? '').toBeGreaterThan(0);
  for (const fragment of geometry.fragments) {
    for (const inset of Object.values(fragment))
      expect(inset, geometry.text ?? '').toBeGreaterThanOrEqual(-1);
  }
}

for (const sample of samples) {
  test(`compact source-complete envelopes at ${sample.width}px ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const reference = references.find(
      item => item.id === 'enveloppes' && item.language === sample.language
    );
    if (!reference) throw new Error('Missing real-backend Enveloppes reference');
    await page.setViewportSize({ width: sample.width, height: 1400 });
    await prepareTheme(page, sample.theme);
    await authenticate({
      language: sample.language,
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
              id: '00000000-0000-4000-8000-00000000ec01',
              role: 'assistant',
              content: reference.html,
              created_at: '2026-11-07T12:00:00Z',
              metadata: null,
            },
          ],
          conversation_id: '00000000-0000-4000-8000-00000000ec02',
          total_count: 1,
          has_more: false,
          next_cursor: null,
        },
      },
    ]);
    await page.goto(`/${sample.language}/dashboard/chat`, { waitUntil: 'domcontentloaded' });
    await waitForHydration(page);
    await awaitStyledPage(page, 'Enveloppes');
    await expect(page.locator('.lia-email').first()).toBeVisible();
    await page.evaluate(scale => {
      document.documentElement.style.setProperty('--lia-text-scale', String(scale));
    }, sample.textScale);

    // The existing collection defers mounting the remainder until first open;
    // it must then retain those children and every complete received body.
    await expect(page.locator('.lia-email')).toHaveCount(3);
    await expect(page.locator('.lia-email:visible')).toHaveCount(3);
    if (sample.textScale === 1) {
      const firstEmail = page.locator('.lia-email').first();
      const attachment = await firstEmail.locator('.lia-chip--attach').boundingBox();
      const classification = await firstEmail
        .locator('.content-classification-badge')
        .boundingBox();
      if (!attachment || !classification) throw new Error('Missing attachment or classification');
      expect(
        Math.abs(
          attachment.y + attachment.height / 2 - classification.y - classification.height / 2
        )
      ).toBeLessThanOrEqual(1);
    }
    const moreMail = page.locator('.lia-card-collection > summary').first();
    await expect(moreMail).toContainText('(7)');
    await moreMail.focus();
    await moreMail.press('Enter');
    await expect(page.locator('.lia-email:visible')).toHaveCount(10);
    for (let index = 0; index < 10; index++) {
      await expectCompletePaintedText(page.locator('.lia-email__subject').nth(index));
      await expect(page.locator('.lia-email').nth(index)).toContainText(
        `EMAIL_COMPLETE_BODY_${index + 1}`
      );
    }
    await expect(moreMail).toBeFocused();
    await moreMail.press('Enter');
    await expect(page.locator('.lia-email:visible')).toHaveCount(3);
    await expect(page.locator('.lia-email')).toHaveCount(10);
    await moreMail.press('Enter');
    await expect(page.locator('.lia-email:visible')).toHaveCount(10);

    const participants = page.locator('.lia-event__participant');
    await expect(participants).toHaveCount(7);
    await expect(page.locator('.lia-event__participant:visible')).toHaveCount(5);
    const morePeople = page.locator('.lia-event__participants summary').first();
    await morePeople.focus();
    await morePeople.press('Enter');
    await expect(page.locator('.lia-event__participant:visible')).toHaveCount(7);
    await expect(morePeople).toBeFocused();

    for (const palette of ['default', 'ocean', 'forest', 'sunset', 'slate']) {
      await page.evaluate(
        value => document.documentElement.setAttribute('data-theme', value),
        palette
      );
      await expectNoOverflow(page, `Enveloppes ${palette} ${sample.width} ${sample.textScale}`);
      const scan = await new AxeBuilder({ page })
        .include('.lia-multi-domain')
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze();
      expect(scan.violations, `${palette} ${sample.theme}`).toEqual([]);
    }
    await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'default'));
    await captureCards(
      page,
      page.locator('.lia-multi-domain'),
      `ten-compact-${sample.width}-${sample.theme}.png`
    );

    // Inspect the actually visible complete messages, not merely text retained
    // inside closed details. The last fact must also be reachable by scrolling.
    await page.setViewportSize({ width: sample.width, height: 900 });
    for (let index = 0; index < 10; index++) {
      const email = page.locator('.lia-email').nth(index);
      for (const summary of await email.locator('summary').all()) {
        if (sample.width < 400) await summary.tap();
        else {
          await summary.focus();
          await summary.press('Enter');
        }
        expect((await summary.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      }
      const lastFact = email.getByText(new RegExp(`EMAIL_COMPLETE_BODY_${index + 1}\\.`));
      await expect(lastFact).toBeVisible();
      await lastFact.scrollIntoViewIfNeeded();
      await expect(lastFact).toBeInViewport();
      await expect(email).toContainText('alex@example.test');
      await expect(email).toContainText('louise@example.test');
    }
    const attachment = page.locator('.lia-email').first().locator('.lia-attachment');
    const filename = attachment.locator('.lia-attachment__name');
    await expect(filename).toHaveText('Plan du jardin.pdf');
    await expect(filename).toBeVisible();
    await expectCompletePaintedText(filename);
    await expect(attachment.locator('.lia-attachment__icon')).toBeVisible();
    await expect(attachment.locator('.lia-attachment__size')).toHaveText('(8.2KB)');
    await expectCompletePaintedText(attachment.locator('.lia-attachment__size'));
    await expectNoOverflow(page, `ten expanded ${sample.width} ${sample.theme}`);
    const expandedScan = await new AxeBuilder({ page })
      .include('.lia-multi-domain')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    expect(expandedScan.violations).toEqual([]);
    await captureCards(
      page,
      page.locator('.lia-multi-domain'),
      `ten-expanded-${sample.width}-${sample.theme}.png`
    );
    for (const family of ['email', 'event']) {
      const card = page.locator(`.lia-${family}`).first();
      await captureCards(page, card, `${family}-${sample.width}-${sample.theme}.png`);
    }
    await moreMail.focus();
    await moreMail.press('Enter');
    await expect(page.locator('.lia-email:visible')).toHaveCount(3);
    await expect(page.locator('.lia-email')).toHaveCount(10);
  });
}
