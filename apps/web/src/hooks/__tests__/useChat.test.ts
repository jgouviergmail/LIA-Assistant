/**
 * useChat — end-to-end hook tests over a scripted SSE chunk driver.
 *
 * The chatSSEClient is mocked at module level: each test scripts the exact
 * chunk sequence the backend would stream and drives it through the REAL
 * processSSEChunk / chat-reducer pipeline, asserting the resulting hook
 * state. requestAnimationFrame is stubbed so token batching only flushes
 * through the synchronous paths (non-token chunk, onError flush), keeping
 * every test deterministic.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { toast } from 'sonner';

import type { ChatStreamChunk } from '@/types/chat';

// ---------------------------------------------------------------------------
// Hoisted mutable state consumed by the module mocks below
// ---------------------------------------------------------------------------

const h = vi.hoisted(() => {
  const streamChat = vi.fn();
  const cancel = vi.fn();
  return {
    streamChat,
    cancel,
    user: {
      id: 'user-1',
      email: 'u@test.local',
      picture_url: null,
    } as { id: string; email: string; picture_url: string | null } | null,
    geolocation: {
      coordinates: null as { lat: number; lon: number; accuracy: number; timestamp: number } | null,
      isEnabled: false,
      permission: 'prompt' as string,
      enable: vi.fn(async () => true),
    },
    onStatusChange: null as ((available: boolean) => void) | null,
    requiresGeolocation: vi.fn((_content: string, _language: string) => false),
    voice: {
      handleVoiceChunk: vi.fn(),
      stopPlayback: vi.fn(),
      warmupAudio: vi.fn(async () => {}),
      recordUserInteraction: vi.fn(),
    },
  };
});

vi.mock('@/lib/api/chat', async importOriginal => {
  // Keep the real ChatStreamError class: useChat narrows errors with
  // `instanceof ChatStreamError` to resolve their i18n key.
  const actual = await importOriginal<typeof import('@/lib/api/chat')>();
  return {
    ...actual,
    chatSSEClient: {
      streamChat: (...args: unknown[]) => h.streamChat(...args),
      cancel: (...args: unknown[]) => h.cancel(...args),
    },
  };
});

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: h.user }),
}));

vi.mock('@/hooks/useGeolocation', () => ({
  useGeolocation: () => h.geolocation,
}));

vi.mock('@/hooks/useLiaGender', () => ({
  useLiaGender: () => ({ isMale: false }),
}));

vi.mock('@/hooks/useVoicePlayback', () => ({
  useVoicePlayback: () => h.voice,
}));

vi.mock('@/hooks/useAPIHealth', () => ({
  useAPIHealth: (opts: { onStatusChange: (available: boolean) => void }) => {
    h.onStatusChange = opts.onStatusChange;
    return { apiAvailable: true, checkHealth: vi.fn(), isChecking: false };
  },
}));

vi.mock('@/lib/location-detection', () => ({
  messageRequiresGeolocation: (content: string, language: string) =>
    h.requiresGeolocation(content, language),
}));

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

vi.mock('@/lib/logging-context', () => {
  // Stable identity across renders, like the real useMemo-backed context.
  const withContext = (ctx?: object) => ctx ?? {};
  return { useLoggingContext: () => ({ withContext }) };
});

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    info: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    loading: vi.fn(),
  }),
}));

import { useChat } from '../useChat';

// ---------------------------------------------------------------------------
// Scripted stream driver
// ---------------------------------------------------------------------------

type OnChunk = (chunk: ChatStreamChunk) => void;
type OnError = (error: Error) => void;
type OnDone = () => void;

/** Configure the mocked streamChat to replay `chunks` then complete. */
function scriptStream(chunks: ChatStreamChunk[]): void {
  h.streamChat.mockImplementation(
    async (_req: unknown, onChunk: OnChunk, _onError: OnError, onDone: OnDone) => {
      for (const chunk of chunks) onChunk(chunk);
      onDone();
    }
  );
}

function token(content: string): ChatStreamChunk {
  return { type: 'token', content } as ChatStreamChunk;
}

function done(metadata: Record<string, unknown> = {}): ChatStreamChunk {
  return { type: 'done', content: '', metadata } as ChatStreamChunk;
}

