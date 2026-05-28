/**
 * Tests for keyset pagination (scroll-up) wiring in ``useConversation``.
 *
 * Covers ``loadConversationPage``, ``loadOlderMessages``, and the concurrency
 * mutex on overlapping fetches.
 *
 * Strategy: mock ``@/lib/api-client`` at module level and assert both the
 * shape of the returned ``ConversationPage`` and the ``before`` query param
 * forwarded to the backend.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGet = vi.fn();

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: {
      id: 'user-1',
      email: 'u@test.local',
      picture_url: null,
    },
  }),
}));

vi.mock('@/lib/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('@/lib/logging-context', () => ({
  useLoggingContext: () => ({
    withContext: (ctx: object) => ctx,
  }),
}));

import { useConversation } from '../useConversation';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

interface ApiMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  message_metadata: null;
  created_at: string;
  tokens_in: null;
  tokens_out: null;
  tokens_cache: null;
  cost_eur: null;
  google_api_requests: null;
  stt_provider: null;
  stt_audio_duration_seconds: null;
  stt_cost_eur: null;
  tts_provider: null;
  tts_model: null;
  tts_characters: null;
  tts_cost_eur: null;
}

const makeApiMessage = (id: string, created_at: string, role: 'user' | 'assistant' = 'user'): ApiMessage => ({
  id,
  role,
  content: `msg ${id}`,
  message_metadata: null,
  created_at,
  tokens_in: null,
  tokens_out: null,
  tokens_cache: null,
  cost_eur: null,
  google_api_requests: null,
  stt_provider: null,
  stt_audio_duration_seconds: null,
  stt_cost_eur: null,
  tts_provider: null,
  tts_model: null,
  tts_characters: null,
  tts_cost_eur: null,
});

// Mount the metadata endpoint (GET /conversations/me) so the useEffect on
// mount doesn't break — we don't care about its result here.
const mockMetaResponse = {
  id: 'conv-1',
  user_id: 'user-1',
  title: null,
  message_count: 0,
  total_tokens: 0,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

beforeEach(() => {
  mockGet.mockReset();
  // Default: metadata endpoint returns a fake conversation.
  mockGet.mockImplementation(async (url: string) => {
    if (url === '/conversations/me') return mockMetaResponse;
    throw new Error(`Unexpected URL: ${url}`);
  });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useConversation — keyset pagination', () => {
  it('loadConversationPage returns messages in display order with pagination metadata', async () => {
    // Backend returns DESC (newest first); hook must reverse to oldest-first.
    mockGet.mockImplementation(async (url: string, _config?: unknown) => {
      if (url === '/conversations/me') return mockMetaResponse;
      if (url === '/conversations/me/messages') {
        return {
          messages: [
            makeApiMessage('m3', '2026-01-01T00:03:00Z'),
            makeApiMessage('m2', '2026-01-01T00:02:00Z'),
            makeApiMessage('m1', '2026-01-01T00:01:00Z'),
          ],
          conversation_id: 'conv-1',
          total_count: 3,
          has_more: true,
          next_cursor: '2026-01-01T00:01:00Z',
        };
      }
      throw new Error(`Unexpected URL: ${url}`);
    });

    const { result } = renderHook(() => useConversation());

    let page!: Awaited<ReturnType<typeof result.current.loadConversationPage>>;
    await act(async () => {
      page = await result.current.loadConversationPage();
    });

    expect(page.messages.map(m => m.id)).toEqual(['m1', 'm2', 'm3']);
    expect(page.hasMore).toBe(true);
    expect(page.nextCursor).toBe('2026-01-01T00:01:00Z');
  });

  it('loadOlderMessages forwards the cursor as the "before" query param', async () => {
    const olderPageResponse = {
      messages: [
        makeApiMessage('m0', '2026-01-01T00:00:00Z'),
      ],
      conversation_id: 'conv-1',
      total_count: 1,
      has_more: false,
      next_cursor: null,
    };
    mockGet.mockImplementation(async (url: string) => {
      if (url === '/conversations/me') return mockMetaResponse;
      if (url === '/conversations/me/messages') return olderPageResponse;
      throw new Error(`Unexpected URL: ${url}`);
    });

    const { result } = renderHook(() => useConversation());

    await act(async () => {
      await result.current.loadOlderMessages('2026-01-01T00:01:00Z');
    });

    // Locate the messages call (the metadata call from mount has different URL)
    const messagesCall = mockGet.mock.calls.find(
      ([url]) => url === '/conversations/me/messages'
    );
    expect(messagesCall).toBeDefined();
    const config = messagesCall![1] as { params: { limit: number; before?: string } };
    expect(config.params.before).toBe('2026-01-01T00:01:00Z');
    expect(config.params.limit).toBe(50);
  });

  it('loadOlderMessages mutex skips overlapping calls', async () => {
    // Pending response — never resolves until we let it. Forces both calls
    // to overlap inside the same tick.
    let resolveFirst: ((v: unknown) => void) | undefined;
    const olderResponse = {
      messages: [makeApiMessage('m0', '2026-01-01T00:00:00Z')],
      conversation_id: 'conv-1',
      total_count: 1,
      has_more: false,
      next_cursor: null,
    };

    mockGet.mockImplementation((url: string) => {
      if (url === '/conversations/me') return Promise.resolve(mockMetaResponse);
      if (url === '/conversations/me/messages') {
        return new Promise(resolve => {
          resolveFirst = resolve;
        }).then(() => olderResponse);
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });

    const { result } = renderHook(() => useConversation());

    let firstPromise!: Promise<Awaited<ReturnType<typeof result.current.loadOlderMessages>>>;
    let secondPage!: Awaited<ReturnType<typeof result.current.loadOlderMessages>>;
    await act(async () => {
      firstPromise = result.current.loadOlderMessages('2026-01-01T00:01:00Z');
      // Second call fires while the first is still in flight — must short-circuit
      secondPage = await result.current.loadOlderMessages('2026-01-01T00:01:00Z');
    });

    expect(secondPage.messages).toEqual([]);
    expect(secondPage.hasMore).toBe(false);

    // Let the first call complete cleanly so test teardown doesn't leak.
    await act(async () => {
      resolveFirst?.(undefined);
      await firstPromise;
    });

    // Only one /messages call was actually issued by the mutex-guarded path.
    const messagesCalls = mockGet.mock.calls.filter(
      ([url]) => url === '/conversations/me/messages'
    );
    expect(messagesCalls).toHaveLength(1);
  });

  it('first page omits the "before" query param', async () => {
    mockGet.mockImplementation(async (url: string) => {
      if (url === '/conversations/me') return mockMetaResponse;
      if (url === '/conversations/me/messages') {
        return {
          messages: [],
          conversation_id: 'conv-1',
          total_count: 0,
          has_more: false,
          next_cursor: null,
        };
      }
      throw new Error(`Unexpected URL: ${url}`);
    });

    const { result } = renderHook(() => useConversation());

    await act(async () => {
      await result.current.loadConversationPage();
    });

    const messagesCall = mockGet.mock.calls.find(
      ([url]) => url === '/conversations/me/messages'
    );
    expect(messagesCall).toBeDefined();
    const config = messagesCall![1] as { params: { limit: number; before?: string } };
    expect(config.params.before).toBeUndefined();
  });
});
