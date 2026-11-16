/** Every argument and its complete vignette fit the narrowest supported reading width. */
import { test, expect } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

test.use({ viewport: { width: 320, height: 700 }, locale: 'fr-FR' });

for (const [language, path] of [
  ['fr', '/'],
  ['en', '/en'],
  ['de', '/de'],
  ['es', '/es'],
  ['it', '/it'],
  ['zh', '/zh'],
]) {
  test(`arguments ${language} keep their text and complete vignettes within 320px`, async ({
    page,
    mockApi,
  }) => {
    await mockApi([{ url: '**/api/v1/auth/me', status: 401, json: { detail: 'anonymous' } }]);
    await page.goto(path);
    await awaitStyledPage(page, `${language} arguments at 320px`);
    await expect(page.locator('html')).toHaveAttribute('lang', language);
    await expect(page.locator('#arguments article')).toHaveCount(5);
    await expect(page.locator('#arguments [data-vignette]')).toHaveCount(5);
    await expectNoOverflow(page, `${language} arguments at 320px`);

    // A constrained grid must also wrap long translated words inside its cards.
    const platformTitles = page.locator('#platform article h3');
    await expect(platformTitles).toHaveCount(5);
    const overflowingTitles = await platformTitles.evaluateAll(titles =>
      titles
        .filter(title => title.scrollWidth > title.clientWidth + 1)
        .map(title => title.textContent)
    );
    expect(overflowingTitles, `${language}: platform titles wrap within their cards`).toEqual([]);

    // The section must fit by reflow, not by clipping a decorative diagram.
    // Check the actual boxes of every visible glyph and bar within its frame.
    const clipped = await page.locator('#arguments [data-vignette]').evaluateAll(frames => {
      return frames.flatMap(frame => {
        const bounds = frame.getBoundingClientRect();
        return Array.from(frame.querySelectorAll('*')).flatMap(part => {
          const box = part.getBoundingClientRect();
          if (!box.width || !box.height) return [];
          const fits =
            box.left >= bounds.left - 1 &&
            box.right <= bounds.right + 1 &&
            box.top >= bounds.top - 1 &&
            box.bottom <= bounds.bottom + 1;
          return fits ? [] : [{ vignette: frame.getAttribute('data-vignette'), tag: part.tagName }];
        });
      });
    });
    expect(clipped, `${language}: every vignette stays complete`).toEqual([]);
  });
}
