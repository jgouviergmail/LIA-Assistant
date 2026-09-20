/**
 * Chat journey — the live mode on ElevenLabs Agents (ADR-300 wave 4), hermetic.
 *
 * The provider is played by `page.routeWebSocket` on the signed URL the API
 * minted: it answers the initiation with the conversation's metadata (a
 * 24 kHz agent), emits the person's transcript, asks `send_to_lia` as a
 * CLIENT tool call, receives the `client_tool_result`, and speaks its whole
 * reply as one `agent_response`. The API is mocked (an ElevenLabs connector
 * whose « model » is an agent with a portal voice, config, start with the
 * signed URL as credential, turns, end, chat stream); the microphone is
 * Chromium's fake device. Proves in a real browser tree that:
 *  - the session opens on the signed URL with the `convai` subprotocol and
 *    the initiation frame the API rendered goes out first;
 *  - a client tool call is a delegation: the request lands in the thread,
 *    its answer streams and goes back as a `client_tool_result`;
 *  - the agent's reply is a caption, and End posts the outcome.
 *
 * No backend, LLM, or paid provider is contacted.
 */
import { test, expect, type MockRoute } from '../fixtures';

test.use({
  launchOptions: {
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
  },
});

const SESSION = 'c'.repeat(32);
const CONVERSATION_ID = '00000000-0000-4000-8000-00000000c003';
const AGENT = 'agent_0123456789abcdef';
const SIGNED_URL = `wss://api.elevenlabs.io/v1/convai/conversation?agent_id=${AGENT}&conversation_signature=sig`;

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

const CAPABILITIES = {
  async_delegation: false,
  delivery_scheduling: false,
  reports_idle: false,
  cancels_on_interruption: false,
  configurable_vad: false,
  resumes: false,
  thinking: false,
  direct_tools: true,
  portal_voice: true,
};

const SETUP = {
  type: 'conversation_initiation_client_data',
  conversation_config_override: { agent: { prompt: { prompt: 'You are the voice of LIA.' } } },
  source_info: { source: 'lia', version: 'test' },
};

