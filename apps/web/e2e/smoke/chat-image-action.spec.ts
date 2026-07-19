/**
 * Chat journey — markdown image action is keyboard-operable (audit F013).
 *
 * Hermetic: the conversation history is mocked with one assistant message
 * containing a Google-Places photo (markdown image), the photo endpoint
 * returns a real 1x1 PNG, everything else dies on the 501 catch-all. Proves,
 * in a real browser accessibility tree, that the image-open action is a named
 * native button reachable and operable from the keyboard, opening the
 * lightbox exactly once, and that Escape closes it.
 */
import { test, expect, type MockRoute } from '../fixtures';

// Minimal valid 1x1 transparent PNG.
const PNG_1X1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
  'base64'
);

const assistantMessage = {
  id: '00000000-0000-4000-8000-00000000m001',
  role: 'assistant',
  content:
    'Voici la terrasse :\n\n![Terrasse du café](/api/v1/connectors/google-places/photo?ref=abc)',
  message_metadata: null,
  created_at: '2026-07-15T10:00:00Z',
  tokens_in: null,
  tokens_out: null,
  tokens_cache: null,
  cost_eur: null,
  google_api_requests: null,
  stt_provider: null,
};

const chatData: MockRoute[] = [
  {
    url: '**/api/v1/conversations/me',
    json: {
      id: '00000000-0000-4000-8000-00000000c001',
      user_id: '00000000-0000-4000-8000-000000000001',
      title: 'E2E',
      message_count: 1,
      total_tokens: 0,
      created_at: '2026-07-15T09:00:00Z',
      updated_at: '2026-07-15T10:00:00Z',
    },
  },
  {
    url: '**/api/v1/conversations/me/messages*',
    json: {
      messages: [assistantMessage],
      conversation_id: '00000000-0000-4000-8000-00000000c001',
      total_count: 1,
      has_more: false,
      next_cursor: null,
    },
  },
  { url: '**/api/v1/conversations/me/totals', json: {} },
  {
    url: '**/api/v1/agents/health',
    json: { status: 'healthy', graph_compiled: true },
  },
  {
    url: '**/api/v1/connectors/google-places/photo*',
    handler: async route => {
      await route.fulfill({ status: 200, contentType: 'image/png', body: PNG_1X1 });
    },
  },
];

test.describe('chat markdown image action', () => {
  test('image-open button is named, keyboard-activated once, Escape closes', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(chatData);

    await page.goto('/en/dashboard/chat');

    // The action is a real named button in the browser accessibility tree.
    const expand = page.getByRole('button', { name: 'View image full screen' });
    await expect(expand).toBeVisible();

    await expand.focus();
    await expect(expand).toBeFocused();
    await page.keyboard.press('Enter');

    // Exactly ONE lightbox opened: one close button, image visible full screen.
    const closeButtons = page.getByRole('button', { name: 'Close' });
    await expect(closeButtons).toHaveCount(1);

    await page.keyboard.press('Escape');
    await expect(closeButtons).toHaveCount(0);
  });
});

test.describe('image lightbox modal semantics', () => {
  test('is a named modal that takes focus and gives it back', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(chatData);
    await page.goto('/en/dashboard/chat');

    const expand = page.getByRole('button', { name: 'View image full screen' });
    await expand.focus();
    await page.keyboard.press('Enter');

    // Real accessibility tree: the overlay is a modal dialog named after the
    // picture — jsdom cannot prove this, only a browser can.
    const dialog = page.getByRole('dialog', { name: 'Terrasse du café' });
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute('aria-modal', 'true');

    // The controls live inside the dialog: a screen-reader user who lands here
    // reaches Close without leaving the modal.
    await expect(dialog.getByRole('button', { name: 'Close' })).toBeVisible();

    // Focus moved into the dialog…
    await expect(dialog).toBeFocused();

    // Tab stays inside. `aria-modal` above tells assistive tech the rest of the
    // page is inert; nothing in the DOM enforces that, so the trap is what
    // makes the attribute honest. Real browser tab order — user-event only
    // approximates it under jsdom, which is why this assertion lives here.
    await page.keyboard.press('Tab');
    await expect(dialog.getByRole('button', { name: 'Download' })).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(dialog.getByRole('button', { name: 'Close' })).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(dialog.getByRole('button', { name: 'Download' })).toBeFocused();

    // …and focus comes back to the thumbnail that opened it.
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(expand).toBeFocused();
  });

  test('renders the overlay above the backdrop, controls in place', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(chatData);
    await page.goto('/en/dashboard/chat');

    await page.getByRole('button', { name: 'View image full screen' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    // The two-layer restructure (backdrop / pointer-transparent dialog) must
    // not have moved the controls out of the top-right corner, nor left the
    // image hidden behind the backdrop.
    const close = page.getByRole('button', { name: 'Close' });
    const image = dialog.getByRole('img');
    await expect(close).toBeVisible();
    await expect(image).toBeVisible();

    const viewport = page.viewportSize()!;
    const closeBox = (await close.boundingBox())!;
    expect(closeBox.y).toBeLessThan(viewport.height / 4);
    expect(closeBox.x).toBeGreaterThan(viewport.width / 2);

    // No manual screenshot here: the config already captures one
    // `only-on-failure`, so an unconditional one is a stray artifact on every
    // green run — and it asserts nothing.

    // Clicking the empty area still falls through to the backdrop and closes.
    await page.mouse.click(20, viewport.height - 20);
    await expect(dialog).toHaveCount(0);
  });
});