const ROUTER_CHUNK = {
  type: 'router_decision',
  content: '',
  metadata: {
    intention: 'conversation',
    confidence: 0.9,
    context_label: 'x',
    next_node: 'response',
  },
} as ChatStreamChunk;

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  h.user = { id: 'user-1', email: 'u@test.local', picture_url: null };
  h.geolocation.coordinates = null;
  h.geolocation.isEnabled = false;
  h.geolocation.permission = 'prompt';
  h.requiresGeolocation.mockReturnValue(false);
  h.onStatusChange = null;
  // Token batching must never rely on a real animation frame in these tests:
  // ordering is guaranteed by the synchronous flushes (non-token chunk, error).
  vi.stubGlobal(
    'requestAnimationFrame',
    vi.fn(() => 1)
  );
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useChat — nominal send/stream/done cycle', () => {
  it('streams a full turn: user message, aggregated answer, idle at the end', async () => {
    scriptStream([
      ROUTER_CHUNK,
      token('Bonjour'),
      token(' Julien'),
      done({ tokens_in: 12, tokens_out: 34, cost_eur: 0.01, message_count: 2 }),
    ]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('Salut LIA');
    });

    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[0]).toMatchObject({ role: 'user', content: 'Salut LIA' });
    expect(result.current.messages[1]).toMatchObject({
      role: 'assistant',
      content: 'Bonjour Julien',
      tokensIn: 12,
      tokensOut: 34,
    });
    expect(result.current.isTyping).toBe(false);
    expect(result.current.conversationTotals).toMatchObject({
      totalTokensIn: 12,
      totalTokensOut: 34,
      totalCostEur: 0.01,
      totalMessages: 2,
    });
  });

  it('replaces the progress feedback with the real answer (no residual progress bubble)', async () => {
    scriptStream([
      ROUTER_CHUNK,
      {
        type: 'execution_step',
        content: '',
        metadata: { emoji: '🧠', i18n_key: 'analyzing' },
      } as ChatStreamChunk,
      token('Réponse finale'),
      done(),
    ]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('Question');
    });

    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[1].content).toBe('Réponse finale');
    expect(result.current.messages[1].content).not.toContain('execution.steps');
  });

  it('accumulates totals across two consecutive turns', async () => {
    scriptStream([token('a'), done({ tokens_in: 10, tokens_out: 5, message_count: 2 })]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('un');
    });
    await act(async () => {
      await result.current.sendMessage('deux');
    });

    expect(result.current.conversationTotals.totalTokensIn).toBe(20);
    expect(result.current.conversationTotals.totalMessages).toBe(4);
    expect(result.current.messages).toHaveLength(4);
  });

  it('cancels any pending stream before starting a new one', async () => {
    scriptStream([token('x'), done()]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('hello');
    });

    expect(h.cancel).toHaveBeenCalledTimes(1);
    expect(h.cancel.mock.invocationCallOrder[0]).toBeLessThan(
      h.streamChat.mock.invocationCallOrder[0]
    );
    expect(h.voice.stopPlayback).toHaveBeenCalled();
    expect(h.voice.recordUserInteraction).toHaveBeenCalled();
  });

  it('cancels the SSE stream on unmount', () => {
    const { unmount } = renderHook(() => useChat());
    h.cancel.mockClear();

    unmount();

    expect(h.cancel).toHaveBeenCalledTimes(1);
  });

  it('refuses to send without an authenticated user', async () => {
    h.user = null;
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('anonyme');
    });

    expect(h.streamChat).not.toHaveBeenCalled();
    expect(result.current.messages).toHaveLength(0);
  });

  it('forwards attachments and STT cost metadata in the request and the optimistic bubble', async () => {
    scriptStream([done()]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage(
        'vocal',
        ['att-1'],
        [
          {
            id: 'att-1',
            filename: 'photo.jpg',
            mime_type: 'image/jpeg',
            size: 10,
            content_type: 'image',
          },
        ],
        {
          stt_provider: 'elevenlabs',
          stt_cost_usd: 0.002,
          stt_cost_eur: 0.0018,
          stt_audio_duration_seconds: 3.2,
        }
      );
    });

    const request = h.streamChat.mock.calls[0][0] as Record<string, unknown>;
    expect(request).toMatchObject({
      message: 'vocal',
      user_id: 'user-1',
      attachment_ids: ['att-1'],
      stt_provider: 'elevenlabs',
      stt_cost_eur: 0.0018,
    });
    expect(result.current.messages[0]).toMatchObject({
      source: 'voice',
      sttProvider: 'elevenlabs',
      sttCostEur: 0.0018,
    });
  });

  it('sends even when the audio warmup fails (silent catch)', async () => {
    h.voice.warmupAudio.mockRejectedValueOnce(new Error('iOS locked'));
    scriptStream([done()]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('hello');
    });

    expect(h.streamChat).toHaveBeenCalledTimes(1);
  });

  it('nullifies missing STT duration fields instead of dropping them', async () => {
    scriptStream([done()]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('vocal', undefined, undefined, {
        stt_provider: 'elevenlabs',
        stt_cost_usd: null,
        stt_cost_eur: null,
      });
    });

    const request = h.streamChat.mock.calls[0][0] as Record<string, unknown>;
    expect(request.stt_audio_duration_seconds).toBeNull();
    expect(request.stt_cost_eur).toBeNull();
    expect(result.current.messages[0].sttAudioDurationSeconds).toBeNull();
  });

  it('shrinks the reported viewport when the debug panel is visible', async () => {
    scriptStream([done()]);
    const { result } = renderHook(() => useChat({ debugPanelVisible: true }));
    // Geolocation enabled but coordinates not yet acquired → context stays null.
    h.geolocation.isEnabled = true;

    await act(async () => {
      await result.current.sendMessage('test');
    });

    const request = h.streamChat.mock.calls[0][0] as {
      context: { viewport_width: number; geolocation: null };
    };
    expect(request.context.viewport_width).toBeLessThan(window.innerWidth);
    expect(request.context.geolocation).toBeNull();
  });

  it('exposes API availability through the health callback', () => {
    const { result } = renderHook(() => useChat());
    expect(result.current.apiAvailable).toBe(false);

    act(() => {
      h.onStatusChange?.(true);
    });

    expect(result.current.apiAvailable).toBe(true);
    expect(result.current.isConnected).toBe(true);
  });
});

