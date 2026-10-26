import type { MockRoute } from './api-mock';

export const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c001',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E HITL',
  message_count: 0,
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

/** Pending tool_confirmation interrupt (shape from the T0.3 runtime capture). */
export const PENDING_TOOL_CONFIRMATION = {
  message_id: 'hitl_e2e_tool_1',
  action_requests: [
    {
      type: 'tool_confirmation',
      tool_name: 'send_email_tool',
      tool_args: { to: 'e2e@example.com', subject: 'Bonjour' },
      available_actions: [
        { action: 'confirm', label: 'confirm', style: 'primary' },
        { action: 'cancel', label: 'cancel', style: 'destructive' },
      ],
      registry_ids: [],
    },
  ],
  interrupt_ts: '2026-07-18T10:00:00+00:00',
  generated_question: "Confirmer l'envoi de l'e-mail ?",
};

/** SSE body: a bare done chunk (resolves a submitted card). */
export function sseDone(): string {
  return 'data: {"type":"done","content":"","metadata":null}\n\n';
}

/** Common mocks for a chat page with one pending interrupt. */
export function baseRoutes(pendingBody: unknown, streamBody: () => string): MockRoute[] {
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    { url: '**/api/v1/conversations/me', json: CONVERSATION },
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: [],
        conversation_id: CONVERSATION.id,
        total_count: 0,
        has_more: false,
        next_cursor: null,
      },
    },
    { url: '**/api/v1/conversations/me/totals', json: {} },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: pendingBody },
    { url: '**/api/v1/usage/**', json: {} },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async route => {
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: streamBody(),
        });
      },
    },
  ];
}
