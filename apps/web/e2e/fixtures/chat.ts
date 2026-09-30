import type { MockRoute } from './api-mock';

/**
 * The chat-page mocks shared by every spec that lands on `/dashboard/chat`,
 * with the POST bodies captured so assertions are about WHAT was sent.
 *
 * Extracted 2026-08-05 (ADR-210): the two-people 360° spec and the intent
 * replay spec each need the same surface — an empty history, a healthy agent,
 * and a `/agents/chat/stream` handler that records its body and answers with
 * a minimal token+done stream. Two copies of one contract do not stay equal
 * (the relations fixture learned this on 2026-08-03).
 */

/** The slice of the chat POST body the specs assert on. */
export interface ChatBody {
  message?: string;
  directive?: { capability?: string; subject?: string };
}

/**
 * Chat-page routes; every captured POST body is pushed onto `bodies`.
 *
 * @param bodies - The spec's capture array — assertions poll its length.
 */
export function chatRoutes(bodies: ChatBody[]): MockRoute[] {
  return [
    { url: '**/api/v1/conversations/me/totals', json: {} },
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: [],
        conversation_id: '00000000-0000-4000-8000-0000000000ff',
        total_count: 0,
        has_more: false,
        next_cursor: null,
      },
    },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async route => {
        bodies.push((route.request().postDataJSON() ?? {}) as ChatBody);
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body:
            'data: {"type":"token","content":"Voici le point.","metadata":null}\n\n' +
            'data: {"type":"done","content":"","metadata":null}\n\n',
        });
      },
    },
  ];
}

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c0h1',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E chat header',
  message_count: 2,
  total_tokens: 1200,
  created_at: '2026-07-26T09:00:00Z',
  updated_at: '2026-07-26T10:00:00Z',
};

/**
 * A LOADED chat: history, totals and active knowledge spaces — the context
 * pill, the spaces indicator and the status pill only appear in this state,
 * the one a real user is in, so every header geometry check lands here.
 */
export function loadedChatRoutes(): MockRoute[] {
  return [
    { url: '**/api/v1/conversations/me', json: CONVERSATION },
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: [
          {
            id: '00000000-0000-4000-8000-00000000m0h1',
            role: 'assistant',
            content: '<p>Bonjour.</p>',
            created_at: '2026-07-26T10:00:00Z',
          },
        ],
        conversation_id: CONVERSATION.id,
        total_count: 1,
        has_more: false,
        next_cursor: null,
      },
    },
    {
      url: '**/api/v1/conversations/me/totals',
      json: {
        total_tokens_in: 42000,
        total_tokens_out: 18000,
        total_tokens_cache: 6000,
        total_cost_eur: 0.42,
        total_google_api_requests: 12,
        context_tokens: 68000,
        context_threshold: 100000,
      },
    },
    {
      url: '**/api/v1/rag-spaces*',
      json: {
        spaces: [
          { id: 's1', name: 'Documentation', is_active: true, document_count: 12 },
          { id: 's2', name: 'Contrats', is_active: true, document_count: 4 },
        ],
        total: 2,
      },
    },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
  ];
}
