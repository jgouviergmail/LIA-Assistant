/**
 * A return named where it landed (ADR-378 amendment 2026-11-14).
 *
 * A call placed from an annex, a meeting imported there, a routine started
 * there: each return comes back to that discussion. Its toast, shown wherever
 * the person is, says where the return is when it is not the discussion on
 * screen, and offers to open it — only where leaving cancels nothing, asked
 * again at the click. Read from the real catalogues, in English and French.
 */

import { act, renderHook } from '@testing-library/react';
import { createInstance } from 'i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { UseChatServerSyncOptions } from '@/hooks/useChatServerSync';
import type { Notification, UseNotificationsOptions } from '@/hooks/useNotifications';
import en from '../../../locales/en/translation.json';
import fr from '../../../locales/fr/translation.json';

const language = createInstance();
await language.init({ lng: 'en', resources: { en: { translation: en }, fr: { translation: fr } } });
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: language.t, i18n: language }) }));

const requestSync = vi.fn();
vi.mock('@/hooks/useConversationSync', () => ({
  useConversationSync: () => ({ requestSync, requestReset: vi.fn() }),
}));

const notificationOptions = vi.hoisted(() => ({ last: null as UseNotificationsOptions | null }));
vi.mock('@/hooks/useNotifications', () => ({
  useNotifications: (options: UseNotificationsOptions) => {
    notificationOptions.last = options;
    return {};
  },
}));

interface ToastOptions {
  description?: string;
  action?: { label: string; onClick: () => void };
}
const toast = vi.hoisted(() => ({ info: vi.fn<(title: string, options: ToastOptions) => void>() }));
vi.mock('sonner', () => ({ toast }));

import { useChatServerSync } from '@/hooks/useChatServerSync';

const TITLES: Record<string, string> = { 'main-1': 'Main', 'annex-1': 'Travaux' };

function options(overrides: Partial<UseChatServerSyncOptions> = {}): UseChatServerSyncOptions {
  return {
    owner: { id: 'owner-a' },
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
    hydratePendingHitl: vi.fn(async () => {}),
    conversationId: 'main-1',
    discussionTitle: id => TITLES[id] ?? null,
    ...overrides,
  };
}

const handlers = () => notificationOptions.last as UseNotificationsOptions;
const shown = (): ToastOptions => toast.info.mock.calls.at(-1)?.[1] ?? {};
const callReturn = { type: 'proactive_phone_call', conversation_id: 'annex-1' };

beforeEach(async () => {
  vi.clearAllMocks();
  await language.changeLanguage('en');
});

describe('a return that landed in another discussion', () => {
  it('is named before its preview, and opens that discussion', () => {
    const openDiscussion = vi.fn();
    renderHook(() => useChatServerSync(options({ openDiscussion })));

    handlers().onProactiveNotification?.('<p>Il rappellera demain.</p>', 'call-1', callReturn);

    expect(shown().description).toBe('In “Travaux” · Il rappellera demain.');
    expect(shown().action?.label).toBe('Open');
    shown().action?.onClick();
    expect(openDiscussion).toHaveBeenCalledWith('annex-1');
    // The thread on screen is not the one that changed.
    expect(requestSync).not.toHaveBeenCalled();
  });

  it('is named in the reader’s language', async () => {
    await language.changeLanguage('fr');
    renderHook(() => useChatServerSync(options({ openDiscussion: vi.fn() })));

    handlers().onProactiveNotification?.('Il rappellera demain.', 'call-1', callReturn);

    expect(shown().description).toBe('Dans « Travaux » · Il rappellera demain.');
    expect(shown().action?.label).toBe('Ouvrir');
  });

  it('says « another discussion » when the catalogue on hand does not hold it', () => {
    renderHook(() => useChatServerSync(options({ discussionTitle: () => null })));

    handlers().onProactiveNotification?.('Prêt', 'meeting-1', {
      type: 'proactive_meeting',
      conversation_id: 'annex-7',
    });

    expect(shown().description).toBe('In another discussion · Prêt');
  });

  it('names a routine result the same way', () => {
    renderHook(() => useChatServerSync(options({ openDiscussion: vi.fn() })));

    handlers().onScheduledAction?.('Résumé du matin', 'a1', 'Briefing', {
      conversation_id: 'annex-1',
    });

    expect(toast.info).toHaveBeenCalledWith(
      'Briefing',
      expect.objectContaining({ description: 'In “Travaux” · Résumé du matin' })
    );
    expect(requestSync).not.toHaveBeenCalled();
  });

  it('is named without an offer to leave while leaving would cancel the turn', () => {
    renderHook(() => useChatServerSync(options({ openDiscussion: undefined })));

    handlers().onProactiveNotification?.('Fini', 'call-1', callReturn);

    expect(shown().description).toBe('In “Travaux” · Fini');
    expect(shown().action).toBeUndefined();
  });

  it('asks again at the click: a turn started since the toast keeps the person here', () => {
    const openDiscussion = vi.fn();
    const { rerender } = renderHook((props: UseChatServerSyncOptions) => useChatServerSync(props), {
      initialProps: options({ openDiscussion }),
    });
    handlers().onProactiveNotification?.('Fini', 'call-1', callReturn);
    const offered = shown().action;

    rerender(options({ openDiscussion: undefined, isTyping: true }));
    act(() => offered?.onClick());

    expect(openDiscussion).not.toHaveBeenCalled();
  });
});