describe('useChat — error paths', () => {
  it('onError: flushes buffered tokens then appends the localized error bubble', async () => {
    h.streamChat.mockImplementation(async (_req: unknown, onChunk: OnChunk, onError: OnError) => {
      onChunk(token('réponse partielle'));
      onError(new Error('network down'));
    });
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('test');
    });

    // The partial answer was flushed BEFORE the error transition…
    expect(result.current.messages[1].content).toBe('réponse partielle');
    // …and the error bubble is localized through i18n (the mock t echoes the
    // key) instead of leaking a hardcoded-French prefix + raw English text.
    expect(result.current.messages[2].content).toBe('errors.chat.connection_error');
    expect(result.current.isTyping).toBe(false);
    expect(result.current.isConnected).toBe(false);
  });

  it('onError: resolves the i18n key carried by a ChatStreamError (typed HTTP errors)', async () => {
    const { ChatStreamError } =
      await vi.importActual<typeof import('@/lib/api/chat')>('@/lib/api/chat');
    h.streamChat.mockImplementation(async (_req: unknown, _onChunk: OnChunk, onError: OnError) => {
      onError(
        new ChatStreamError(
          'UsageLimitExceededError',
          'errors.chat.usage_limit_exceeded',
          'You have reached your usage limit.'
        )
      );
    });
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('test');
    });

    expect(result.current.messages[1].content).toBe('errors.chat.usage_limit_exceeded');
  });

  it('error chunk: renders the backend-localized error and leaves the error state', async () => {
    scriptStream([
      { type: 'error', content: 'Limite atteinte.', metadata: null } as unknown as ChatStreamChunk,
    ]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('test');
    });

    expect(result.current.messages[1]).toMatchObject({
      role: 'assistant',
      content: 'Limite atteinte.',
    });
    expect(result.current.isConnected).toBe(false);
  });

  it('streamChat rejection: transitions to the SSE error state with a localized bubble', async () => {
    h.streamChat.mockRejectedValue(new Error('fetch exploded'));
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('test');
    });

    expect(result.current.messages[1].content).toBe('errors.chat.connection_error');
    expect(result.current.isTyping).toBe(false);
  });
});

