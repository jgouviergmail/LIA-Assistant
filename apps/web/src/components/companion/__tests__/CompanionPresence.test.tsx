/**
 * CompanionPresence — the floating avatar that follows the user across the
 * dashboard. Beyond the pure helpers (covered in `companion-presence.test.ts`),
 * this pins the live wiring:
 *
 *  - it is absent when logged out and on the chat page — and while absent it
 *    must also **switch its SSE subscription and its polling off**, otherwise
 *    two notification connections would run at once;
 *  - only the counted notification types feed the badge, which is cleared the
 *    moment the user reaches the chat;
 *  - the active-run poll is cancelled on dismiss and on unmount.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen, act, waitFor } from '@/__tests__/test-utils';
import { usePsycheStore } from '@/stores/psycheStore';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import { useCompanionActivityStore } from '@/stores/companionActivityStore';
import type { NotificationType } from '@/hooks/useNotifications';

const { push, pathname } = vi.hoisted(() => ({
  push: vi.fn(),
  pathname: { value: '/fr/dashboard' },
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  usePathname: () => pathname.value,
}));

interface NotificationsArgs {
  isAuthenticated: boolean;
  enableSSE: boolean;
  onNotification?: (n: { type: NotificationType }) => void;
}
const { notifications } = vi.hoisted(() => ({
  notifications: { calls: [] as NotificationsArgs[] },
}));
vi.mock('@/hooks/useNotifications', () => ({
  useNotifications: (args: NotificationsArgs) => {
    notifications.calls.push(args);
    return {};
  },
}));

const { fetchActiveRun } = vi.hoisted(() => ({ fetchActiveRun: vi.fn() }));
vi.mock('@/lib/api/chat', () => ({ fetchActiveRun }));

import { CompanionPresence } from '../CompanionPresence';

const AVATAR = 'companion.open_chat';
const MINIMIZE = 'companion.minimize';
const RESTORE = 'companion.restore';

/** Fires an SSE notification through the callback the companion registered. */
async function notify(type: NotificationType) {
  const last = notifications.calls[notifications.calls.length - 1];
  await act(async () => {
    last.onNotification?.({ type });
  });
}

function render(isAuthenticated = true) {
  return renderWithProviders(<CompanionPresence isAuthenticated={isAuthenticated} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  notifications.calls = [];
  pathname.value = '/fr/dashboard';
  usePsycheStore.getState().reset();
  useEyesSignalsStore.getState().reset();
  fetchActiveRun.mockResolvedValue({ active: false });
});

afterEach(() => vi.useRealTimers());

describe('CompanionPresence — visibility', () => {
  it('keeps reception alive in the world while showing its shortcut only when attention is needed', async () => {
    renderWithProviders(<CompanionPresence isAuthenticated attentionOnly />);
    await waitFor(() => expect(fetchActiveRun).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: AVATAR })).not.toBeInTheDocument();
    expect(notifications.calls.at(-1)?.enableSSE).toBe(true);
    await notify('reminder');
    expect(await screen.findByRole('button', { name: 'companion.aria_state' })).toBeVisible();
  });
  it('stays away while the user is logged out', async () => {
    render(false);
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: AVATAR })).not.toBeInTheDocument()
    );
    const last = notifications.calls[notifications.calls.length - 1];
    expect(last.isAuthenticated).toBe(false);
    expect(last.enableSSE).toBe(false);
  });

  it('yields the floor to the chat page, subscription included', async () => {
    pathname.value = '/fr/dashboard/chat';
    render();
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: AVATAR })).not.toBeInTheDocument()
    );
    const last = notifications.calls[notifications.calls.length - 1];
    expect(last.enableSSE).toBe(false);
    expect(fetchActiveRun).not.toHaveBeenCalled();
  });

  it('shows up on the other dashboard pages', async () => {
    render();
    expect(await screen.findByRole('button', { name: AVATAR })).toBeInTheDocument();
  });
});

