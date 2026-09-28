/**
 * useChatServerSync — what keeps the chat in step with elsewhere (ADR-320).
 *
 * The behaviour this pins changed on purpose: a reminder, a proactive
 * notification or a routine used to BUILD a bubble here (under an id no row
 * carries — it came back a second time at the next read) or to REPLACE the
 * whole list. Each now keeps its toast and asks for a sync; the message reaches
 * the thread as the row the server archived.
 */

import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { UseChatServerSyncOptions } from '@/hooks/useChatServerSync';
import type { UseNotificationsOptions } from '@/hooks/useNotifications';

const requestSync = vi.fn();
const requestReset = vi.fn();
const syncOptions = vi.hoisted(() => ({ last: null as Record<string, unknown> | null }));
vi.mock('@/hooks/useConversationSync', () => ({
  useConversationSync: (options: Record<string, unknown>) => {
    syncOptions.last = options;
    return { requestSync, requestReset };
  },
}));

const notificationOptions = vi.hoisted(() => ({ last: null as UseNotificationsOptions | null }));
vi.mock('@/hooks/useNotifications', () => ({
  useNotifications: (options: UseNotificationsOptions) => {
    notificationOptions.last = options;
    return {};
  },
}));

const toast = vi.hoisted(() => ({ info: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

import { proactiveToastPresentation, useChatServerSync } from '@/hooks/useChatServerSync';

function options(overrides: Partial<UseChatServerSyncOptions> = {}): UseChatServerSyncOptions {
  return {
    signedIn: true,
    authLoading: false,
    apiAvailable: true,
    isTyping: false,
    historyView: false,
    isLoadingOlder: false,
    messages: [],
    readNewestPage: vi.fn(),
    mergeServerPage: vi.fn(),
    clearMessages: vi.fn(),
    setApiTotals: vi.fn(),
    setHasMoreOlder: vi.fn(),
    setOldestCursor: vi.fn(),
    onNotification: vi.fn(),
    ...overrides,
  };
}

const handlers = () => notificationOptions.last as UseNotificationsOptions;

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useChatServerSync — notifications keep their toast and ask for a sync', () => {
  it('a reminder builds no bubble: a toast, then the archived row through the sync', () => {
    renderHook(() => useChatServerSync(options()));

    handlers().onReminder?.('<p>Appeler Marie</p>', 'r1');

    expect(toast.info).toHaveBeenCalledWith('Appeler Marie', { duration: 5000 });
    expect(requestSync).toHaveBeenCalledWith('notification');
  });

  it('a proactive notification and a routine result do the same', () => {
    renderHook(() => useChatServerSync(options()));

    handlers().onProactiveNotification?.('Du nouveau', 'target', { interest_topic: 'Jardin' });
    handlers().onScheduledAction?.('Résumé du matin', 'a1', 'Briefing');

    expect(toast.info).toHaveBeenCalledTimes(2);
    expect(requestSync).toHaveBeenCalledTimes(2);
  });

  it('a relayed live turn says its sentence and syncs (ADR-301)', () => {
    renderHook(() => useChatServerSync(options()));

    handlers().onProactiveNotification?.('Ta session est dans le fil', 't', {
      event: 'live_relay',
    });

    expect(toast.info).toHaveBeenCalledWith('Ta session est dans le fil', { duration: 5000 });
    expect(requestSync).toHaveBeenCalledWith('notification');
  });
});

describe('useChatServerSync — the thread sync signals', () => {
  it('a change asks for a sync, a reset asks for a reset', () => {
    renderHook(() => useChatServerSync(options()));

    handlers().onConversationEvent?.('conversation_updated');
    handlers().onConversationEvent?.('conversation_reset');

    expect(requestSync).toHaveBeenCalledWith('signal');
    expect(requestReset).toHaveBeenCalledTimes(1);
  });

  it('a reopened stream catches up what Pub/Sub dropped', () => {
    renderHook(() => useChatServerSync(options()));

    handlers().onReconnected?.();

    expect(requestSync).toHaveBeenCalledWith('reconnected');
  });

  it('a reset empties the thread, its totals and its pagination', () => {
    const opts = options();
    renderHook(() => useChatServerSync(opts));

    (syncOptions.last?.onReset as () => void)();

    expect(opts.clearMessages).toHaveBeenCalled();
    expect(opts.setApiTotals).toHaveBeenCalledWith(null);
    expect(opts.setHasMoreOlder).toHaveBeenCalledWith(false);
    expect(opts.setOldestCursor).toHaveBeenCalledWith(null);
  });
});

describe('useChatServerSync — when the thread may be touched', () => {
  it.each([
    [{ isTyping: true }, true],
    [{ historyView: true }, true],
    [{ isLoadingOlder: true }, true],
    [{}, false],
  ])('blocked for %o → %s', (overrides, blocked) => {
    renderHook(() => useChatServerSync(options(overrides)));

    expect(syncOptions.last?.blocked).toBe(blocked);
  });

  it('syncs only for a signed-in account whose API answers', () => {
    renderHook(() => useChatServerSync(options({ apiAvailable: false })));
    expect(syncOptions.last?.enabled).toBe(false);

    renderHook(() => useChatServerSync(options({ signedIn: false })));
    expect(syncOptions.last?.enabled).toBe(false);
    expect(handlers().isAuthenticated).toBe(false);
  });
});

describe('proactiveToastPresentation', () => {
  it('tints a peer notification and names its sender', () => {
    expect(
      proactiveToastPresentation({ type: 'proactive_peer_message', sender_name: 'Claire' })
    ).toEqual({ message: '🤝 Claire', className: '!bg-primary/10 !border-primary/25' });
  });

  it('titles an interest with its topic, and falls back to a generic title', () => {
    expect(proactiveToastPresentation({ interest_topic: 'Jardin' }).message).toBe('💡 Jardin');
    expect(proactiveToastPresentation(undefined).message).toBe('💡 Info');
  });
});
