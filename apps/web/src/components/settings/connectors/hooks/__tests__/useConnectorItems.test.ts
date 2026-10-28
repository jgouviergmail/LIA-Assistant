/**
 * useConnectorItems — the calendars or task lists a preference picker offers.
 *
 * The read belongs to the picker's lifetime, transport included: the retry
 * supersedes a read still in flight (whose late answer is dropped), and an
 * unmount aborts the request rather than only ignoring its answer.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderHook, act, waitFor } from '@/__tests__/test-utils';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));

import { useConnectorItems } from '../useConnectorItems';

interface CalendarAnswer {
  items: { name: string; is_default: boolean; access_role: string }[];
}

let answers: ((body: CalendarAnswer) => void)[];

function signalOf(call: number): AbortSignal {
  const [, config] = get.mock.calls[call] as [string, { signal: AbortSignal }];
  return config.signal;
}

beforeEach(() => {
  answers = [];
  get.mockReset();
  get.mockImplementation(() => new Promise<CalendarAnswer>(resolve => answers.push(resolve)));
});

describe('useConnectorItems — read lifetime', () => {
  it('reads the calendars of a calendar connector with its lifetime signal', async () => {
    const { result } = renderHook(() => useConnectorItems('c-1', 'google_calendar'));
    await waitFor(() => expect(answers).toHaveLength(1));

    expect(get).toHaveBeenCalledWith('/connectors/c-1/calendars', {
      signal: expect.any(AbortSignal),
    });
    await act(async () =>
      answers[0]({ items: [{ name: 'Work', is_default: true, access_role: 'owner' }] })
    );
    expect(result.current.items).toEqual([{ name: 'Work', isDefault: true, accessRole: 'owner' }]);
    expect(result.current.loading).toBe(false);
  });

  it('lets the retry supersede the read in flight, whose late answer is dropped', async () => {
    const { result } = renderHook(() => useConnectorItems('c-1', 'google_calendar'));
    await waitFor(() => expect(answers).toHaveLength(1));

    act(() => result.current.refetch());

    await waitFor(() => expect(answers).toHaveLength(2));
    expect(signalOf(0).aborted).toBe(true);
    await act(async () =>
      answers[1]({ items: [{ name: 'Fresh', is_default: false, access_role: 'writer' }] })
    );
    await act(async () =>
      answers[0]({ items: [{ name: 'Stale', is_default: true, access_role: 'owner' }] })
    );
    expect(result.current.items.map(item => item.name)).toEqual(['Fresh']);
    expect(result.current.loading).toBe(false);
  });

  it('aborts the request in flight when the picker unmounts', async () => {
    const { unmount } = renderHook(() => useConnectorItems('c-1', 'google_tasks'));
    await waitFor(() => expect(answers).toHaveLength(1));
    expect(get).toHaveBeenCalledWith('/connectors/c-1/task-lists', {
      signal: expect.any(AbortSignal),
    });
    expect(signalOf(0).aborted).toBe(false);

    unmount();

    expect(signalOf(0).aborted).toBe(true);
  });
});
