/**
 * What the mailbox leaves unread (ADR-369, lot 4).
 *
 * The figures are polled while the page is seen, read at once when it comes back, and
 * a read state moves them on the spot. What the provider refuses leaves the last ones.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn() } }));

vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { MAIL_COUNTS_EVERY_MS, useMailCounts } from '../useMailCounts';

const COUNTS = { counts: { 'system:inbox': 3, Projets: 1 }, truncated: false };

function setVisibility(state: DocumentVisibilityState): void {
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: state });
  document.dispatchEvent(new Event('visibilitychange'));
}

async function rendered(enabled = true) {
  const view = renderHook(() => useMailCounts(enabled));
  if (enabled) await waitFor(() => expect(view.result.current.counts).toBeDefined());
  return view;
}

describe('useMailCounts', () => {
  beforeEach(() => {
    api.get.mockReset();
    api.get.mockResolvedValue(COUNTS);
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('reads nothing while no mail provider is ready', async () => {
    const { result } = await rendered(false);

    expect(api.get).not.toHaveBeenCalled();
    expect(result.current.counts).toBeUndefined();
  });

  it('reads the figures, and again after its time', async () => {
    const timers = vi.spyOn(window, 'setInterval');
    await rendered();
    const [tick] = timers.mock.calls.find(([, every]) => every === MAIL_COUNTS_EVERY_MS)!;
    const before = api.get.mock.calls.length;

    await act(async () => {
      (tick as () => void)();
    });

    expect(api.get.mock.calls.length).toBe(before + 1);
    timers.mockRestore();
  });

  it('keeps one timer across renders: one rearmed by each would never ring', async () => {
    const timers = vi.spyOn(window, 'setInterval');
    const { rerender } = await rendered();

    rerender();
    rerender();

    const mine = timers.mock.calls.filter(([, every]) => every === MAIL_COUNTS_EVERY_MS);
    expect(mine).toHaveLength(1);
    timers.mockRestore();
  });

  it('asks nothing of a hidden page, and reads at once when it comes back', async () => {
    await rendered();
    const before = api.get.mock.calls.length;

    act(() => setVisibility('hidden'));
    expect(api.get.mock.calls.length).toBe(before);

    await act(async () => setVisibility('visible'));
    expect(api.get.mock.calls.length).toBe(before + 1);
  });

  it('moves one figure on the spot, never below zero', async () => {
    const { result } = await rendered();

    act(() => result.current.adjust('system:inbox', -1));
    expect(result.current.counts?.['system:inbox']).toBe(2);

    act(() => result.current.adjust('Projets', -5));
    expect(result.current.counts?.Projets).toBe(0);
  });

  it('leaves alone a figure it never read', async () => {
    const { result } = await rendered();

    act(() => result.current.adjust('system:starred', 1));

    expect(result.current.counts?.['system:starred']).toBeUndefined();
  });

  it('keeps the last figures when a reading fails', async () => {
    const { result } = await rendered();
    api.get.mockRejectedValueOnce(new Error('gone'));

    await act(async () => result.current.reread());

    expect(result.current.counts?.['system:inbox']).toBe(3);
  });

  it('stops asking when it leaves the screen', async () => {
    const stopped = vi.spyOn(window, 'clearInterval');
    const { unmount } = await rendered();

    unmount();

    expect(stopped).toHaveBeenCalled();
    stopped.mockRestore();
  });
});
