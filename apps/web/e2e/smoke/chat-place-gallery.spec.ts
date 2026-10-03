/** Real backend photo markup, hermetic media requests, and the Docker chat UI. */
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
const image =
  '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450"><rect width="800" height="450" fill="#b5d5cf"/><path d="M0 450V250L220 160L410 300L620 120L800 230V450Z" fill="#456c5c"/></svg>';

for (const sample of samples) {
  test(`manual place gallery at ${sample.width}px in ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const reference = references.find(
      item => item.id === 'gallery' && item.language === sample.language
    );
    if (!reference) throw new Error('Missing backend gallery reference');
    const requests: string[] = [];
    await page.setViewportSize({ width: sample.width, height: 1000 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await authenticate({ language: sample.language, response_display_mode: 'cards' });
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
    await page.route('**/api/v1/connectors/google-places/photo/**', async route => {
      const url = route.request().url();
      requests.push(url);
      const failed = url.includes('photo2?');
      await route.fulfill({
        status: failed ? 429 : 200,
        contentType: failed ? 'application/json' : 'image/svg+xml',
        body: failed ? '{"detail":"quota"}' : image,
        headers: {
          'Access-Control-Allow-Origin': 'https://localhost:3000',
          'Access-Control-Allow-Credentials': 'true',
          'Cache-Control': 'private, max-age=86400',
        },
      });
    });
    await page.goto(`/${sample.language}/dashboard/chat`);
    await waitForHydration(page);
    await awaitStyledPage(page, 'manual place gallery');
    await page.evaluate(theme => {
      document.documentElement.classList.toggle('dark', theme !== 'light');
      document.documentElement.toggleAttribute('data-oled', theme === 'oled');
    }, sample.theme);
    const gallery = page.locator('.lia-place-carousel');
    const thumbnail = gallery.locator('img');
    await expect(thumbnail).toHaveJSProperty('naturalWidth', 800);
    expect(requests).toHaveLength(1); // No eager photo or HD prefetch.
    expect(requests[0]).toContain('photo0?');
    await expect(page.getByRole('link', { name: 'Photographe 1', exact: true })).toBeVisible();
    const heroBox = await page.locator('.lia-place__photo').boundingBox();
    const frameBox = await gallery.boundingBox();
    const captionBox = await page.locator('.lia-place__photo .lia-photo-attribution').boundingBox();
    expect(
      (heroBox?.height ?? 0) - (frameBox?.height ?? 0) - (captionBox?.height ?? 0)
    ).toBeLessThan(8);
    for (const control of await gallery.locator('button:visible').all()) {
      const box = await control.boundingBox();
      expect(box?.width).toBeGreaterThanOrEqual(44);
      expect(box?.height).toBeGreaterThanOrEqual(44);
    }
    await gallery.focus();
    await gallery.press('ArrowRight');
    await expect(thumbnail).toHaveAttribute('src', /photo1\?/);
    await expect(thumbnail).toHaveJSProperty('naturalWidth', 800);
    await expect(page.getByRole('link', { name: 'Photographe 2', exact: true })).toBeVisible();
    expect(requests.some(url => url.includes('photo2?'))).toBe(false);
    const expand = gallery.getByRole('button', { name: /plein écran|full screen/ });
    await expand.click();
    const dialog = page.getByRole('dialog', { name: 'Le Jardin des Saveurs' });
    await expect(dialog).toBeVisible();
    await expect(dialog).toBeFocused();
    await expect(dialog.locator('img')).toHaveAttribute(
      'src',
      (await thumbnail.getAttribute('src')) ?? ''
    );
    await expect(dialog.getByRole('link', { name: 'Photographe 2', exact: true })).toBeVisible();
    await page.keyboard.press('ArrowLeft');
    await expect(dialog.locator('img')).toHaveAttribute('src', /photo0\?/);
    await expect(dialog.getByRole('link', { name: 'Photographe 1', exact: true })).toBeVisible();
    await expect(dialog.getByRole('link').last()).toHaveAttribute(
      'href',
      'https://example.test/photo0'
    );
    await page.keyboard.press('Tab');
    expect(await dialog.evaluate(el => el.contains(document.activeElement))).toBe(true);
    expect(await dialog.evaluate(el => getComputedStyle(el).animationName)).toBe('none');
    await expectNoOverflow(page, `gallery ${sample.width} ${sample.theme}`);
    const accessibility = await new AxeBuilder({ page })
      .include('[role="dialog"]')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    expect(accessibility.violations).toEqual([]);
    await dialog.screenshot({
      path: test.info().outputPath(`gallery-fullscreen-${sample.theme}.png`),
      style: 'nextjs-portal { display: none !important; }',
    });
    await page.keyboard.press('Escape');
    await expect(expand).toBeFocused();
    await page
      .locator('.lia-card')
      .screenshot({ path: test.info().outputPath(`gallery-${sample.theme}.png`) });
    await gallery.focus();
    await gallery.press('End');
    await expect(gallery.getByText(/indisponible|unavailable/)).toBeVisible();
    await expect(expand).toBeDisabled();
    const failures = requests.filter(url => url.includes('photo2?')).length;
    await gallery.press('ArrowLeft');
    await expect(thumbnail).toHaveAttribute('src', /photo1\?/);
    expect(requests.filter(url => url.includes('photo2?'))).toHaveLength(failures);
    // Routing disables browser caching: identical inline/modal URLs are verified above.
    // The provider cache/billing contract is exercised separately by backend tests.
  });
}
