/**
 * useConversation — API mapping, error paths, totals and reset.
 *
 * Complements useConversation.pagination.test.ts (keyset pagination, mutex):
 * this suite covers the ConversationMessage → Message UI mapping, the 404
 * soft paths for new users, generic error resilience, loadConversationTotals
 * and resetConversation.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const h = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  user: {
    id: 'user-1',
    email: 'u@test.local',
    picture_url: 'https://avatar/u1.png',
  } as { id: string; email: string; picture_url: string | null } | null,
}));

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: (...args: unknown[]) => h.get(...args),
    post: (...args: unknown[]) => h.post(...args),
  },
}));

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: h.user }),
}));

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

vi.mock('@/lib/logging-context', () => {
  // Stable identity across renders, like the real useMemo-backed context —
  // an unstable withContext would re-trigger every effect depending on it.
  const withContext = (ctx?: object) => ctx ?? {};
  return { useLoggingContext: () => ({ withContext }) };
});

import { useConversation } from '../useConversation';
import { logger } from '@/lib/logger';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const META = {
  id: 'conv-1',
  user_id: 'user-1',
  title: null,
  message_count: 2,
  total_tokens: 100,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const RICH_API_MESSAGE = {
  id: 'm-voice',
  role: 'user' as const,
  content: 'message dicté',
  message_metadata: {
    generated_images: [{ url: 'https://img/1.png', alt: 'généré' }],
    browser_screenshot: { url: 'https://shot/1.jpg', alt: 'capture' },
  },
  created_at: '2026-01-01T00:01:00Z',
  tokens_in: 11,
  tokens_out: 22,
  tokens_cache: 3,
  cost_eur: 0.05,
  google_api_requests: 2,
  stt_provider: 'elevenlabs',
  stt_audio_duration_seconds: 4.5,
  stt_cost_eur: 0.001,
  tts_provider: 'openai',
  tts_model: 'tts-1',
  tts_characters: 120,
  tts_cost_eur: 0.002,
};

function pageResponse(messages: unknown[] = []) {
  return {
    messages,
    conversation_id: 'conv-1',
    total_count: messages.length,
    has_more: false,
    next_cursor: null,
  };
}

function http404(): Error {
  const error = new Error('Not Found') as Error & { response: { status: number } };
  error.response = { status: 404 };
  return error;
}

beforeEach(() => {
  vi.clearAllMocks();
  h.user = { id: 'user-1', email: 'u@test.local', picture_url: 'https://avatar/u1.png' };
  h.get.mockImplementation(async (url: string) => {
    if (url === '/conversations/me') return META;
    throw new Error(`Unexpected URL: ${url}`);
  });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useConversation — metadata load on mount', () => {
  it('exposes the conversation metadata fetched at mount', async () => {
    const { result } = renderHook(() => useConversation());

    await act(async () => {});

    expect(result.current.conversation).toEqual(META);
  });

  it('keeps conversation=null when the metadata call fails', async () => {
    h.get.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useConversation());

    await act(async () => {});

    expect(result.current.conversation).toBeNull();
    expect(logger.error).toHaveBeenCalledWith(
      'conversation_load_failed',
      expect.any(Error),
      expect.any(Object)
    );
  });
});

describe('useConversation — UI message mapping', () => {
  it('maps every backend field to the UI Message shape (voice + costs + media)', async () => {
    h.get.mockImplementation(async (url: string) => {
      if (url === '/conversations/me') return META;
      if (url === '/conversations/me/messages') return pageResponse([RICH_API_MESSAGE]);
      throw new Error(`Unexpected URL: ${url}`);
    });
    const { result } = renderHook(() => useConversation());

    let page!: Awaited<ReturnType<typeof result.current.loadConversationPage>>;
    await act(async () => {
      page = await result.current.loadConversationPage();
    });

    expect(page.messages).toHaveLength(1);
    expect(page.messages[0]).toMatchObject({
      id: 'm-voice',
      role: 'user',
      content: 'message dicté',
      avatar: 'https://avatar/u1.png',
      tokensIn: 11,
      tokensOut: 22,
      tokensCache: 3,
      costEur: 0.05,
      googleApiRequests: 2,
      source: 'voice', // derived from stt_provider
      sttProvider: 'elevenlabs',
      sttAudioDurationSeconds: 4.5,
      sttCostEur: 0.001,
      audioDurationSeconds: 4.5,
      ttsProvider: 'openai',
      ttsModel: 'tts-1',
      ttsCharacters: 120,
      ttsCostEur: 0.002,
      generatedImages: [{ url: 'https://img/1.png', alt: 'généré' }],
      browserScreenshot: { url: 'https://shot/1.jpg', alt: 'capture' },
    });
    expect(page.messages[0].timestamp).toEqual(new Date('2026-01-01T00:01:00Z'));
  });

  it('maps a bare assistant message with nulls to a clean UI message', async () => {
    const bare = {
      ...RICH_API_MESSAGE,
      id: 'm-bare',
      role: 'assistant' as const,
      message_metadata: null,
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
    };
    h.get.mockImplementation(async (url: string) => {
      if (url === '/conversations/me') return META;
      if (url === '/conversations/me/messages') return pageResponse([bare]);
      throw new Error(`Unexpected URL: ${url}`);
    });
    const { result } = renderHook(() => useConversation());

    let page!: Awaited<ReturnType<typeof result.current.loadConversationPage>>;
    await act(async () => {
      page = await result.current.loadConversationPage();
    });

    const message = page.messages[0];
    expect(message.avatar).toBeUndefined(); // assistant → no avatar
    expect(message.source).toBeUndefined(); // no stt_provider → not voice
    expect(message.tokensIn).toBeUndefined();
    expect(message.generatedImages).toBeUndefined();
    // QW-5: history rows always carry their DB id (feedback endpoint target) —
    // a bare message has nothing else in its metadata.
    expect(message.metadata).toEqual({ message_db_id: message.id });
  });
});

describe('useConversation — page fetch error paths', () => {
  it('returns an empty page on 404 (new user, no conversation yet)', async () => {
    h.get.mockImplementation(async (url: string) => {
      if (url === '/conversations/me') return META;
      throw http404();
    });
    const { result } = renderHook(() => useConversation());

    let page!: Awaited<ReturnType<typeof result.current.loadConversationPage>>;
    await act(async () => {
      page = await result.current.loadConversationPage();
    });

    expect(page).toEqual({ messages: [], hasMore: false, nextCursor: null });
    expect(logger.error).not.toHaveBeenCalled();
  });

  it('returns an empty page and logs on a generic error', async () => {
    h.get.mockImplementation(async (url: string) => {
      if (url === '/conversations/me') return META;
      throw new Error('500 internal');
    });
    const { result } = renderHook(() => useConversation());

    let page!: Awaited<ReturnType<typeof result.current.loadConversationPage>>;
    await act(async () => {
      page = await result.current.loadConversationPage();
    });

    expect(page).toEqual({ messages: [], hasMore: false, nextCursor: null });
    expect(logger.error).toHaveBeenCalledWith(
      'conversation_history_load_failed',
      expect.any(Error),
      expect.any(Object)
    );
  });

  it('returns empty pages without any API call when no user is authenticated', async () => {
    h.user = null;
    const { result } = renderHook(() => useConversation());

    let page!: Awaited<ReturnType<typeof result.current.loadConversationPage>>;
    let older!: Awaited<ReturnType<typeof result.current.loadOlderMessages>>;
    await act(async () => {
      page = await result.current.loadConversationPage();
      older = await result.current.loadOlderMessages('2026-01-01T00:00:00Z');
    });

    expect(page.messages).toEqual([]);
    expect(older.messages).toEqual([]);
    expect(h.get).not.toHaveBeenCalled();
  });
});

describe('useConversation — totals', () => {
  const TOTALS = {
    conversation_id: 'conv-1',
    total_tokens_in: 100,
    total_tokens_out: 50,
    total_tokens_cache: 10,
    total_cost_eur: 0.5,
    total_google_api_requests: 4,
    context_tokens: 12_000,
    context_threshold: 48_000,
  };

  it('returns the aggregate totals', async () => {
    h.get.mockImplementation(async (url: string) => {
      if (url === '/conversations/me') return META;
      if (url === '/conversations/me/totals') return TOTALS;
      throw new Error(`Unexpected URL: ${url}`);
    });
    const { result } = renderHook(() => useConversation());

    let totals!: Awaited<ReturnType<typeof result.current.loadConversationTotals>>;
    await act(async () => {
      totals = await result.current.loadConversationTotals();
    });

    expect(totals).toEqual(TOTALS);
  });

  it('returns null on 404 without logging an error', async () => {
    h.get.mockImplementation(async (url: string) => {
      if (url === '/conversations/me') return META;
      throw http404();
    });
    const { result } = renderHook(() => useConversation());

    let totals!: Awaited<ReturnType<typeof result.current.loadConversationTotals>>;
    await act(async () => {
      totals = await result.current.loadConversationTotals();
    });

    expect(totals).toBeNull();
    expect(logger.error).not.toHaveBeenCalled();
  });

  it('returns null and logs on a generic error; null without user', async () => {
    h.get.mockImplementation(async (url: string) => {
      if (url === '/conversations/me') return META;
      throw new Error('boom');
    });
    const { result } = renderHook(() => useConversation());

    let totals!: Awaited<ReturnType<typeof result.current.loadConversationTotals>>;
    await act(async () => {
      totals = await result.current.loadConversationTotals();
    });
    expect(totals).toBeNull();
    expect(logger.error).toHaveBeenCalledWith(
      'conversation_totals_load_failed',
      expect.any(Error),
      expect.any(Object)
    );

    h.user = null;
    const { result: anonymous } = renderHook(() => useConversation());
    await act(async () => {
      totals = await anonymous.current.loadConversationTotals();
    });
    expect(totals).toBeNull();
  });
});

describe('useConversation — reset', () => {
  it('posts the reset and clears the local conversation state', async () => {
    h.post.mockResolvedValue({});
    const { result } = renderHook(() => useConversation());

    await act(async () => {}); // let the mount metadata load
    expect(result.current.conversation).toEqual(META);

    await act(async () => {
      await result.current.resetConversation();
    });

    expect(h.post).toHaveBeenCalledWith('/conversations/me/reset');
    expect(result.current.conversation).toBeNull();
  });

  it('re-throws on failure so the caller can surface the error', async () => {
    h.post.mockRejectedValue(new Error('reset failed'));
    const { result } = renderHook(() => useConversation());

    await expect(
      act(async () => {
        await result.current.resetConversation();
      })
    ).rejects.toThrow('reset failed');
    expect(logger.error).toHaveBeenCalledWith(
      'conversation_reset_failed',
      expect.any(Error),
      expect.any(Object)
    );
  });

  it('throws immediately without a user', async () => {
    h.user = null;
    const { result } = renderHook(() => useConversation());

    await expect(
      act(async () => {
        await result.current.resetConversation();
      })
    ).rejects.toThrow('User not authenticated');
    expect(h.post).not.toHaveBeenCalled();
  });
});