describe('CompanionPresence — notification badge', () => {
  it('records a real notification ping for the application companion', async () => {
    render();
    await screen.findByRole('button', { name: AVATAR });
    expect(useEyesSignalsStore.getState().notificationAt).toBeNull();

    await notify('reminder');

    expect(useEyesSignalsStore.getState().isNotificationLive(Date.now())).toBe(true);
    await notify('system');
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('counts a proactive notification and announces the total', async () => {
    render();
    await screen.findByRole('button', { name: AVATAR });

    await notify('proactive_interest');

    expect(await screen.findByText('1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'companion.aria_state' })).toBeInTheDocument();
  });

  it('ignores the notification types that are not meant to be counted', async () => {
    render();
    await screen.findByRole('button', { name: AVATAR });

    await notify('system');

    expect(screen.queryByText('1')).not.toBeInTheDocument();
  });

  it('caps the badge at 9+', async () => {
    render();
    await screen.findByRole('button', { name: AVATAR });

    for (let i = 0; i < 11; i++) await notify('reminder');

    expect(await screen.findByText('9+')).toBeInTheDocument();
  });

  it('clears the badge when the user opens the chat from the companion', async () => {
    const { user } = render();
    await screen.findByRole('button', { name: AVATAR });
    await notify('scheduled_action');

    await user.click(screen.getByRole('button', { name: 'companion.aria_state' }));

    // `fr` is the default locale — the middleware serves it unprefixed.
    expect(push).toHaveBeenCalledWith('/dashboard/chat');
    await waitFor(() => expect(screen.queryByText('1')).not.toBeInTheDocument());
  });

  it('keeps the locale prefix when the user browses a non-default language', async () => {
    pathname.value = '/en/dashboard/settings';
    const { user } = render();

    await user.click(await screen.findByRole('button', { name: AVATAR }));

    expect(push).toHaveBeenCalledWith('/en/dashboard/chat');
  });
});

describe('CompanionPresence — application action mode', () => {
  it('keeps the badge and keyboard chat access without rendering a second face', async () => {
    const { user } = renderWithProviders(
      <CompanionPresence isAuthenticated renderAvatar={false} />
    );
    const button = await screen.findByRole('button', { name: AVATAR });
    expect(button.querySelector('img')).toBeNull();
    expect(button.querySelector('.lia-eyes')).toBeNull();
    expect(button.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');

    await notify('scheduled_action');
    expect(screen.getByText('1')).toBeInTheDocument();
    const notified = screen.getByRole('button', { name: 'companion.aria_state' });
    notified.focus();
    await user.keyboard('{Enter}');
    expect(push).toHaveBeenCalledWith('/dashboard/chat');
    expect(screen.queryByText('1')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: MINIMIZE }));
    expect(screen.getByRole('button', { name: RESTORE })).toBeInTheDocument();
    expect(notifications.calls.at(-1)?.enableSSE).toBe(false);
    await user.click(screen.getByRole('button', { name: RESTORE }));
    expect(screen.getByRole('button', { name: AVATAR }).querySelector('img')).toBeNull();
    expect(notifications.calls.at(-1)?.enableSSE).toBe(true);
  });

  it('reports working edges and resets when the chat takes ownership', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fetchActiveRun.mockResolvedValue({ active: true });
    const onWorkingChange = vi.fn<(working: boolean) => void>();
    const { rerender } = renderWithProviders(
      <CompanionPresence isAuthenticated renderAvatar={false} onWorkingChange={onWorkingChange} />
    );
    await waitFor(() => expect(onWorkingChange.mock.calls).toEqual([[false], [true]]));

    await act(async () => void vi.advanceTimersByTime(6_000));
    expect(fetchActiveRun).toHaveBeenCalledTimes(2);
    expect(onWorkingChange.mock.calls).toEqual([[false], [true]]);

    pathname.value = '/fr/dashboard/chat';
    rerender(
      <CompanionPresence isAuthenticated renderAvatar={false} onWorkingChange={onWorkingChange} />
    );
    await waitFor(() => expect(onWorkingChange.mock.calls).toEqual([[false], [true], [false]]));
    expect(notifications.calls.at(-1)?.enableSSE).toBe(false);
  });

  it('releases a working signal on unmount without leaving the poll alive', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fetchActiveRun.mockResolvedValue({ active: true });
    const onWorkingChange = vi.fn<(working: boolean) => void>();
    const { unmount } = renderWithProviders(
      <CompanionPresence isAuthenticated renderAvatar={false} onWorkingChange={onWorkingChange} />
    );
    await waitFor(() => expect(onWorkingChange).toHaveBeenLastCalledWith(true));

    unmount();
    expect(onWorkingChange).toHaveBeenLastCalledWith(false);
    const calls = onWorkingChange.mock.calls.length;
    await act(async () => void vi.advanceTimersByTime(30_000));
    expect(fetchActiveRun).toHaveBeenCalledTimes(1);
    expect(onWorkingChange).toHaveBeenCalledTimes(calls);
  });
});

describe('CompanionPresence — minimize', () => {
  it('collapses to a restore dot and comes back on demand', async () => {
    const { user } = render();
    await screen.findByRole('button', { name: AVATAR });

    await user.click(screen.getByRole('button', { name: MINIMIZE }));
    expect(await screen.findByRole('button', { name: RESTORE })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: AVATAR })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: RESTORE }));
    expect(await screen.findByRole('button', { name: AVATAR })).toBeInTheDocument();
  });

  it('stops watching for runs while minimized', async () => {
    const { user } = render();
    await screen.findByRole('button', { name: AVATAR });
    await waitFor(() => expect(fetchActiveRun).toHaveBeenCalled());

    await user.click(screen.getByRole('button', { name: MINIMIZE }));
    fetchActiveRun.mockClear();

    // The poll interval is torn down with the effect, so time passing changes
    // nothing while the companion is out of the way.
    await new Promise(resolve => setTimeout(resolve, 20));
    expect(fetchActiveRun).not.toHaveBeenCalled();
  });
});

