/**
 * Sharing a generated image with a connection (ADR-316), in a real browser.
 *
 * Hermetic: the conversation, the image bytes, the connections and the share
 * endpoint are mocked; everything else dies on the 501 catch-all. Three claims
 * only a laid-out page proves:
 *
 * 1. **The sender's card offers the share, and the dialog's button is the only
 *    way to send.** The connections are read when the dialog opens (not by the
 *    card), a keyboard user picks one and sends; the oracle is what is ASKED —
 *    the image's attachment id and the trimmed comment.
 * 2. **The recipient's bubble shows the image as a card**, tinted as a peer's,
 *    with the reply and block actions of a relayed message, and the comment as
 *    text — never as the image or the link it tried to be.
 * 3. **At 320 px the dialog fits the screen**: nothing reaches past it.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';
import { scanPage } from '../a11y/scan';

const PNG_1X1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
  'base64'
);
const IMAGE_ID = '0b0e3c3a-6f1d-4c2e-9a51-3d2f1e0c9b8a';
const IMAGE_URL = `/api/v1/attachments/${IMAGE_ID}`;
const CONNECTION_ID = '11111111-2222-4333-8444-555555555555';
const FUTURE = '2099-01-01T00:00:00Z';

/** The instance offers connections: the shell's config, with the flag on. */
const CONFIG: MockRoute = {
  url: '**/api/v1/config',
  json: {
    sse: { heartbeat_interval_seconds: 30 },
    rate_limits: { enabled: false, per_minute: 60, burst: 10 },
    i18n: { supported_languages: ['en', 'fr', 'de', 'es', 'it', 'zh'], default_language: 'en' },
    features: {
      workboard_enabled: true,
      tool_approval_enabled: false,
      attachments_enabled: true,
      rag_spaces_enabled: true,
      rag_spaces_embedding_model: 'text-embedding-3-small',
      peers_enabled: true,
    },
    api_version: 'v1',
  },
};

function message(overrides: Record<string, unknown>) {
  return {
    id: '00000000-0000-4000-8000-00000000m001',
    role: 'assistant',
    content: 'Here is your lighthouse.',
    message_metadata: {
      generated_images: [{ url: IMAGE_URL, alt: 'a lighthouse at dusk', expires_at: FUTURE }],
    },
    created_at: '2026-09-24T10:00:00Z',
    tokens_in: null,
    tokens_out: null,
    tokens_cache: null,
    cost_eur: null,
    google_api_requests: null,
    stt_provider: null,
    ...overrides,
  };
}

function chatRoutes(messages: unknown[], asked: string[], posted: unknown[]): MockRoute[] {
  return [
    CONFIG,
    { url: '**/api/v1/conversations/me/totals', json: {} },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages,
        conversation_id: '00000000-0000-4000-8000-0000000000ff',
        total_count: messages.length,
        has_more: false,
        next_cursor: null,
      },
    },
    {
      url: `**${IMAGE_URL}`,
      handler: async route => {
        await route.fulfill({ status: 200, contentType: 'image/png', body: PNG_1X1 });
      },
    },
    {
      url: '**/api/v1/peers/connections',
      handler: async route => {
        asked.push('GET connections');
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: CONNECTION_ID,
              peer_id: '99999999-2222-4333-8444-555555555555',
              peer_display_name: 'Claire Lefèvre',
              peer_email_hint: 'c…@e….org',
              peer_email: null,
              status: 'accepted',
              direction: null,
              requested_at: '2026-09-01T10:00:00Z',
              responded_at: '2026-09-01T11:00:00Z',
              context_message: null,
              my_shares: [],
              their_shares: [],
            },
          ]),
        });
      },
    },
    {
      url: `**/api/v1/peers/connections/${CONNECTION_ID}/images`,
      method: 'POST',
      handler: async route => {
        posted.push(route.request().postDataJSON());
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'aaaaaaaa-2222-4333-8444-555555555555',
            recipient_display_name: 'Claire Lefèvre',
            delivered: true,
          }),
        });
      },
    },
  ];
}