describe('a return that landed on screen', () => {
  it('keeps its plain toast and syncs the thread', () => {
    renderHook(() =>
      useChatServerSync(
        options({
          selection: { conversation_id: 'annex-1', conversation_revision: 2 },
          isMain: false,
          openDiscussion: vi.fn(),
        })
      )
    );

    handlers().onProactiveNotification?.('Fini', 'call-1', callReturn);

    expect(shown().description).toBe('Fini');
    expect(shown().action).toBeUndefined();
    expect(requestSync).toHaveBeenCalledWith('notification');
  });

  it('names Main for a notification naming no discussion, seen from an annex', () => {
    const openDiscussion = vi.fn();
    renderHook(() =>
      useChatServerSync(
        options({
          selection: { conversation_id: 'annex-1', conversation_revision: 2 },
          isMain: false,
          openDiscussion,
        })
      )
    );

    handlers().onProactiveNotification?.('Rappel du dentiste', 'hb-1', {
      type: 'proactive_heartbeat',
    });

    expect(shown().description).toBe('In “Main” · Rappel du dentiste');
    shown().action?.onClick();
    expect(openDiscussion).toHaveBeenCalledWith(null);
    // Main changed, not the annex on screen.
    expect(requestSync).not.toHaveBeenCalled();
  });

  it('names Main for a reminder seen from an annex, in the reader’s language', async () => {
    await language.changeLanguage('fr');
    renderHook(() =>
      useChatServerSync(
        options({
          selection: { conversation_id: 'annex-1', conversation_revision: 2 },
          isMain: false,
          openDiscussion: vi.fn(),
        })
      )
    );

    handlers().onReminder?.('Appeler le garage', 'rem-1');

    expect(toast.info).toHaveBeenCalledWith(
      'Appeler le garage',
      expect.objectContaining({ description: 'Dans « Principale »' })
    );
    expect(shown().action?.label).toBe('Ouvrir');
  });

  it('keeps a reminder plain when Main is on screen', () => {
    renderHook(() => useChatServerSync(options({ openDiscussion: vi.fn() })));

    handlers().onReminder?.('Appeler le garage', 'rem-1');

    expect(shown().description).toBeUndefined();
    expect(shown().action).toBeUndefined();
  });

  it('names nothing for a return to Main seen from Main', () => {
    renderHook(() => useChatServerSync(options({ openDiscussion: vi.fn() })));

    handlers().onProactiveNotification?.('Fini', 'call-1', { type: 'proactive_phone_call' });

    expect(shown().description).toBe('Fini');
    expect(requestSync).toHaveBeenCalledWith('notification');
  });
});

it('keeps every handler when a title or the leave rule changes: the stream is never rebuilt', () => {
  const { rerender } = renderHook((props: UseChatServerSyncOptions) => useChatServerSync(props), {
    initialProps: options({ openDiscussion: vi.fn() }),
  });
  const before = handlers();

  rerender(options({ discussionTitle: () => 'Renamed', openDiscussion: undefined }));

  expect(handlers().onProactiveNotification).toBe(before.onProactiveNotification);
  expect(handlers().onScheduledAction).toBe(before.onScheduledAction);
  expect(handlers().onReminder).toBe(before.onReminder);
});

describe('what the screen shows never rebuilds the stream (2026-11-15)', () => {
  // Measured in a production bundle: each new identity of a handler made
  // useNotifications close and reopen its stream — five times while the chat
  // loaded, two or three times when a turn started — and an event published
  // in between reached a closed connection and was lost.
  it('keeps every handler across a discussion switch, a turn and new callbacks', () => {
    const { rerender } = renderHook((props: UseChatServerSyncOptions) => useChatServerSync(props), {
      initialProps: options({ onCatalogueChange: vi.fn() }),
    });
    const before = handlers();

    rerender(
      options({
        selection: { conversation_id: 'annex-1', conversation_revision: 2 },
        conversationId: 'annex-1',
        isMain: false,
        isTyping: true,
        onCatalogueChange: vi.fn(),
        onNotification: vi.fn(),
      })
    );
    const after = handlers();

    expect(after.onReminder).toBe(before.onReminder);
    expect(after.onProactiveNotification).toBe(before.onProactiveNotification);
    expect(after.onScheduledAction).toBe(before.onScheduledAction);
    expect(after.onNotification).toBe(before.onNotification);
  });

  it('reads the discussion on screen when the notification lands, not when its handler was made', () => {
    const onCatalogueChange = vi.fn();
    const onNotification = vi.fn();
    const { rerender } = renderHook((props: UseChatServerSyncOptions) => useChatServerSync(props), {
      initialProps: options({ openDiscussion: vi.fn() }),
    });
    const made = handlers();
    rerender(
      options({
        selection: { conversation_id: 'annex-1', conversation_revision: 2 },
        conversationId: 'annex-1',
        isMain: false,
        openDiscussion: vi.fn(),
        onCatalogueChange,
        onNotification,
      })
    );
    const landed: Notification = {
      id: 'hb-1',
      type: 'proactive_heartbeat',
      content: 'Rappel du dentiste',
      timestamp: new Date(0),
      read: false,
    };

    act(() => {
      made.onNotification?.(landed);
      made.onProactiveNotification?.('Rappel du dentiste', 'hb-1', { type: 'proactive_heartbeat' });
    });

    // Seen from the annex now on screen: named Main, Main is not the thread shown.
    expect(shown().description).toBe('In “Main” · Rappel du dentiste');
    expect(requestSync).not.toHaveBeenCalled();
    expect(onCatalogueChange).toHaveBeenCalledTimes(1);
    expect(onNotification).toHaveBeenCalledWith(landed);
  });
});