const START = {
  session_id: SESSION,
  provider: 'elevenlabs',
  model: AGENT,
  mode: 'delegated',
  run_id: `live_session_${SESSION}`,
  credential: SIGNED_URL,
  credential_expires_at: '2030-01-01T00:00:00Z',
  connect_deadline_at: '2030-01-01T00:00:00Z',
  connection: 'token',
  expires_at: '2030-01-01T00:00:00Z',
  session_max_minutes: 30,
  idle_timeout_seconds: 300,
  setup: SETUP,
  preferences: { interruptions: true, end_of_speech: 'normal', result_delivery: 'interrupt' },
  capabilities: CAPABILITIES,
  delegation_tool_name: 'send_to_lia',
  delegation_timeout_seconds: 90,
  delegation_result_max_tokens: 600,
  turn_text_max_chars: 4000,
  rates: {
    pricing_unit: 'per_audio_minute',
    input_unit_price: 0.1,
    output_unit_price: 0,
    audio_input_unit_price: null,
    audio_output_unit_price: null,
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

function routes(chatBodies: Array<Record<string, unknown>>, endBodies: unknown[]): MockRoute[] {
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    {
      url: '**/api/v1/live/connectors',
      json: {
        connectors: [
          {
            provider: 'elevenlabs',
            connector_type: 'elevenlabs_live',
            status: 'active',
            settings: {
              model: AGENT,
              voice: 'agent',
              thinking_level: null,
              idle_timeout_seconds: 300,
              session_max_minutes: 30,
            },
            model_settings: {},
            functionally_verified: true,
            capabilities: CAPABILITIES,
            active: true,
          },
        ],
        active_provider: 'elevenlabs',
      },
    },
    { url: '**/api/v1/live/config', json: LIVE_CONFIG },
    { url: '**/api/v1/live/sessions', method: 'POST', json: START },
    {
      url: `**/api/v1/live/sessions/${SESSION}/turns`,
      method: 'POST',
      json: { user_message_id: null, assistant_message_id: null },
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
            summary_message_id: 'sum3',
            duration_seconds: 42,
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
        created_at: '2026-09-19T09:00:00Z',
        updated_at: '2026-09-19T09:00:00Z',
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

test.describe('chat live session on ElevenLabs', () => {
  test('opens the signed URL, delegates through a client tool, answers it, ends', async ({
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

    const received: Array<Record<string, unknown>> = [];
    let openedUrl = '';
    await page.routeWebSocket(/api\.elevenlabs\.io/, ws => {
      openedUrl = ws.url();
      const frame = (payload: unknown) => ws.send(JSON.stringify(payload));
      ws.onMessage(message => {
        const event = JSON.parse(String(message)) as Record<string, unknown>;
        received.push(event);
        if (event.type === 'conversation_initiation_client_data') {
          frame({
            type: 'conversation_initiation_metadata',
            conversation_initiation_metadata_event: {
              conversation_id: 'conv_e2e',
              agent_output_audio_format: 'pcm_24000',
              user_input_audio_format: 'pcm_16000',
            },
          });
          frame({ type: 'ping', ping_event: { event_id: 1, ping_ms: 20 } });
          frame({
            type: 'user_transcript',
            user_transcription_event: { user_transcript: 'quoi demain ?' },
          });
          frame({
            type: 'client_tool_call',
            client_tool_call: {
              tool_name: 'send_to_lia',
              tool_call_id: 'call_1',
              parameters: { request: 'Quoi demain ?' },
            },
          });
        }
        if (event.type === 'client_tool_result') {
          frame({
            type: 'agent_response',
            agent_response_event: { agent_response: 'Tu as deux réunions demain.' },
          });
        }
      });
    });

    await page.goto('/fr/dashboard/chat');
    await page.getByRole('button', { name: 'Voix et session live' }).click();
    await page.getByRole('menuitem', { name: 'Session Live (ElevenLabs)' }).click();

    const banner = page.getByRole('region', { name: 'Session live' });
    await expect(banner).toBeVisible();
    // The signed URL is the socket's, opened as the API minted it.
    await expect.poll(() => openedUrl).toContain('conversation_signature=sig');
    // The initiation the API rendered went out first, verbatim; the ping got its pong.
    await expect.poll(() => received.length).toBeGreaterThanOrEqual(2);
    expect(received[0]).toEqual(SETUP);
    expect(received.find(e => e.type === 'pong')).toEqual({ type: 'pong', event_id: 1 });

    // The client tool call is a delegation: the request lands in the thread, its answer streams.
    await expect(page.getByText('Quoi demain ?').first()).toBeVisible();
    await expect(page.getByText('Deux réunions demain.').first()).toBeVisible();
    await expect.poll(() => chatBodies.length).toBe(1);
    expect(chatBodies[0]).toMatchObject({
      message: 'Quoi demain ?',
      live_session_id: SESSION,
      spoken_text: 'quoi demain ?',
    });

    // The answer goes back as a client tool result on the same call id, the note beside it.
    await expect.poll(() => received.some(e => e.type === 'client_tool_result')).toBe(true);
    const result = received.find(e => e.type === 'client_tool_result')!;
    expect(result.tool_call_id).toBe('call_1');
    expect(result.is_error).toBe(false);
    expect(JSON.parse(String(result.result))).toMatchObject({
      result: expect.stringContaining('Deux réunions demain.'),
      tone: 'LIA said this warmly.',
    });

    // The agent's whole reply is a caption of the banner.
    await expect(banner).toContainText('Tu as deux réunions demain.');

    await banner.getByRole('button', { name: 'Terminer la session live' }).click();
    await expect(banner).toHaveCount(0);
    await expect.poll(() => endBodies.length).toBe(1);
    expect(endBodies[0]).toEqual({
      outcome: 'ended',
      detail: null,
      provider_conversation_id: 'conv_e2e',
    });
    const card = page.getByTestId('live-session-summary');
    await expect(card).toBeVisible();
    await expect(card).toContainText('terminée par toi');
  });
});
