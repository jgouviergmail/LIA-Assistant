/**
 * Chat journey — the reading invariant + floating return button (UXR Lot 3, A3).
 *
 * Hermetic: history is a single mocked page; the answer stream is a mocked SSE
 * whose route handler awaits a test-controlled GATE promise, so "tokens land
 * while the reader is away" is deterministic, not a race.
 *
 * Why a browser test: jsdom performs no layout (see the pinned rationale in
 * ChatMessageList.test.tsx) — only a real engine can show a viewport being
 * yanked. Discriminance: under the pre-Lot-3 behavior the auto-scroll effect
 * ran `scrollIntoView(bottom)` on EVERY token, so the `distanceToBottom > 500`
 * assertion below fails by construction against that code.
 *
 * Preserved behavior guarded too: an OWN send from a scrolled position still
 * jumps to the sent message.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c004',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E scroll follow',
  message_count: 40,
  total_tokens: 0,
  created_at: '2026-07-18T09:00:00Z',
  updated_at: '2026-07-18T10:00:00Z',
};

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

/** Single history page (has_more: false → no pagination interplay). */
function historyPage() {
  return {
    messages: Array.from({ length: 40 }, (_, i) => {
      const index = 40 - i; // newest first (keyset order)
      return {
        id: '00000000-0000-4000-8000-' + String(index).padStart(12, '0'),
        conversation_id: CONVERSATION.id,
        role: index % 2 === 1 ? 'user' : 'assistant',
        content:
          'Message ' +
          index +
          '. Une ligne de contenu suffisamment longue pour occuper plusieurs ' +
          'lignes a l ecran et forcer la liste a deborder largement du viewport.',
        created_at: new Date(Date.UTC(2026, 6, 18, 9, 0, index)).toISOString(),
        tokens_in: null,
        tokens_out: null,
        tokens_cache: null,
        cost_eur: null,
        google_api_requests: null,
        stt_provider: null,
        stt_audio_duration_seconds: null,
      };
    }),
    conversation_id: CONVERSATION.id,
    total_count: 40,
    has_more: false,
    next_cursor: null,
  };
}

const NL = String.fromCharCode(10);

/** SSE body: 20 token chunks then done — one streamed assistant answer. */
function sseAnswer(): string {
  const token = 'data: {"type":"token","content":"Voici la suite de la reponse. "}' + NL + NL;
  return token.repeat(20) + 'data: {"type":"done","content":"","metadata":null}' + NL + NL;
}

/**
 * Base routes; the stream handler AWAITS `gate` before delivering the SSE
 * body, so the test controls exactly when tokens land.
 */
function baseRoutes(gate: Promise<void>): MockRoute[] {
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    { url: '**/api/v1/conversations/me', json: CONVERSATION },
    { url: '**/api/v1/conversations/me/messages*', json: historyPage() },
    { url: '**/api/v1/conversations/me/totals', json: {} },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async route => {
        await gate;
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: sseAnswer(),
        });
      },
    },
  ];
}

/** Geometry of the box that actually scrolls, read from the live layout. */
async function geometry(page: import('@playwright/test').Page) {
  return page.evaluate(() => {
    const boxes = Array.from(document.querySelectorAll<HTMLElement>('.overflow-y-auto'));
    const el = boxes.find(b => b.scrollHeight > b.clientHeight) ?? boxes[0];
    return {
      distanceToBottom: el ? Math.round(el.scrollHeight - el.clientHeight - el.scrollTop) : -1,
    };
  });
}

test.describe('chat scroll follow invariant', () => {
  test('a streaming answer never yanks the reader who scrolled away', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    let release!: () => void;
    const gate = new Promise<void>(resolve => {
      release = resolve;
    });
    await authenticate();
    await mockApi(baseRoutes(gate));

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await expect(page.getByText('Message 40', { exact: false })).toBeAttached();
    // Unavoidable sleep: the initial-pin window is an INTERNAL timer of
    // ChatMessageList (INITIAL_PIN_WINDOW_MS) with no observable DOM state;
    // 3000ms > the window by design. Every other wait below polls state.
    await page.waitForTimeout(3000);

    // Send at the bottom — the question appears, the stream stays gated.
    await page.locator('textarea').fill('Ma question pendant la lecture');
    await page.keyboard.press('Enter');
    await expect(page.getByText('Ma question pendant la lecture')).toBeAttached();

    // The reader goes back up to re-read the thread.
    await page.mouse.move(640, 400);
    await page.mouse.wheel(0, -3000);
    await expect
      .poll(async () => (await geometry(page)).distanceToBottom, { timeout: 3000 })
      .toBeGreaterThan(500);

    // Tokens land NOW, while the reader is away.
    release();
    await expect(page.getByText('Voici la suite de la reponse.', { exact: false })).toBeAttached();
    // THE invariant: the viewport was not yanked. Two paints AFTER the tokens
    // landed (double rAF) guarantee any wrongful follow would have happened.
    await page.evaluate(
      () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))
    );
    expect((await geometry(page)).distanceToBottom).toBeGreaterThan(500);

    // The floating button surfaces the off-screen response (badge inside the
    // button — the sr-only live region carries the same text on purpose).
    const button = page.getByRole('button', { name: 'Revenir en bas de la conversation' });
    await expect(button).toBeVisible();
    await expect(button).toContainText('1 nouvelle réponse');

    // One tap → back to the bottom, button (and badge) gone.
    await button.click();
    await expect
      .poll(async () => (await geometry(page)).distanceToBottom, { timeout: 3000 })
      .toBeLessThanOrEqual(8);
    await expect(button).toHaveCount(0);
  });

  test('sending from a scrolled position still jumps to your message', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(baseRoutes(Promise.resolve())); // stream answers immediately

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await expect(page.getByText('Message 40', { exact: false })).toBeAttached();
    // Same unavoidable pin-window sleep as above.
    await page.waitForTimeout(3000);

    await page.mouse.move(640, 400);
    await page.mouse.wheel(0, -3000);
    await expect
      .poll(async () => (await geometry(page)).distanceToBottom, { timeout: 3000 })
      .toBeGreaterThan(500);

    // An OWN send must always show the sent message (preserved behavior).
    await page.locator('textarea').fill('Nouvelle question depuis le passe');
    await page.keyboard.press('Enter');
    await expect(page.getByText('Nouvelle question depuis le passe')).toBeAttached();
    await expect
      .poll(async () => (await geometry(page)).distanceToBottom, { timeout: 3000 })
      .toBeLessThanOrEqual(50);
  });
});
