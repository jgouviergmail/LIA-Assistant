/**
 * Chat — rich-HTML display mode rendering (ADR-177).
 *
 * Hermetic: empty mocked history + mocked SSE streaming a full `lia-response`
 * document in small chunks (several land mid-tag on purpose). Guards, in a
 * real engine (jsdom performs no layout):
 * - the components render as DOM, never as raw tag text;
 * - the collapsible toggles from the keyboard (native <summary> semantics);
 * - nothing overflows the viewport horizontally, desktop and 390px mobile.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const NL = String.fromCharCode(10);

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c177',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E html mode',
  message_count: 0,
  total_tokens: 0,
  created_at: '2026-07-29T09:00:00Z',
  updated_at: '2026-07-29T09:00:00Z',
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

const EMPTY_HISTORY = {
  messages: [],
  conversation_id: CONVERSATION.id,
  total_count: 0,
  has_more: false,
  next_cursor: null,
};

const HTML_ANSWER = [
  '<div class="lia-response">',
  '<h2>Synthèse de la journée</h2>',
  '<div class="lia-callout lia-callout-success"><p class="lia-callout__title">Tout est prêt</p>' +
    '<p>Trois créneaux confirmés.</p></div>',
  '<dl class="lia-kv"><dt>Date</dt><dd><strong>12 août</strong></dd>' +
    '<dt>Lieu</dt><dd>Paris</dd></dl>',
  '<div class="lia-stats"><div class="lia-stat"><span class="lia-stat__value">12</span>' +
    '<span class="lia-stat__label">rendez-vous</span></div>' +
    '<div class="lia-stat"><span class="lia-stat__value">3</span>' +
    '<span class="lia-stat__label">urgents</span></div></div>',
  '<table><caption>Comparatif</caption><thead><tr><th>Option</th><th>Durée</th></tr></thead>' +
    '<tbody><tr><td>A</td><td>1 h</td></tr><tr><td>B</td><td>2 h</td></tr></tbody></table>',
  '<details class="lia-collapsible"><summary>Voir le détail</summary>' +
    '<p>Contenu replié.</p></details>',
  '</div>',
].join('');

/** Stream the document in 24-char chunks — several land mid-tag on purpose. */
function sseAnswer(): string {
  const chunks: string[] = [];
  for (let i = 0; i < HTML_ANSWER.length; i += 24) {
    const piece = HTML_ANSWER.slice(i, i + 24).replace(/"/g, String.fromCharCode(92) + '"');
    chunks.push('data: {"type":"token","content":"' + piece + '"}' + NL + NL);
  }
  return chunks.join('') + 'data: {"type":"done","content":"","metadata":null}' + NL + NL;
}

function baseRoutes(): MockRoute[] {
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    { url: '**/api/v1/conversations/me', json: CONVERSATION },
    { url: '**/api/v1/conversations/me/messages*', json: EMPTY_HISTORY },
    { url: '**/api/v1/conversations/me/totals', json: {} },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async route => {
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: sseAnswer(),
        });
      },
    },
  ];
}

async function sendAndAwaitAnswer(page: import('@playwright/test').Page): Promise<void> {
  await page.locator('textarea').fill('Synthèse de ma journée en HTML');
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('heading', { name: 'Synthèse de la journée', level: 2 })
  ).toBeVisible({ timeout: 15_000 });
}

test.describe('rich HTML display mode (ADR-177)', () => {
  test('components render as DOM, collapsible is keyboard-operable, no overflow', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(baseRoutes());

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await awaitStyledPage(page, 'chat-html-mode desktop');

    await sendAndAwaitAnswer(page);

    // Raw tag source must never be readable anywhere in the thread — the
    // regression this whole mode guards against.
    expect(await page.locator('body').textContent()).not.toContain('<h2>');

    await expect(page.locator('.lia-callout-success .lia-callout__title')).toHaveText(
      'Tout est prêt'
    );
    const kv = page.locator('dl.lia-kv');
    await expect(kv.locator('dt')).toHaveCount(2);
    await expect(page.locator('.lia-stat__value').first()).toHaveText('12');
    await expect(page.locator('table caption')).toHaveText('Comparatif');

    // Keyboard: <summary> is natively focusable; Enter toggles the details.
    const details = page.locator('details.lia-collapsible');
    await expect(details).not.toHaveAttribute('open', '');
    await details.locator('summary').focus();
    await page.keyboard.press('Enter');
    await expect(details).toHaveAttribute('open', '');
    await expect(page.getByText('Contenu replié.')).toBeVisible();

    await expectNoOverflow(page, 'html-answer desktop');
  });

  test('mobile 390px: rich components stack without horizontal overflow', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate();
    await mockApi(baseRoutes());

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await awaitStyledPage(page, 'chat-html-mode mobile');

    await sendAndAwaitAnswer(page);

    await expect(page.locator('.lia-stat__value').first()).toBeVisible();
    await expectNoOverflow(page, 'html-answer mobile');
  });
});
