/**
 * ChatSSEClient — the 429 that means "the demo is paused", not "your quota".
 *
 * Layer 0 rejects before the stream opens, so this path must carry the same
 * distinction the stream does. The backend switches to a structured detail
 * (the shape already used by the 409 active-run contract) whenever it is the
 * instance ceiling rather than a personal limit.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { ChatSSEClient, ChatStreamError } from '../chat';
import type { ChatRequest } from '@/types/chat';

const fetchMock = vi.fn();
const REQUEST: ChatRequest = { message: 'bonjour', user_id: 'u-1', session_id: 's-1' };

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Runs the real client against one stubbed response and returns its error. */
async function errorFor(response: Response): Promise<ChatStreamError> {
  const errors: Error[] = [];
  fetchMock.mockResolvedValue(response);
  await new ChatSSEClient().streamChat(
    REQUEST,
    () => {},
    e => errors.push(e),
    () => {}
  );
  return errors[0] as ChatStreamError;
}

function jsonResponse(body: unknown, status: number, headers?: HeadersInit): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...(headers ?? {}) },
  });
}

describe('429 — instance ceiling versus personal quota', () => {
  it('maps the structured instance detail to its own i18n key', async () => {
    const error = await errorFor(
      jsonResponse(
        {
          detail: {
            error: 'Instance daily budget exhausted',
            error_code: 'instance_budget_exhausted',
            limit: 'instance_daily_budget',
          },
        },
        429,
        { 'Retry-After': '3600' }
      )
    );

    expect(error.name).toBe('InstanceBudgetExhaustedError');
    expect(error.i18nKey).toBe('errors.chat.instance_budget_exhausted');
  });

  it('keeps the personal-quota mapping for a plain string detail', async () => {
    const error = await errorFor(jsonResponse({ detail: 'quota reached' }, 429));

    expect(error.name).toBe('UsageLimitExceededError');
    expect(error.i18nKey).toBe('errors.chat.usage_limit_exceeded');
  });

  it('falls back to the personal-quota mapping when the body is unreadable', async () => {
    // A proxy may replace the body; a parse failure must not lose the 429.
    const error = await errorFor(new Response('<html>429</html>', { status: 429 }));

    expect(error.name).toBe('UsageLimitExceededError');
    expect(error.i18nKey).toBe('errors.chat.usage_limit_exceeded');
  });
});
