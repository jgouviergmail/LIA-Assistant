/**
 * Chat journey — the thread follows the server without a reload (ADR-320).
 *
 * Hermetic: the history is a mocked page the test swaps, and the person's
 * real-time channel (`/notifications/stream`) is a mocked SSE whose handler
 * awaits a test-controlled gate, then says « the conversation changed » ONCE —
 * exactly what the API publishes after committing a message archived
 * elsewhere (another tab, Telegram, a routine, a reminder).
 *
 * Why a browser test: « nothing on screen remounts » and « the reader is not
 * moved » are properties of a real DOM and a real layout. A bubble already on
 * screen carries a mark set by the test; a remount would create a fresh node
 * without it. A flag on `window` proves the page itself was never reloaded.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';

const CONVERSATION_ID = '00000000-0000-4000-8000-00000000c320';

const APP_CONFIG = {
  sse: { heartbeat_interval_seconds: 15 },
  rate_limits: { enabled: false, per_minute: 60, burst: 10 },
  i18n: { supported_languages: ['fr', 'en'], default_language: 'fr' },
  features: {
    tool_approval_enabled: true,
    attachments_enabled: true,
    rag_spaces_enabled: false,
    rag_spaces_embedding_model: '',
  },
  api_version: 'v1',
};

const ARRIVAL = 'Rappel : arrose les plantes du balcon';

function historyRow(index: number, content?: string) {
  return {
    id: '00000000-0000-4000-8000-' + String(index).padStart(12, '0'),
    conversation_id: CONVERSATION_ID,
    role: index % 2 === 1 ? 'user' : 'assistant',
    content:
      content ??
      'Message ' +
        index +
        '. Une ligne de contenu suffisamment longue pour occuper plusieurs ' +
        'lignes a l ecran et forcer la liste a deborder largement du viewport.',
    message_metadata: null,
    created_at: new Date(Date.UTC(2026, 8, 25, 9, 0, index)).toISOString(),
    tokens_in: null,
    tokens_out: null,
    tokens_cache: null,
    cost_eur: null,
    google_api_requests: null,
    stt_provider: null,
    stt_audio_duration_seconds: null,
  };
}

/** The newest page, newest first (keyset order); `arrived` adds the reminder. */
function historyPage(arrived: boolean) {
  const rows = Array.from({ length: 40 }, (_, i) => historyRow(i + 1));
  if (arrived) rows.push({ ...historyRow(42, ARRIVAL), role: 'assistant' });
  return {
    messages: rows.reverse(),
    conversation_id: CONVERSATION_ID,
    total_count: rows.length,
    has_more: false,
    next_cursor: null,
  };
}

const NL = String.fromCharCode(10);

/** The page the history route serves, and the gate of the one signal. */
function syncRoutes(state: { arrived: boolean }, gate: Promise<void>): MockRoute[] {
  let signalled = false;
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    {
      url: '**/api/v1/conversations/me',
      json: {
        id: CONVERSATION_ID,
        user_id: '00000000-0000-4000-8000-000000000001',
        title: 'E2E sync',
        message_count: 40,
        total_tokens: 0,
        created_at: '2026-09-25T09:00:00Z',
        updated_at: '2026-09-25T10:00:00Z',
      },
    },
    {
      url: '**/api/v1/conversations/me/messages*',
      handler: async route => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(historyPage(state.arrived)),
        });
      },
    },
    { url: '**/api/v1/conversations/me/totals', json: {} },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
    {
      url: '**/api/v1/notifications/stream',
      handler: async route => {
        if (signalled) {
          // A reconnection after the one signal: an idle stream.
          await route.fulfill({
            status: 200,
            contentType: 'text/event-stream',
            body: ': idle' + NL + NL,
          });
          return;
        }
        await gate;
        signalled = true;
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body:
            'event: notification' +
            NL +
            'data: {"type":"conversation_updated","conversation_id":"' +
            CONVERSATION_ID +
            '"}' +
            NL +
            NL,
        });
      },
    },
  ];
}

/** Geometry of the box that actually scrolls, read from the live layout. */
async function distanceToBottom(page: import('@playwright/test').Page): Promise<number> {
  return page.evaluate(() => {
    const boxes = Array.from(document.querySelectorAll<HTMLElement>('.overflow-y-auto'));
    const el = boxes.find(b => b.scrollHeight > b.clientHeight) ?? boxes[0];
    return el ? Math.round(el.scrollHeight - el.clientHeight - el.scrollTop) : -1;
  });
}

test.describe('chat conversation sync (ADR-320)', () => {
  test('a message archived elsewhere joins the thread — no reload, no remount', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    let release!: () => void;
    const gate = new Promise<void>(resolve => {
      release = resolve;
    });
    const state = { arrived: false };
    await authenticate();
    await mockApi(syncRoutes(state, gate));

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    const onScreen = page.getByText('Message 40', { exact: false });
    await expect(onScreen).toBeAttached();

    await onScreen.evaluate(node => node.setAttribute('data-e2e-mark', 'kept'));
    await page.evaluate(() => {
      (window as unknown as { __notReloaded: boolean }).__notReloaded = true;
    });

    // The reminder is archived elsewhere, then announced.
    state.arrived = true;
    release();

    await expect(page.getByText(ARRIVAL)).toBeAttached();
    // The bubble that was on screen is the SAME node: nothing remounted.
    await expect(page.locator('[data-e2e-mark="kept"]')).toHaveCount(1);
    expect(
      await page.evaluate(
        () => (window as unknown as { __notReloaded?: boolean }).__notReloaded === true
      )
    ).toBe(true);
    // Merged once: the reminder is not shown twice.
    await expect(page.getByText(ARRIVAL)).toHaveCount(1);
  });

  test('a reader who scrolled up is not moved; the arrival is counted on the button', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    let release!: () => void;
    const gate = new Promise<void>(resolve => {
      release = resolve;
    });
    const state = { arrived: false };
    await authenticate();
    await mockApi(syncRoutes(state, gate));

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await expect(page.getByText('Message 40', { exact: false })).toBeAttached();
    // Unavoidable sleep: the initial-pin window is an INTERNAL timer of
    // ChatMessageList with no observable DOM state (see chat-scroll-follow).
    await page.waitForTimeout(3000);

    await page.mouse.move(640, 400);
    await page.mouse.wheel(0, -3000);
    await expect.poll(() => distanceToBottom(page), { timeout: 3000 }).toBeGreaterThan(500);

    state.arrived = true;
    release();
    await expect(page.getByText(ARRIVAL)).toBeAttached();
    await page.evaluate(
      () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))
    );

    // The reader stays where they were (the existing reading invariant, Q5)…
    expect(await distanceToBottom(page)).toBeGreaterThan(500);
    // …and the existing indicator says something arrived.
    const button = page.getByRole('button', { name: 'Revenir en bas de la conversation' });
    await expect(button).toBeVisible();
    await expect(button).toContainText('1 nouvelle réponse');
  });
});
