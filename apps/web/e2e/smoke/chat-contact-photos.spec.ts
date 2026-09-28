/** Contact photos fill their card frame, including previously saved HTML. */
import { readFileSync } from 'node:fs';
import path from 'node:path';

import { test, expect, waitForHydration, chatRoutes, type MockRoute } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const corpus = JSON.parse(
  readFileSync(
    path.join(__dirname, '../../../api/tests/unit/domains/agents/display/contact_card_corpus.json'),
    'utf8'
  )
) as { id: string; html: string; legacyHtml: string }[];

// Deliberately non-square. A default markdown/profile wrapper either cuts the
// image's centre or draws a rectangle instead of filling the 42px contact slot.
const PORTRAIT =
  '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="180" viewBox="0 0 120 180">' +
  '<rect width="120" height="180" fill="#c7d2fe"/>' +
  '<circle cx="60" cy="75" r="28" fill="#4f46e5"/>' +
  '<path d="M20 180v-35a40 40 0 0 1 80 0v35" fill="#4f46e5"/></svg>';

function routes(answer: string): MockRoute[] {
  return [
    ...chatRoutes([]),
    {
      url: '**/api/v1/conversations/me',
      json: {
        id: '00000000-0000-4000-8000-0000000000ff',
        user_id: '00000000-0000-4000-8000-000000000001',
        title: 'Contacts',
        message_count: 0,
        total_tokens: 0,
        created_at: '2026-09-28T08:00:00Z',
        updated_at: '2026-09-28T08:00:00Z',
      },
    },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async route => {
        await route.fulfill({
          contentType: 'text/event-stream',
          body:
            `data: ${JSON.stringify({ type: 'token', content: answer })}\n\n` +
            'data: {"type":"done","content":"","metadata":null}\n\n',
        });
      },
    },
    {
      url: '**/api/v1/auth/profile-image-proxy*',
      handler: route => route.fulfill({ contentType: 'image/svg+xml', body: PORTRAIT }),
    },
    {
      url: '**/api/v1/connectors/microsoft/contacts/photo/contact-a',
      handler: route => route.fulfill({ contentType: 'image/svg+xml', body: PORTRAIT }),
    },
  ];
}

for (const width of [1280, 390]) {
  test(`contact photos stay centred in their frames at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ response_display_mode: 'cards' });
    const answer = ['html', 'legacyHtml']
      .map(key => corpus.map(item => item[key as 'html' | 'legacyHtml']).join(''))
      .join('');
    await mockApi(routes('<div class="lia-response">' + answer + '</div>'));
    await page.route('https://contacts.example.test/**', route =>
      route.fulfill({ contentType: 'image/svg+xml', body: PORTRAIT })
    );
    // Even the broken version remains hermetic: capture a direct Google
    // preload while asserting below that the displayed source is proxied.
    await page.route('https://lh3.googleusercontent.com/**', route =>
      route.fulfill({ contentType: 'image/svg+xml', body: PORTRAIT })
    );
    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await awaitStyledPage(page, 'contact card photos');
    await page.locator('textarea').fill('Affiche mes contacts');
    await page.keyboard.press('Enter');
    const cards = page.locator('.lia-card.lia-contact');
    await expect(cards).toHaveCount(corpus.length * 2);
    for (const card of await cards.all()) {
      const slot = card.locator('.lia-card-top > .lia-illus');
      const photo = slot.locator('img');
      if ((await photo.count()) === 0) {
        await expect(slot).toHaveText('LD');
        continue;
      }
      await expect(photo).toHaveCSS('opacity', '1');
      await expect(photo).toHaveCSS('object-fit', 'cover');
      await expect(slot.locator('button')).toHaveCount(0);
      const bounds = await photo.evaluate(node => {
        const image = node as HTMLImageElement;
        const frame = image.closest('.lia-illus')!;
        const a = image.getBoundingClientRect();
        const b = frame.getBoundingClientRect();
        return {
          direct: image.parentElement === frame,
          loaded: image.complete && image.naturalWidth > 0,
          frame: { x: b.x, y: b.y, width: b.width, height: b.height },
          image: { x: a.x, y: a.y, width: a.width, height: a.height },
        };
      });
      expect(bounds.direct).toBe(true);
      expect(bounds.loaded).toBe(true);
      expect(bounds.frame.width).toBe(42);
      expect(bounds.frame.height).toBe(42);
      expect(bounds.image).toEqual(bounds.frame);
    }
    await expect(cards.locator('img[src*="profile-image-proxy"]')).toHaveCount(2);
    await expectNoOverflow(page, `contact card photos ${width}`);
  });
}
