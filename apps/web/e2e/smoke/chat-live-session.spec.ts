/**
 * Chat journey — the live mode (ADR-299), hermetic.
 *
 * The provider is played by `page.routeWebSocket`: it acknowledges the setup,
 * emits the person's transcript, asks `send_to_lia`, and receives the tool
 * response — in BINARY frames, as the real provider sends them (measured on
 * Docker dev 2026-09-18: a text-frame fake let a text-only reader pass while
 * the real session stayed on « Connecting… » for ever). The API is mocked
 * (connector, config, start, turns, end, chat stream); the microphone is
 * Chromium's fake device. Proves in a real browser tree that:
 *  - the Live button appears with the capability and an active connector;
 *  - the banner is a named region with its controls reachable;
 *  - a delegated request lands in the thread as a user bubble and its answer
 *    streams, stamped with the session;
 *  - the tool response carries the flattened answer back to the voice;
 *  - End posts the outcome and the closing card names LIA's cost.
 *
 * A second journey plays a DIRECT session (ADR-300 wave 4): the third entry
 * of the voice menu, the start posted with its mode, a function call the
 * provider makes answered through the API's tool door and nothing in the
 * thread, the banner naming the session and the lookup.
 *
 * No backend, LLM, or paid provider is contacted.
 */
import { test, expect, type MockRoute } from '../fixtures';

test.use({
  launchOptions: {
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
  },
});

const SESSION = 'a'.repeat(32);
const CONVERSATION_ID = '00000000-0000-4000-8000-00000000c001';

const APP_CONFIG = {
  sse: { heartbeat_interval_seconds: 15 },
  rate_limits: { enabled: false, per_minute: 60, burst: 10 },
  i18n: { supported_languages: ['fr', 'en'], default_language: 'fr' },
  features: {
    tool_approval_enabled: true,
    attachments_enabled: false,
    rag_spaces_enabled: false,
    rag_spaces_embedding_model: '',
    live_enabled: true,
  },
  api_version: 'v1',
};

const START = {
  session_id: SESSION,
  provider: 'gemini',
  model: 'gemini-x-live',
  mode: 'delegated',
  run_id: `live_session_${SESSION}`,
  credential: 'tok',
  credential_expires_at: '2030-01-01T00:00:00Z',
  connect_deadline_at: '2030-01-01T00:00:00Z',
  connection: 'token',
  expires_at: '2030-01-01T00:00:00Z',
  session_max_minutes: 30,
  idle_timeout_seconds: 300,
  setup: { model: 'models/gemini-x-live' },
  preferences: {
    interruptions: true,
    end_of_speech: 'normal',
    result_delivery: 'interrupt',
  },
  capabilities: {
    async_delegation: true,
    delivery_scheduling: true,
    reports_idle: false,
    cancels_on_interruption: true,
    configurable_vad: true,
    resumes: true,
    thinking: false,
    direct_tools: true,
    portal_voice: false,
  },
  delegation_tool_name: 'send_to_lia',
  delegation_timeout_seconds: 90,
  delegation_result_max_tokens: 600,
  turn_text_max_chars: 4000,
  rates: {
    pricing_unit: 'per_1m_tokens',
    input_unit_price: 0.75,
    output_unit_price: 4.5,
    audio_input_unit_price: 3,
    audio_output_unit_price: 12,
    usd_eur_rate: 0.9,
  },
  session_budget_eur: null,
};

const LIVE_CONFIG = {
  session_max_minutes: 30,
  connect_window_seconds: 60,
  idle_timeout_seconds: 300,
  hidden_grace_seconds: 20,
  delegation_timeout_seconds: 90,
  delegation_result_max_tokens: 600,
  delegation_tool_name: 'send_to_lia',
  turn_text_max_chars: 4000,
  delegation_lines: { timed_out: 'T', result_cut: 'C', superseded: 'X', empty_request: 'E' },
  direct_lines: { lookup_failed: 'F' },
  session_max_bounds: { min: 1, max: 240 },
  idle_timeout_bounds: { min: 5, max: 3600 },
  unlimited_value: 0,
  tone_lines: { warm: 'LIA said this warmly.' },
};

