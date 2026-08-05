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
