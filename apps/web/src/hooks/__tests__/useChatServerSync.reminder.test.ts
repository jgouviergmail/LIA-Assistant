/**
 * A reminder that rings on the open page offers its short « later » in its toast
 * (ADR-268 amendment 2026-11-16). Read from the real catalogues, in English and
 * French: the label is the configured delay, the verdict is dated on the
 * account's wall, and the handler's identity never moves (the notification
 * stream reopens when it does, and loses what was published meanwhile).
 */

import { act, renderHook } from '@testing-library/react';
import { createInstance } from 'i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { UseChatServerSyncOptions } from '@/hooks/useChatServerSync';
import type { UseNotificationsOptions } from '@/hooks/useNotifications';
import { resetFiringVerdicts } from '@/lib/reminder-firing';
import en from '../../../locales/en/translation.json';
import fr from '../../../locales/fr/translation.json';

const language = createInstance();
await language.init({ lng: 'en', resources: { en: { translation: en }, fr: { translation: fr } } });
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: language.t, i18n: language }) }));

// Stable, as the real hook's are: a fresh spy per render would move every
// handler built on it and hide what this file pins.
const conversationSync = vi.hoisted(() => ({ requestSync: vi.fn(), requestReset: vi.fn() }));
vi.mock('@/hooks/useConversationSync', () => ({
  useConversationSync: () => conversationSync,
}));

const notificationOptions = vi.hoisted(() => ({ last: null as UseNotificationsOptions | null }));
vi.mock('@/hooks/useNotifications', () => ({
  useNotifications: (options: UseNotificationsOptions) => {
    notificationOptions.last = options;
    return {};
  },
}));

const { mutate } = vi.hoisted(() => ({
  mutate: vi.fn(async (_endpoint: string, _data?: unknown): Promise<unknown> => undefined),
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate, loading: false, error: null, reset: vi.fn(), data: null }),
}));

interface ToastOptions {
  duration?: number;
  description?: string;
  action?: { label: string; onClick: () => void };
}
const toast = vi.hoisted(() => ({
  info: vi.fn<(title: string, options?: ToastOptions) => void>(),
  success: vi.fn<(title: string) => void>(),
  error: vi.fn<(title: string) => void>(),
}));
vi.mock('sonner', () => ({ toast }));

import { useChatServerSync } from '@/hooks/useChatServerSync';

function options(overrides: Partial<UseChatServerSyncOptions> = {}): UseChatServerSyncOptions {
  return {
    owner: { id: 'owner-a', timezone: 'Asia/Tokyo' },
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
    discussionTitle: () => 'Main',
    ...overrides,
  };
}

const handlers = () => notificationOptions.last as UseNotificationsOptions;
const shown = (): ToastOptions => toast.info.mock.calls.at(-1)?.[1] ?? {};
const OFFER = { firingId: 'firing-1', shortMinutes: 10 };

beforeEach(async () => {
  vi.clearAllMocks();
  resetFiringVerdicts();
  await language.changeLanguage('en');
});

describe('the toast of a reminder that rang', () => {
  it('offers the short delay and stays long enough to be pressed', () => {
    renderHook(() => useChatServerSync(options()));

    handlers().onReminder?.('Call the bank', 'reminder-1', OFFER);

    expect(shown().action?.label).toBe('In 10 min');
    expect(shown().duration).toBe(10_000);
  });

  it('says a whole hour in hours, in the reader’s language', async () => {
    await language.changeLanguage('fr');
    renderHook(() => useChatServerSync(options()));

    handlers().onReminder?.('Appeler la banque', 'reminder-1', { ...OFFER, shortMinutes: 60 });

    expect(shown().action?.label).toBe('Dans 1 h');
  });

  it('offers nothing when the occurrence was not recorded', () => {
    renderHook(() => useChatServerSync(options()));

    handlers().onReminder?.('Call the bank', 'reminder-1');

    expect(shown().action).toBeUndefined();
    expect(shown().duration).toBe(5000);
  });

  it('seen from an annex, it opens Main, whose bubble offers every delay', () => {
    renderHook(() =>
      useChatServerSync(
        options({
          isMain: false,
          conversationId: 'annex-1',
          selection: { conversation_id: 'annex-1', conversation_revision: 1 },
          openDiscussion: vi.fn(),
        })
      )
    );

    handlers().onReminder?.('Call the bank', 'reminder-1', OFFER);

    expect(shown().action?.label).toBe(en.chat.discussions.notification_open);
  });

  it('a press postpones the occurrence and says until when, on the account’s wall', async () => {
    mutate.mockResolvedValueOnce({
      outcome: 'snoozed',
      snoozed_until: '2026-11-17T00:00:00Z',
      next_occurrence_at: null,
    });
    renderHook(() => useChatServerSync(options()));
    handlers().onReminder?.('Call the bank', 'reminder-1', OFFER);

    await act(async () => {
      shown().action?.onClick();
    });

    expect(mutate).toHaveBeenCalledWith('/reminders/firings/firing-1/snooze', {
      choice: 'short',
      surface: 'chat',
    });
    await vi.waitFor(() => expect(toast.success).toHaveBeenCalledOnce());
    expect(toast.success.mock.calls[0][0]).toMatch(/^Postponed to .*9:00/);
  });

  it('a press that cannot be made is said', async () => {
    mutate.mockRejectedValueOnce(new Error('offline'));
    renderHook(() => useChatServerSync(options()));
    handlers().onReminder?.('Call the bank', 'reminder-1', OFFER);

    await act(async () => {
      shown().action?.onClick();
    });

    await vi.waitFor(() => expect(toast.error).toHaveBeenCalledWith(en.reminders.firing.failed));
  });

  it('keeps the handler identity across renders', () => {
    const { rerender } = renderHook((props: UseChatServerSyncOptions) => useChatServerSync(props), {
      initialProps: options(),
    });
    const first = handlers().onReminder;

    rerender(options({ owner: { id: 'owner-a', timezone: 'Europe/Paris' } }));

    expect(handlers().onReminder).toBe(first);
  });
});
