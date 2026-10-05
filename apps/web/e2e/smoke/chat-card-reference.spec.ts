/** Real backend cards through stored chat + sanitizer + the Docker-served UI. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { test, expect, waitForHydration } from '../fixtures';
import { loadedChatRoutes } from '../fixtures/chat';
import { prepareTheme, awaitStyledPage, expectNoOverflow } from './overflow-report';

interface Reference {
  id: string;
  language: string;
  html: string;
}

const samples = [
  { width: 1280, language: 'fr', theme: 'light' },
  { width: 390, language: 'en', theme: 'dark' },
  { width: 320, language: 'fr', theme: 'oled' },
];

test.use({ hasTouch: true });

const references: Reference[] = JSON.parse(
  readFileSync(
    path.join(
      __dirname,
      '../../../api/tests/unit/domains/agents/display/card_reference_corpus.json'
    ),
    'utf8'
  )
);

for (const sample of samples) {
  test(`native Microsoft facts at ${sample.width}px in ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const reference = references.find(
      item => item.id === 'microsoft' && item.language === sample.language
    );
    if (!reference) throw new Error('Missing native Microsoft reference');
    await page.setViewportSize({ width: sample.width, height: 1400 });
    await prepareTheme(page, sample.theme);
    await authenticate({
      language: sample.language,
      theme: sample.theme as 'light' | 'dark' | 'oled',
      response_display_mode: 'html_cards',
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
    await page.goto(`/${sample.language}/dashboard/chat`, { waitUntil: 'domcontentloaded' });
    await waitForHydration(page);
    await awaitStyledPage(page, 'native Microsoft facts');
    await page.addStyleTag({ content: 'nextjs-portal { display: none !important; }' });

    for (const summary of await page.locator('.lia-card summary').all()) {
      if (sample.width === 320) await summary.tap();
      else {
        await summary.focus();
        await summary.press('Enter');
      }
      expect((await summary.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    }
    await expect(page.locator('.lia-task')).toContainText(
      sample.language === 'en' ? 'In progress' : 'En cours'
    );
    await expect(page.locator('.lia-task')).toContainText('Design');
    await expect(page.locator('.lia-task')).toContainText('Accessibilité');
    await expect(page.locator('.lia-event')).toContainText(/monday|lundi/i);
    await expect(page.locator('.lia-event')).toContainText(/friday|vendredi/i);
    await expect(page.locator('.lia-event')).toContainText('12');
    await expect(page.locator('.lia-event .lia-chip-row').first()).toContainText(
      sample.language === 'en' ? '9:00 AM' : '09:00'
    );
    await expect(page.locator('.lia-calendar')).toContainText(
      sample.language === 'en' ? 'Can edit' : 'Modification autorisée'
    );
    await expect(page.locator('.lia-calendar')).not.toContainText(/owner|propriétaire/i);
    await expectNoOverflow(page, `native Microsoft ${sample.width} ${sample.theme}`);
    const accessibility = await new AxeBuilder({ page })
      .include('.lia-multi-domain')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    expect(accessibility.violations).toEqual([]);
    await page
      .locator('.lia-multi-domain')
      .screenshot({ path: test.info().outputPath(`microsoft-${sample.theme}.png`) });
  });
}

for (const sample of samples) {
  test(`read-only snapshots at ${sample.width}px in ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const reference = references.find(
      item => item.id === 'snapshots' && item.language === sample.language
    );
    if (!reference) throw new Error('Missing backend snapshot reference');
    await page.setViewportSize({ width: sample.width, height: 1200 });
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
              id: '00000000-0000-4000-8000-00000000c403',
              role: 'assistant',
              content: reference.html,
              created_at: '2025-03-18T09:30:00Z',
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
    await awaitStyledPage(page, 'read-only snapshots');

    await expect(page.locator('[data-card-version="2"] > .lia-card')).toHaveCount(2);
    await expect(page.getByText('Lampe du bureau', { exact: true })).toBeVisible();
    await expect(page.getByText('Préparer la visite', { exact: true })).toBeVisible();
    await expect(page.locator('.lia-hues')).toContainText('0%');
    await expect(page.locator('.lia-tickets')).toContainText('LIA');
    await expect(page.locator('.lia-card button')).toHaveCount(0);
    await expectNoOverflow(page, `snapshots ${sample.width} ${sample.theme}`);
    const accessibility = await new AxeBuilder({ page })
      .include('.lia-multi-domain')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    expect(accessibility.violations).toEqual([]);
    await page.locator('.lia-multi-domain').screenshot({
      path: test.info().outputPath(`snapshots-${sample.theme}.png`),
      style: 'nextjs-portal { display: none !important; }',
    });
  });
}

for (const sample of samples) {
  test(`complete card details at ${sample.width}px in ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const reference = references.find(
      item => item.id === 'details' && item.language === sample.language
    );
    if (!reference) throw new Error('Missing backend detail reference');
    await page.setViewportSize({ width: sample.width, height: 1800 });
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
              id: '00000000-0000-4000-8000-00000000c402',
              role: 'assistant',
              content: reference.html,
              created_at: '2025-03-18T09:30:00Z',
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
    await awaitStyledPage(page, 'complete card details');

    await expect(page.locator('[data-card-version="2"] > .lia-card')).toHaveCount(5);
    for (const summary of await page.locator('.lia-card summary').all()) {
      await summary.focus();
      await summary.press('Enter');
      await expect(summary).toBeFocused();
      const box = await summary.boundingBox();
      expect(box?.height).toBeGreaterThanOrEqual(44);
    }
    await expect(page.getByText('Étape 13', { exact: true })).toBeVisible();
    await expect(page.getByText('camille4@example.test', { exact: true })).toBeVisible();
    await expect(page.getByText('participant13@example.test', { exact: true })).toBeVisible();
    await expect(page.locator('.lia-contact')).toContainText('Camille Dupont');
    await expect(page.locator('.lia-contact')).toContainText('Robotique');
    await expect(page.locator('.lia-contact')).toContainText('Laboratoire du Sud');
    await expect(page.locator('.lia-contact')).toContainText('Accessibilité');
    await expect(page.locator('.lia-file')).toContainText('Robin');
    await expect(page.locator('.lia-file')).toContainText('design@example.test');
    await expect(page.getByRole('progressbar')).toHaveAttribute('value', '6');
    await expect(page.getByRole('progressbar')).toHaveAttribute('max', '13');
    await expectNoOverflow(page, `complete details ${sample.width} ${sample.theme}`);
    const accessibility = await new AxeBuilder({ page })
      .include('.lia-multi-domain')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    expect(accessibility.violations).toEqual([]);
    await page.setViewportSize({ width: sample.width, height: 4000 });
    for (const domain of ['task', 'contact', 'event', 'file', 'calendar']) {
      const card = page.locator(`.lia-card.lia-${domain}`).first();
      await card.scrollIntoViewIfNeeded();
      await card.screenshot({
        path: test.info().outputPath(`${domain}-${sample.theme}.png`),
        style: 'nextjs-portal { display: none !important; }',
      });
    }
  });
}

for (const sample of samples) {
  test(`backend reference cards at ${sample.width}px in ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const reference = references.find(
      item => item.id === 'mixed' && item.language === sample.language
    );
    if (!reference) throw new Error('Missing backend reference');
    await page.setViewportSize({ width: sample.width, height: 900 });
    await prepareTheme(page, sample.theme);
    await authenticate({
      language: sample.language,
      theme: sample.theme as 'light' | 'dark' | 'oled',
      response_display_mode: 'html_cards',
    });
    await mockApi([
      ...loadedChatRoutes(),
      {
        url: '**/api/v1/conversations/me/messages*',
        json: {
          messages: [
            {
              id: '00000000-0000-4000-8000-00000000c401',
              role: 'assistant',
              content: reference.html,
              created_at: '2025-03-18T09:30:00Z',
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
    await awaitStyledPage(page, 'backend reference cards');

    const cards = page.locator('[data-card-version="2"] > .lia-card');
    await expect(cards).toHaveCount(4);
    for (const identity of ['Votre voyage à Lyon est confirmé', 'Le Jardin des Saveurs', 'Lyon']) {
      await expect(page.getByText(identity, { exact: true }).first()).toBeVisible();
    }
    await expect(page.locator('.lia-route')).toContainText('Gare de Lyon Part-Dieu');
    await expect(page.locator('.lia-weather')).toContainText('18°C');
    await expectNoOverflow(page, `reference ${sample.width} ${sample.theme}`);
    const accessibility = await new AxeBuilder({ page })
      .include('.lia-multi-domain')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    expect(accessibility.violations).toEqual([]);
    const sizes = await cards.evaluateAll(nodes =>
      nodes.map(node => ({
        overflow: node.scrollWidth - node.clientWidth,
        font: getComputedStyle(node).fontFamily,
      }))
    );
    expect(sizes.every(size => size.overflow <= 1)).toBe(true);
    expect(sizes.every(size => size.font.length > 0)).toBe(true);

    const summary = page.locator('.lia-email summary').first();
    await summary.focus();
    await page.keyboard.press('Enter');
    await expect(summary).toBeFocused();
    await page.setViewportSize({ width: sample.width, height: 1800 });
    for (const domain of ['email', 'place', 'route', 'weather']) {
      const card = page.locator(`.lia-card.lia-${domain}`).first();
      await card.scrollIntoViewIfNeeded();
      await card.screenshot({ path: test.info().outputPath(`${domain}-${sample.theme}.png`) });
    }
    await page.setViewportSize({ width: sample.width, height: 900 });
    await expect(page.locator('.lia-email details').first()).toHaveAttribute('open', '');
    await expect(
      page.getByText('Votre réservation est confirmée.', { exact: false })
    ).toBeVisible();
    const target = await summary.boundingBox();
    expect(target?.height).toBeGreaterThanOrEqual(44);
    await page.keyboard.press('Enter');
    await expect(page.locator('.lia-email details').first()).not.toHaveAttribute('open');
    await expect(summary).toBeFocused();
    await page.screenshot({
      path: test.info().outputPath(`reference-${sample.theme}.png`),
      fullPage: true,
    });
  });
}