function sseAnswer(text: string): string {
  // The answering model declared its register (ADR-253): the voice is handed its note.
  const done = {
    type: 'done',
    content: '',
    metadata: { expressivity: { register: 'warm', intensity: 0.6, accent: 'none' } },
  };
  return (
    `data: ${JSON.stringify({ type: 'token', content: text, metadata: null })}\n\n` +
    `data: ${JSON.stringify(done)}\n\n`
  );
}

function routes(
  chatBodies: Array<Record<string, unknown>>,
  endBodies: unknown[],
  startBodies: unknown[] = [],
  toolBodies: unknown[] = [],
  turnBodies: unknown[] = [],
  endRelay: string | null = null
): MockRoute[] {
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    {
      url: '**/api/v1/live/connectors',
      json: {
        connectors: [
          {
            provider: 'gemini',
            connector_type: 'gemini_live',
            status: 'active',
            settings: {
              model: 'gemini-x-live',
              voice: 'Kore',
              thinking_level: null,
              idle_timeout_seconds: 300,
              session_max_minutes: 30,
            },
            model_settings: {},
            functionally_verified: true,
            capabilities: START.capabilities,
            active: true,
          },
        ],
        active_provider: 'gemini',
      },
    },
    { url: '**/api/v1/live/config', json: LIVE_CONFIG },
    {
      url: '**/api/v1/live/sessions',
      method: 'POST',
      handler: async route => {
        const body = (route.request().postDataJSON() ?? {}) as { mode?: string };
        startBodies.push(body);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ...START, mode: body.mode ?? 'delegated' }),
        });
      },
    },
    {
      url: `**/api/v1/live/sessions/${SESSION}/tools`,
      method: 'POST',
      handler: async route => {
        toolBodies.push(route.request().postDataJSON());
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            text: 'Deux rendez-vous demain : le dentiste à neuf heures.',
            ok: true,
          }),
        });
      },
    },
    {
      url: `**/api/v1/live/sessions/${SESSION}/turns`,
      method: 'POST',
      handler: async route => {
        turnBodies.push(route.request().postDataJSON());
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ user_message_id: null, assistant_message_id: null }),
        });
      },
    },
    {
      url: `**/api/v1/live/sessions/${SESSION}/end`,
      method: 'POST',
      handler: async route => {
        endBodies.push(route.request().postDataJSON());
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            summary_message_id: 'sum1',
            duration_seconds: 65,
            delegations: 1,
            voice_turns: 0,
            extensions: 0,
            usage: {
              tokens_in: 10,
              tokens_out: 5,
              tokens_cache: 0,
              cost_eur: 0.0012,
              google_api_requests: 0,
            },
            relay: endRelay,
          }),
        });
      },
    },
    {
      url: '**/api/v1/conversations/me',
      json: {
        id: CONVERSATION_ID,
        user_id: '00000000-0000-4000-8000-000000000001',
        title: 'Live',
        message_count: 0,
        total_tokens: 0,
        created_at: '2026-09-18T09:00:00Z',
        updated_at: '2026-09-18T09:00:00Z',
      },
    },
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: [],
        conversation_id: CONVERSATION_ID,
        total_count: 0,
        has_more: false,
        next_cursor: null,
      },
    },
    { url: '**/api/v1/conversations/me/totals', json: {} },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async route => {
        chatBodies.push((route.request().postDataJSON() ?? {}) as Record<string, unknown>);
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: sseAnswer('Deux réunions demain.'),
        });
      },
    },
  ];
}