test.describe('sharing a generated image with a connection', () => {
  test('the card opens the dialog, and the dialog sends what was chosen', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    const asked: string[] = [];
    const posted: unknown[] = [];
    await mockApi(chatRoutes([message({})], asked, posted));

    await page.goto('/en/dashboard/chat');
    const share = page.getByRole('button', { name: 'Share with a connection' });
    await waitForHydration(page, 'img[alt="a lighthouse at dusk"]');
    // The card itself asks nothing: the connections are read by the dialog.
    expect(asked).toEqual([]);

    await share.focus();
    await page.keyboard.press('Enter');
    const dialog = page.getByRole('dialog', { name: 'Share this image' });
    await expect(dialog).toBeVisible();
    await expect.poll(() => asked).toEqual(['GET connections']);

    const send = dialog.getByRole('button', { name: 'Share', exact: true });
    await expect(send).toBeDisabled();
    await dialog.getByRole('radio', { name: 'Claire Lefèvre' }).check();
    await dialog.getByRole('textbox').fill('  For your birthday!  ');
    await send.click();

    await expect
      .poll(() => posted)
      .toEqual([{ attachment_id: IMAGE_ID, comment: 'For your birthday!' }]);
    await expect(page.getByText('Image shared with Claire Lefèvre')).toBeVisible();
    await expect(dialog).toBeHidden();
  });

  test('the recipient sees a peer bubble with the card and the comment as text', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    const received = message({
      content:
        // What `markdown_literal` writes: references, never backslashes — the
        // chat's math step reads `\[x\]` as a LaTeX block (measured here).
        'Gérard Dupont shared an image with you.\n\n> Look !&#91;x&#93;(https://t.example/p.png)',
      message_metadata: {
        type: 'proactive_peer_image',
        target_id: 'aaaaaaaa-2222-4333-8444-555555555555',
        sender_id: '88888888-2222-4333-8444-555555555555',
        sender_name: 'Gérard Dupont',
        generated_images: [{ url: IMAGE_URL, alt: 'a lighthouse at dusk', expires_at: FUTURE }],
      },
    });
    await mockApi(chatRoutes([received], [], []));

    await page.goto('/en/dashboard/chat');
    await waitForHydration(page, 'img[alt="a lighthouse at dusk"]');

    await expect(page.getByText('Gérard Dupont shared an image with you.')).toBeVisible();
    // The comment tried to be an image: it reads as the words it is.
    await expect(page.getByText('Look ![x](https://t.example/p.png)')).toBeVisible();
    await expect(page.locator('img[src*="t.example"]')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Reply' })).toBeVisible();
    await expect(page.getByRole('button', { name: /Block/ })).toBeVisible();
  });

  test('at 320 px the dialog stays on the screen', async ({ page, authenticate, mockApi }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await authenticate();
    await mockApi(chatRoutes([message({})], [], []));

    await page.goto('/en/dashboard/chat');
    await waitForHydration(page, 'img[alt="a lighthouse at dusk"]');
    await page.getByRole('button', { name: 'Share with a connection' }).click();
    const dialog = page.getByRole('dialog', { name: 'Share this image' });
    await expect(dialog.getByRole('radio', { name: 'Claire Lefèvre' })).toBeVisible();

    const box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(320);
    const scrolls = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(scrolls).toBe(false);
  });

  test('the share dialog scans clean (axe WCAG A/AA)', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await authenticate();
    await mockApi(chatRoutes([message({})], [], []));

    await page.goto('/en/dashboard/chat');
    await waitForHydration(page, 'img[alt="a lighthouse at dusk"]');
    await page.getByRole('button', { name: 'Share with a connection' }).click();
    const dialog = page.getByRole('dialog', { name: 'Share this image' });
    await dialog.getByRole('radio', { name: 'Claire Lefèvre' }).check();

    const { blocking, summary } = await scanPage(page, testInfo, 'chat share dialog');
    expect(
      blocking,
      `axe violations on the share dialog:
${summary}`
    ).toHaveLength(0);
  });
});
