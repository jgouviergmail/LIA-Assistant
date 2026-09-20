/**
 * Chat journey — the live mode on GPT-Live (ADR-299, wave 2 A9), hermetic.
 *
 * The provider is played by a fake `RTCPeerConnection` installed before the
 * page's scripts run: it hands out an offer, opens the `oai-events` data
 * channel once the answer is set, emits the person's transcript and a
 * `session.delegation.created` that carries NO text (the documented shape),
 * and records what the page appends. The API is mocked (connectors, config,
 * start with `connection: offer`, the OFFER EXCHANGE, turns, end, chat
 * stream). Proves in a real browser tree that:
 *  - the session opens through the API's offer exchange with the nonce;
 *  - the request is composed from the input transcript and lands in the
 *    thread as a user bubble, its answer streams;
 *  - the answer goes back to the voice as `session.commentary.append`;
 *  - End asks `session.close` and posts the outcome.
 *
 * No backend, LLM, or paid provider is contacted.
 */
import { test, expect, type MockRoute } from '../fixtures';

test.use({
  launchOptions: {
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
  },
});

const SESSION = 'b'.repeat(32);
const CONVERSATION_ID = '00000000-0000-4000-8000-00000000c002';
const NONCE = 'n'.repeat(43);

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
  async_delegation: true,
  delivery_scheduling: false,
  reports_idle: false,
  cancels_on_interruption: false,
  configurable_vad: false,
  resumes: false,
  thinking: false,
};