test.describe('chat live session', () => {
  test('starts, delegates a spoken request, answers the voice, ends with the card', async ({
    page,
    context,
    authenticate,
    mockApi,
  }) => {
    await context.grantPermissions(['microphone']);
    await authenticate();
    const chatBodies: Array<Record<string, unknown>> = [];
    const endBodies: unknown[] = [];
    await mockApi(routes(chatBodies, endBodies));

    const toolResponses: Array<Record<string, unknown>> = [];
    await page.routeWebSocket(/generativelanguage\.googleapis\.com/, ws => {
      // A Buffer is sent as a BINARY frame — the provider's own shape.
      const frame = (payload: unknown) => ws.send(Buffer.from(JSON.stringify(payload)));
      ws.onMessage(message => {
        const received = JSON.parse(String(message)) as Record<string, unknown>;
        if (received.setup) {
          frame({ setupComplete: {} });
          frame({ serverContent: { inputTranscription: { text: 'quoi demain ?' } } });
          frame({
            toolCall: {
              functionCalls: [
                { id: 'c1', name: 'send_to_lia', args: { request: 'Quoi demain ?' } },
              ],
            },
          });
        }
        if (received.toolResponse) {
          toolResponses.push(received.toolResponse as Record<string, unknown>);
          // The model turn's usage, as measured on a real session (ADR-300 wave 3):
          // the banner's meter counts it on the person's key.
          frame({
            usageMetadata: {
              promptTokenCount: 1227,
              responseTokenCount: 68,
              totalTokenCount: 1295,
              promptTokensDetails: [
                { modality: 'TEXT', tokenCount: 974 },
                { modality: 'AUDIO', tokenCount: 198 },
              ],
              responseTokensDetails: [{ modality: 'AUDIO', tokenCount: 48 }],
              thoughtsTokenCount: 115,
            },
          });
        }
      });
    });

    await page.goto('/fr/dashboard/chat');
    // Wave 2 (A1): the entry is the header's voice menu, one icon for the two voices.
    const voiceMenu = page.getByRole('button', { name: 'Voix et session live' });
    await expect(voiceMenu).toBeVisible();
    await voiceMenu.click();
    await page.getByRole('menuitem', { name: 'Session Live (Gemini)' }).click();

    const banner = page.getByRole('region', { name: 'Session live' });
    await expect(banner).toBeVisible();
    await expect(banner.getByRole('button', { name: 'Terminer la session live' })).toBeVisible();

    // The delegated request: a user bubble with the request, the answer streams.
    await expect(page.getByText('Quoi demain ?').first()).toBeVisible();
    await expect(page.getByText('Deux réunions demain.').first()).toBeVisible();
    await expect.poll(() => chatBodies.length).toBe(1);
    expect(chatBodies[0]).toMatchObject({
      message: 'Quoi demain ?',
      live_session_id: SESSION,
      spoken_text: 'quoi demain ?',
    });

    // The voice is handed the flattened answer.
    await expect.poll(() => toolResponses.length).toBe(1);
    expect(JSON.stringify(toolResponses[0])).toContain('Deux réunions demain.');
    expect(JSON.stringify(toolResponses[0])).toContain('"id":"c1"');
    // ... with the delivery note of the register the answer wore, as its own field.
    expect(JSON.stringify(toolResponses[0])).toContain('"tone":"LIA said this warmly."');

    // The composer is closed while the session runs and says why.
    await expect(
      page.getByPlaceholder('La session live est en cours', { exact: false })
    ).toBeVisible();

    // The meter, in the chat's vocabulary: the provider's report priced by the
    // declared tariff, indicative (ADR-300 wave 3).
    const meter = banner.getByTestId('live-meter');
    await expect(meter).toContainText('1 227 IN');
    await expect(meter).toContainText('183 OUT');
    await expect(meter).toContainText('0,0023 €');
    await expect(meter).toContainText('contexte 1 295');

    await banner.getByRole('button', { name: 'Terminer la session live' }).click();
    await expect(banner).toHaveCount(0);
    await expect.poll(() => endBodies.length).toBe(1);
    expect(endBodies[0]).toEqual({
      outcome: 'ended',
      detail: null,
      provider_conversation_id: null,
    });
    const card = page.getByTestId('live-session-summary');
    await expect(card).toBeVisible();
    await expect(card).toContainText('terminée par toi');
    await expect(card).toContainText('0,0012 €');
  });

  test('a DIRECT session answers the voice through the tool door and never the chat', async ({
    page,
    context,
    authenticate,
    mockApi,
  }) => {
    await context.grantPermissions(['microphone']);
    await authenticate();
    const chatBodies: Array<Record<string, unknown>> = [];
    const endBodies: unknown[] = [];
    const startBodies: unknown[] = [];
    const toolBodies: unknown[] = [];
    const turnBodies: unknown[] = [];
    await mockApi(routes(chatBodies, endBodies, startBodies, toolBodies, turnBodies, 'scheduled'));

    const toolResponses: Array<Record<string, unknown>> = [];
    await page.routeWebSocket(/generativelanguage\.googleapis\.com/, ws => {
      const frame = (payload: unknown) => ws.send(Buffer.from(JSON.stringify(payload)));
      ws.onMessage(message => {
        const received = JSON.parse(String(message)) as Record<string, unknown>;
        if (received.setup) {
          frame({ setupComplete: {} });
          frame({ serverContent: { inputTranscription: { text: 'quoi demain ?' } } });
          // The model calls LIA's own tool, declared on the session's setup.
          frame({
            toolCall: {
              functionCalls: [{ id: 'c1', name: 'get_events_tool', args: { query: 'demain' } }],
            },
          });
        }
        if (received.toolResponse) {
          toolResponses.push(received.toolResponse as Record<string, unknown>);
          frame({ serverContent: { outputTranscription: { text: 'Deux rendez-vous demain.' } } });
          frame({ serverContent: { turnComplete: true } });
        }
      });
    });

    await page.goto('/fr/dashboard/chat');
    await page.getByRole('button', { name: 'Voix et session live' }).click();
    // The third entry, after the spoken replies and the live session.
    const items = page.getByRole('menuitem');
    await expect(items).toHaveCount(2);
    await expect(items.nth(0)).toHaveText(/Session Live \(Gemini\)/);
    await expect(items.nth(1)).toHaveText(/Session Live directe \(Gemini\)/);
    await items.nth(1).click();

    const banner = page.getByRole('region', { name: 'Session live' });
    await expect(banner).toBeVisible();
    await expect(banner.getByRole('status')).toContainText('Session directe');
    // The notice (ADR-301): LIA reads for the person and acts on nothing
    // while they talk; at the end their words are relayed to the chat.
    await expect(banner.getByRole('note')).toContainText(
      'relayé dans ta conversation comme un message de toi'
    );
    await expect.poll(() => startBodies.length).toBe(1);
    expect(startBodies[0]).toEqual({ mode: 'direct' });

    // The lookup went through the API's tool door, its text back to the voice on the same id.
    await expect.poll(() => toolBodies.length).toBe(1);
    expect(toolBodies[0]).toEqual({ name: 'get_events_tool', arguments: { query: 'demain' } });
    await expect.poll(() => toolResponses.length).toBe(1);
    expect(JSON.stringify(toolResponses[0])).toContain('le dentiste à neuf heures');
    expect(JSON.stringify(toolResponses[0])).toContain('"id":"c1"');
    expect(JSON.stringify(toolResponses[0])).toContain('"name":"get_events_tool"');
    // Nothing reached the chat: no delegated turn, no bubble of the request.
    // The exchange lives in the banner, and is handed to the record through
    // the turns door (ADR-301) — which answers no row id, so no bubble either.
    expect(chatBodies).toHaveLength(0);
    await expect(page.getByText('Quoi demain ?')).toHaveCount(0);
    await expect(banner.getByText('Deux rendez-vous demain.')).toBeVisible();
    await expect.poll(() => turnBodies.length).toBe(1);
    expect(turnBodies[0]).toMatchObject({
      user_text: 'quoi demain ?',
      assistant_text: 'Deux rendez-vous demain.',
    });
    // Stop is never offered: there is no chat turn to stop.
    await expect(
      banner.getByRole('button', { name: 'Arrêter LIA et terminer la session' })
    ).toHaveCount(0);

    await banner.getByRole('button', { name: 'Terminer la session live' }).click();
    await expect(banner).toHaveCount(0);
    await expect.poll(() => endBodies.length).toBe(1);
    expect(endBodies[0]).toEqual({
      outcome: 'ended',
      detail: null,
      provider_conversation_id: null,
    });
    // The card says what became of the words (ADR-301): relayed to the chat
    // as the person's own turn — the fate the end answered.
    const card = page.getByTestId('live-session-summary');
    await expect(card).toBeVisible();
    await expect(card.getByTestId('live-session-relay')).toContainText(
      'Tes mots sont en cours de relais dans la conversation'
    );
  });
});