describe('useChat — HITL interrupt then resume', () => {
  it('renders the streamed HITL question, then resumes into the final answer on approval', async () => {
    // Turn 1: the plan hits a HITL gate — question streamed progressively.
    scriptStream([
      ROUTER_CHUNK,
      {
        type: 'hitl_interrupt_metadata',
        content: '',
        metadata: {
          message_id: 'hitl_run1',
          action_requests: [{ name: 'send_email_tool', args: {} }],
        },
      } as ChatStreamChunk,
      {
        type: 'hitl_question_token',
        content: 'Confirmez-vous ',
        metadata: { message_id: 'hitl_run1' },
      } as ChatStreamChunk,
      {
        type: 'hitl_question_token',
        content: "l'envoi ?",
        metadata: { message_id: 'hitl_run1' },
      } as ChatStreamChunk,
      {
        type: 'hitl_interrupt_complete',
        content: '',
        metadata: { message_id: 'hitl_run1' },
      } as ChatStreamChunk,
    ]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('Envoie le mail à Alice');
    });

    expect(result.current.messages).toHaveLength(2);
    const hitlBubble = result.current.messages[1];
    // The router created the progress bubble first, so the HITL flow MORPHS
    // that bubble in place: its id stays the frontend assistant UUID, not the
    // backend message_id (that id is only used when no progress bubble exists).
    expect(hitlBubble.id).not.toBe('hitl_run1');
    expect(hitlBubble.role).toBe('assistant');
    expect(hitlBubble.content).toBe("Confirmez-vous l'envoi ?");
    // Input unlocked so the user can answer the approval question.
    expect(result.current.isTyping).toBe(false);
    // No token metadata on the HITL bubble (attached on final done only).
    expect(hitlBubble.tokensIn).toBeUndefined();

    // Turn 2: the user approves — same endpoint, backend resumes the graph.
    scriptStream([
      token('Email envoyé ✅'),
      done({ tokens_in: 50, tokens_out: 20, message_count: 2 }),
    ]);

    await act(async () => {
      await result.current.sendMessage('oui');
    });

    expect(h.streamChat).toHaveBeenCalledTimes(2);
    expect(result.current.messages).toHaveLength(4);
    expect(result.current.messages[2]).toMatchObject({ role: 'user', content: 'oui' });
    expect(result.current.messages[3]).toMatchObject({
      role: 'assistant',
      content: 'Email envoyé ✅',
      tokensIn: 50,
    });
    expect(result.current.conversationTotals.totalTokensIn).toBe(50);
  });
});

describe('useChat — geolocation interception', () => {
  it('prompts for geolocation when the message needs it and permission is undecided', async () => {
    h.requiresGeolocation.mockReturnValue(true);
    scriptStream([done()]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('quel temps fait-il dans le coin ?');
    });

    expect(toast.info).toHaveBeenCalledWith('chat.geolocation.prompt_title', expect.any(Object));
    expect(h.geolocation.enable).toHaveBeenCalledTimes(1);
    // The message is NOT blocked on the permission — it goes out immediately.
    expect(h.streamChat).toHaveBeenCalledTimes(1);
  });

  it('confirms with a toast only when the permission is actually granted', async () => {
    h.requiresGeolocation.mockReturnValue(true);
    scriptStream([done()]);

    // Denied by the user → no success toast.
    h.geolocation.enable.mockResolvedValueOnce(false);
    const { result } = renderHook(() => useChat());
    await act(async () => {
      await result.current.sendMessage('autour de moi');
    });
    expect(toast.success).not.toHaveBeenCalled();

    // Granted → success toast.
    h.geolocation.enable.mockResolvedValueOnce(true);
    await act(async () => {
      await result.current.sendMessage('autour de moi encore');
    });
    expect(toast.success).toHaveBeenCalledWith('chat.geolocation.enabled_success');
  });

  it('does not prompt when permission was already denied', async () => {
    h.requiresGeolocation.mockReturnValue(true);
    h.geolocation.permission = 'denied';
    scriptStream([done()]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('autour de moi ?');
    });

    expect(toast.info).not.toHaveBeenCalled();
    expect(h.geolocation.enable).not.toHaveBeenCalled();
  });

  it('sends the coordinates in the browser context once geolocation is active', async () => {
    h.geolocation.coordinates = { lat: 48.85, lon: 2.35, accuracy: 12, timestamp: 1 };
    h.geolocation.isEnabled = true;
    scriptStream([done()]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('météo');
    });

    const request = h.streamChat.mock.calls[0][0] as {
      context: { geolocation: { lat: number; lon: number } | null; lia_gender: string };
    };
    expect(request.context.geolocation).toMatchObject({ lat: 48.85, lon: 2.35 });
    expect(request.context.lia_gender).toBe('female');
  });
});

