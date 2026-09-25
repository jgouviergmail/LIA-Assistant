/**
 * An answer's own actions and the debug panel's width, in a real browser
 * (owner requests, 2026-09-24).
 *
 * Hermetic: the conversation, the connections and the debug switch are mocked;
 * everything else dies on the 501 catch-all. What only a laid-out page proves:
 *
 * 1. **Download is ONE click** — the « … » menu that hid it is gone — and the
 *    file is the answer, under a dated `lia-` name.
 * 2. **Share reaches a connection by the ordinary road**: the menu lists the
 *    accepted connections, and picking one PREFILLS the composer (nothing is
 *    sent — the relay goes through the assistant and its confirmation).
 * 3. **The debug panel widens INTO the conversation** by drag and by keyboard,
 *    and the conversation keeps the rest of the row.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';
import { scanPage } from '../a11y/scan';

const CONNECTION_ID = '11111111-2222-4333-8444-555555555555';

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

const ANSWER = {
  id: '00000000-0000-4000-8000-00000000a001',
  role: 'assistant',
  content: 'The quarterly figures are up by 12 %.',
  message_metadata: {},
  created_at: '2026-09-24T10:00:00Z',
  tokens_in: null,
  tokens_out: null,
  tokens_cache: null,
  cost_eur: null,
  google_api_requests: null,
  stt_provider: null,
};

function routes(options: { debugPanel?: boolean } = {}): MockRoute[] {
  return [
    CONFIG,
    { url: '**/api/v1/conversations/me/totals', json: {} },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
    {
      url: '**/api/v1/system-settings/debug-panel-status',
      json: { enabled: options.debugPanel ?? false, user_access_available: false },
    },
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: [ANSWER],
        conversation_id: '00000000-0000-4000-8000-0000000000ff',
        total_count: 1,
        has_more: false,
        next_cursor: null,
      },
    },
    {
      url: '**/api/v1/peers/connections',
      json: [
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
      ],
    },
  ];
}

test.describe("an answer's own actions", () => {
  test('Download is one click and saves the answer under a dated name', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(routes());
    await page.goto('/en/dashboard/chat');
    await waitForHydration(page, 'textarea');

    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Download as Markdown' }).click();
    const file = await download;

    expect(file.suggestedFilename()).toMatch(/^lia-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}\.md$/);
    // The « … » menu that used to hide it is gone.
    await expect(page.getByRole('button', { name: 'More actions' })).toHaveCount(0);
  });

  test('Share lists the connections, and picking one prefills the composer', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(routes());
    await page.goto('/en/dashboard/chat');
    await waitForHydration(page, 'textarea');

    await page.getByRole('button', { name: 'Share', exact: true }).click();
    await expect(page.getByText('Share with a connection')).toBeVisible();
    const scan = await scanPage(page, test.info(), 'answer share menu');
    expect(scan.blocking, `axe violations on the share menu:\n${scan.summary}`).toHaveLength(0);

    await page.getByRole('menuitem', { name: 'Claire Lefèvre' }).click();

    // Prefilled, never sent: the relay takes the assistant's road.
    await expect(page.locator('textarea')).toHaveValue(
      /^Relay this to Claire Lefèvre:\s+The quarterly figures are up by 12 %\./
    );
  });
});

/**
 * The widths of the row's two cards. The handle's parent is the panel's frame,
 * whose parent is the row; the conversation card is the row's first child
 * (measured on the production build: row, conversation, eyes widget, panel).
 */
async function rowWidths(handle: import('@playwright/test').Locator) {
  return handle.evaluate(el => {
    const frame = el.parentElement!;
    const conversation = frame.parentElement!.firstElementChild!;
    return {
      panel: Math.round(frame.getBoundingClientRect().width),
      conversation: Math.round(conversation.getBoundingClientRect().width),
    };
  });
}

test.describe('the debug panel width', () => {
  test.use({ viewport: { width: 1600, height: 900 } });

  test('widens into the conversation by drag and by keyboard', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(routes({ debugPanel: true }));
    await page.goto('/en/dashboard/chat');
    await waitForHydration(page, 'textarea');

    const handle = page.getByRole('separator', { name: 'Resize the debug panel' });
    await expect(handle).toBeVisible();
    const before = Number(await handle.getAttribute('aria-valuenow'));
    const widthsBefore = await rowWidths(handle);

    // Drag the handle 200 px to the left: the panel widens by as much.
    const box = (await handle.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 - 200, box.y + box.height / 2, { steps: 5 });
    await page.mouse.up();
    await expect(handle).toHaveAttribute('aria-valuenow', String(before + 200));
    // The conversation gives way by exactly what the panel took (polled: the
    // layout is read once the browser has laid the new width out).
    await expect
      .poll(() => rowWidths(handle))
      .toEqual({
        panel: widthsBefore.panel + 200,
        conversation: widthsBefore.conversation - 200,
      });

    // The keyboard does what the drag does, and Enter restores the default.
    await handle.focus();
    await page.keyboard.press('ArrowRight');
    await expect(handle).toHaveAttribute('aria-valuenow', String(before + 200 - 16));
    await page.keyboard.press('Enter');
    await expect(handle).toHaveAttribute('aria-valuenow', String(before));
  });
});