const START = {
  session_id: SESSION,
  provider: 'openai',
  model: 'gpt-live-1',
  run_id: `live_session_${SESSION}`,
  credential: NONCE,
  credential_expires_at: '2030-01-01T00:00:00Z',
  connect_deadline_at: '2030-01-01T00:00:00Z',
  connection: 'offer',
  expires_at: '2030-01-01T00:00:00Z',
  session_max_minutes: 30,
  idle_timeout_seconds: 300,
  setup: {},
  preferences: {
    interruptions: true,
    end_of_speech: 'normal',
    result_delivery: 'interrupt',
  },
  capabilities: CAPABILITIES,
  delegation_tool_name: 'send_to_lia',
  delegation_timeout_seconds: 90,
  delegation_result_max_tokens: 600,
  turn_text_max_chars: 4000,
  rates: {
    pricing_unit: 'per_audio_minute',
    input_unit_price: 0.05,
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
  session_max_bounds: { min: 1, max: 240 },
  idle_timeout_bounds: { min: 5, max: 3600 },
  unlimited_value: 0,
  tone_lines: {},
};

function sseAnswer(text: string): string {
  return (
    `data: ${JSON.stringify({ type: 'token', content: text, metadata: null })}\n\n` +
    'data: {"type":"done","content":"","metadata":null}\n\n'
  );
}

function routes(
  chatBodies: Array<Record<string, unknown>>,
  offerBodies: Array<Record<string, unknown>>,
  endBodies: unknown[]
): MockRoute[] {
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    {
      url: '**/api/v1/live/connectors',
      json: {
        connectors: [
          {
            provider: 'openai',
            connector_type: 'gpt_live',
            status: 'active',
            settings: {
              model: 'gpt-live-1',
              voice: 'quartz',
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
        active_provider: 'openai',
      },
    },
    { url: '**/api/v1/live/config', json: LIVE_CONFIG },
    { url: '**/api/v1/live/sessions', method: 'POST', json: START },
    {
      url: `**/api/v1/live/sessions/${SESSION}/offer`,
      method: 'POST',
      handler: async route => {
        offerBodies.push((route.request().postDataJSON() ?? {}) as Record<string, unknown>);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ sdp: 'v=0\r\no=- 1 1 IN IP4 0.0.0.0\r\ns=answer\r\n' }),
        });
      },
    },
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
            summary_message_id: 'sum2',
            duration_seconds: 40,
            delegations: 1,
            voice_turns: 0,
            extensions: 0,
            usage: {
              tokens_in: 10,
              tokens_out: 5,
              tokens_cache: 0,
              cost_eur: 0.0021,
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

/**
 * The fake peer connection, installed before any page script: the offer's
 * SDP is a fixed string, the channel opens once the answer is set, and the
 * provider's events are played on it. What the page sends is kept on
 * `window.__liveSent` for the test to read.
 */
const FAKE_WEBRTC = `
(() => {
  const sent = [];
  window.__liveSent = sent;
  class FakeChannel extends EventTarget {
    constructor(label) {
      super();
      this.label = label;
      this.readyState = 'connecting';
      this.onopen = null; this.onclose = null; this.onerror = null; this.onmessage = null;
    }
    send(data) {
      const event = JSON.parse(data);
      sent.push(event);
      if (event.type === 'session.close') {
        setTimeout(() => this.emit({ type: 'session.closed', reason: 'close_requested', usage: { seconds: 40 } }), 20);
      }
    }
    close() { this.readyState = 'closed'; }
    emit(event) { this.onmessage && this.onmessage({ data: JSON.stringify(event) }); }
    open() { this.readyState = 'open'; this.onopen && this.onopen(); }
  }
  class FakePeer extends EventTarget {
    constructor() {
      super();
      this.channels = [];
      this.localDescription = null;
      this.remoteDescription = null;
      this.iceGatheringState = 'complete';
      this.connectionState = 'new';
      this.ontrack = null;
      this.onconnectionstatechange = null;
    }
    createDataChannel(label) { const c = new FakeChannel(label); this.channels.push(c); window.__liveChannel = c; return c; }
    addTrack() {}
    async createOffer() { return { type: 'offer', sdp: 'v=0\\r\\no=- 1 1 IN IP4 0.0.0.0\\r\\ns=offer\\r\\n' }; }
    async setLocalDescription(d) { this.localDescription = d; }
    async setRemoteDescription(d) {
      this.remoteDescription = d;
      const channel = this.channels[0];
      setTimeout(() => {
        channel.open();
        channel.emit({ type: 'session.started', session: { id: 'live_1' } });
        // The person's words, then the model's own delegation (no text in it).
        channel.emit({ type: 'session.input_transcript.delta', delta: 'quoi ', start_ms: 100, end_ms: 400 });
        channel.emit({ type: 'session.input_transcript.delta', delta: 'demain ?', start_ms: 400, end_ms: 900 });
        channel.emit({ type: 'session.delegation.created', event_id: 'e1', offset_ms: 1200, delegation: { id: 'd1', type: 'delegation', target: 'client' } });
        // The provider's usage tick (ADR-300 wave 3): the seconds the meter bills.
        channel.emit({ type: 'session.usage.updated', usage: { seconds: 90 }, context_window: { usage_ratio: 0.12 } });
      }, 10);
    }
    close() { this.connectionState = 'closed'; }
  }
  window.RTCPeerConnection = FakePeer;
})();
`;

test.describe('chat live session on GPT-Live', () => {
  test('opens through the offer exchange, composes the request, appends the answer, ends', async ({
    page,
    context,
    authenticate,
    mockApi,
  }) => {
    await context.grantPermissions(['microphone']);
    await authenticate();
    const chatBodies: Array<Record<string, unknown>> = [];
    const offerBodies: Array<Record<string, unknown>> = [];
    const endBodies: unknown[] = [];
    await mockApi(routes(chatBodies, offerBodies, endBodies));
    await page.addInitScript(FAKE_WEBRTC);

    await page.goto('/fr/dashboard/chat');
    const voiceMenu = page.getByRole('button', { name: 'Voix et session live' });
    await expect(voiceMenu).toBeVisible();
    await voiceMenu.click();
    await page.getByRole('menuitem', { name: 'Session Live (OpenAI)' }).click();

    const banner = page.getByRole('region', { name: 'Session live' });
    await expect(banner).toBeVisible();

    // The offer left with the nonce, and the session is live once the channel opened.
    await expect.poll(() => offerBodies.length).toBe(1);
    expect(offerBodies[0]).toMatchObject({ credential: NONCE });
    expect(String(offerBodies[0].sdp)).toContain('s=offer');

    // The request composed from the transcript reaches the chat, stamped with the session.
    await expect(page.getByText('quoi demain ?').first()).toBeVisible();
    await expect(page.getByText('Deux réunions demain.').first()).toBeVisible();
    await expect.poll(() => chatBodies.length).toBe(1);
    expect(chatBodies[0]).toMatchObject({
      message: 'quoi demain ?',
      live_session_id: SESSION,
      spoken_text: 'quoi demain ?',
    });

    // The answer goes back to the voice as spoken commentary on the delegation.
    const sent = () =>
      page.evaluate(() => (window as unknown as { __liveSent: unknown[] }).__liveSent);
    await expect
      .poll(async () =>
        (await sent()).some(
          e =>
            (e as { type: string }).type === 'session.commentary.append' &&
            (e as { delegation_id: string }).delegation_id === 'd1' &&
            String((e as { content: string }).content).includes('Deux réunions demain.')
        )
      )
      .toBe(true);

    // The meter of a minute-billed model: the clock (the provider's 90 s) priced
    // per minute, and the share of the context window (ADR-300 wave 3).
    const meter = banner.getByTestId('live-meter');
    await expect(meter).toContainText('⏱ 1:30');
    await expect(meter).toContainText('0,0675 €');
    await expect(meter).toContainText('contexte 12 %');

    await banner.getByRole('button', { name: 'Terminer la session live' }).click();
    await expect(banner).toHaveCount(0);
    await expect.poll(() => endBodies.length).toBe(1);
    expect(endBodies[0]).toEqual({ outcome: 'ended', detail: null });
    expect((await sent()).some(e => (e as { type: string }).type === 'session.close')).toBe(true);
    const card = page.getByTestId('live-session-summary');
    await expect(card).toBeVisible();
    await expect(card).toContainText('0,0021 €');
  });
});