describe('useChat — conversation management API', () => {
  it('setMessages replaces the history and ignores non-array payloads', async () => {
    const { result } = renderHook(() => useChat());
    const history = [
      { id: 'm-1', role: 'user' as const, content: 'q', timestamp: new Date() },
      { id: 'm-2', role: 'assistant' as const, content: 'r', timestamp: new Date() },
    ];

    act(() => {
      result.current.setMessages(history);
    });
    expect(result.current.messages).toEqual(history);

    act(() => {
      result.current.setMessages('corrompu' as unknown as typeof history);
    });
    expect(result.current.messages).toEqual(history); // untouched
  });

  it('appendMessage adds a message and deduplicates by id', () => {
    const { result } = renderHook(() => useChat());
    const notif = {
      id: 'notif-1',
      role: 'assistant' as const,
      content: 'rappel',
      timestamp: new Date(),
    };

    act(() => {
      result.current.appendMessage(notif);
      result.current.appendMessage({ ...notif, content: 'doublon' });
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].content).toBe('rappel');
  });

  it('clearMessages wipes the conversation and the totals', async () => {
    scriptStream([token('x'), done({ tokens_in: 9, message_count: 2 })]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('salut');
    });
    expect(result.current.messages.length).toBeGreaterThan(0);

    act(() => {
      result.current.clearMessages();
    });

    expect(result.current.messages).toEqual([]);
    expect(result.current.conversationTotals.totalTokensIn).toBe(0);
  });

  it('exposes registry items received through registry_update side-channel', async () => {
    const item = {
      id: 'contact_1',
      type: 'CONTACT',
      payload: { name: 'Alice' },
      meta: { source: 'google_contacts', timestamp: '2026-07-09T00:00:00Z' },
    };
    scriptStream([
      {
        type: 'registry_update',
        content: '',
        metadata: { items: { contact_1: item }, count: 1 },
      } as ChatStreamChunk,
      token('ok'),
      done(),
    ]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('cherche Alice');
    });

    expect(result.current.registry.contact_1).toEqual(item);
    expect(result.current.getRegistryItem('contact_1')).toEqual(item);
    expect(result.current.getRegistryItem('ghost')).toBeUndefined();
  });

  it('exposes and clears the browser screenshot overlay', async () => {
    const screenshot = { image_base64: 'anBn', url: 'https://x', title: 't' };
    // No `done` in the script: the stream is still browsing — the overlay
    // must be visible (done clears it as part of stream finalization).
    scriptStream([
      { type: 'browser_screenshot', content: screenshot as unknown as string } as ChatStreamChunk,
    ]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage('va sur example.com');
    });
    expect(result.current.browserScreenshot).toEqual(screenshot);

    act(() => {
      result.current.clearBrowserScreenshot();
    });
    expect(result.current.browserScreenshot).toBeNull();
  });

  it('stops voice playback on click, double-tap and tab-hide interactions', () => {
    renderHook(() => useChat());
    h.voice.stopPlayback.mockClear();

    // Desktop: single click interrupts playback.
    act(() => {
      document.dispatchEvent(new Event('click'));
    });
    expect(h.voice.stopPlayback).toHaveBeenCalledTimes(1);

    // Mobile: single tap does NOT interrupt; double tap does.
    act(() => {
      document.dispatchEvent(new Event('touchstart'));
    });
    expect(h.voice.stopPlayback).toHaveBeenCalledTimes(1);
    act(() => {
      document.dispatchEvent(new Event('touchstart'));
    });
    expect(h.voice.stopPlayback).toHaveBeenCalledTimes(2);

    // Tab visible again: visibilitychange does NOT stop playback.
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(h.voice.stopPlayback).toHaveBeenCalledTimes(2);

    // Tab hidden: playback stops.
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(h.voice.stopPlayback).toHaveBeenCalledTimes(3);
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
  });

  it('hydrateContextUsage seeds the pill and rejects invalid values', () => {
    const { result } = renderHook(() => useChat());

    act(() => {
      result.current.hydrateContextUsage(4_000, 16_000);
    });
    expect(result.current.contextUsage).toMatchObject({ tokens: 4_000, threshold: 16_000 });
    expect(result.current.contextUsage!.ratio).toBeCloseTo(0.25, 5);

    act(() => {
      result.current.hydrateContextUsage(1_000, 0); // invalid threshold → no-op
    });
    expect(result.current.contextUsage).toMatchObject({ tokens: 4_000 });

    act(() => {
      result.current.hydrateContextUsage(null, 16_000); // missing tokens → no-op
    });
    expect(result.current.contextUsage).toMatchObject({ tokens: 4_000 });
  });
});