describe('CompanionPresence — working state', () => {
  it('shows the thinking bubble while a background run is active', async () => {
    fetchActiveRun.mockResolvedValue({ active: true, stream_id: 's-1' });
    render();
    expect(await screen.findByRole('status')).toBeInTheDocument();
  });

  it('keeps the previous state when the check fails (transient error)', async () => {
    fetchActiveRun.mockRejectedValue(new Error('offline'));
    render();
    await screen.findByRole('button', { name: AVATAR });
    await waitFor(() => expect(fetchActiveRun).toHaveBeenCalled());
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('polls again on the next tick and stops once unmounted', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { unmount } = render();
    await waitFor(() => expect(fetchActiveRun).toHaveBeenCalledTimes(1));

    await act(async () => void vi.advanceTimersByTime(6_000));
    expect(fetchActiveRun).toHaveBeenCalledTimes(2);

    unmount();
    await act(async () => void vi.advanceTimersByTime(30_000));
    expect(fetchActiveRun).toHaveBeenCalledTimes(2);
  });
});

it('keeps owned SMS reception alive when its avatar is minimized', async () => {
  const { user } = renderWithProviders(
    <CompanionPresence isAuthenticated ownerId="owner" smsEnabled renderAvatar={false} />
  );
  await screen.findByRole('button', { name: AVATAR });
  await user.click(screen.getByRole('button', { name: MINIMIZE }));
  expect(notifications.calls.at(-1)?.enableSSE).toBe(true);
});

it('publishes fresh owner samples from its existing single poll and rejects a late result after disposal', async () => {
  vi.useFakeTimers();
  vi.setSystemTime(1000);
  useCompanionActivityStore.getState().bindOwner('owner');
  fetchActiveRun.mockResolvedValue({ active: true });
  const view = renderWithProviders(<CompanionPresence isAuthenticated ownerId="owner" />);
  await act(async () => {});
  expect(fetchActiveRun).toHaveBeenCalledTimes(1);
  expect(useCompanionActivityStore.getState().sample).toEqual({ working: true, at: 1000 });
  await act(async () => vi.advanceTimersByTimeAsync(6000));
  expect(fetchActiveRun).toHaveBeenCalledTimes(2);
  expect(useCompanionActivityStore.getState().sample).toEqual({ working: true, at: 7000 });
  const pending = Promise.withResolvers<{ active: boolean }>();
  fetchActiveRun.mockReturnValueOnce(pending.promise);
  await act(async () => vi.advanceTimersByTimeAsync(6000));
  expect(fetchActiveRun).toHaveBeenCalledTimes(3);
  view.unmount();
  expect(useCompanionActivityStore.getState().sample).toBeNull();
  await act(async () => pending.resolve({ active: true }));
  expect(useCompanionActivityStore.getState().sample).toBeNull();
  useCompanionActivityStore.getState().bindOwner(null);
});
