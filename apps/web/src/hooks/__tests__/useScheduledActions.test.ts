/**
 * useScheduledActions — the CRUD layer the settings panel sits on. Component
 * tests mock this hook out entirely, so its own contract is only pinned here:
 * the endpoint each operation targets, and above all the **optimistic cache
 * updaters** it hands to `setData`, which are what the user actually sees
 * before the next refetch lands.
 *
 * The updaters are extracted with `takeUpdater` and applied to a known cache,
 * so each one is checked as the pure function it is — including the guard that
 * makes it a no-op while the cache is still empty.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderHook, act } from '@/__tests__/test-utils';
import {
  mutateSpy,
  mutationResult,
  queryResult,
  setDataSpy,
  takeUpdater,
} from '@/__tests__/api-mocks';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));
const { useApiMutation } = vi.hoisted(() => ({ useApiMutation: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation }));

import {
  useScheduledActions,
  AUTO_REFRESH_INTERVAL_MS,
  EXECUTING_REFRESH_INTERVAL_MS,
} from '../useScheduledActions';
import type { ScheduledAction, ScheduledActionListResponse } from '@/hooks/useScheduledActions';

const ENDPOINT = '/scheduled-actions';

function action(over: Partial<ScheduledAction> = {}): ScheduledAction {
  return {
    id: 'a1',
    user_id: 'u1',
    title: 'Morning brief',
    action_prompt: 'Summarise my day',
    days_of_week: [1],
    trigger_hour: 8,
    trigger_minute: 0,
    user_timezone: 'Europe/Paris',
    next_trigger_at: '2026-07-20T06:00:00Z',
    is_enabled: true,
    status: 'active',
    last_executed_at: null,
    execution_count: 0,
    consecutive_failures: 0,
    last_error: null,
    schedule_display: 'Mon - 08:00',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  };
}

/** The five mutations, handed out in the fixed order the hook declares them. */
const mutate = {
  create: mutateSpy(),
  update: mutateSpy(),
  remove: mutateSpy(),
  toggle: mutateSpy(),
  execute: mutateSpy(),
};
const ORDER = [mutate.create, mutate.update, mutate.remove, mutate.toggle, mutate.execute];

const setData = setDataSpy<ScheduledActionListResponse>();
const refetch = vi.fn();

function cache(over: Partial<ScheduledActionListResponse> = {}): ScheduledActionListResponse {
  return { scheduled_actions: [action()], total: 1, ...over };
}

/** Explicit form: `undefined` here really means "no payload yet". */
function setupWith(data: ScheduledActionListResponse | undefined) {
  useApiQuery.mockReturnValue(queryResult<ScheduledActionListResponse>({ data, setData, refetch }));
  return renderHook(() => useScheduledActions());
}

function setup(data: ScheduledActionListResponse = cache()) {
  return setupWith(data);
}

/** Applies the updater handed to `setData` to a chosen cache state. */
function applyUpdater(previous: ScheduledActionListResponse | undefined) {
  return takeUpdater<ScheduledActionListResponse>(setData)(previous);
}

beforeEach(() => {
  vi.clearAllMocks();
  let cursor = 0;
  useApiMutation.mockImplementation(() =>
    mutationResult({ mutate: ORDER[cursor++ % ORDER.length] })
  );
  Object.values(mutate).forEach(m => m.mockResolvedValue(undefined));
});

afterEach(() => vi.useRealTimers());

describe('useScheduledActions — reading the list', () => {
  it('asks for the collection and exposes what it returns', () => {
    const { result } = setup();

    expect(useApiQuery).toHaveBeenCalledWith(ENDPOINT, expect.objectContaining({}));
    expect(result.current.actions).toHaveLength(1);
    expect(result.current.total).toBe(1);
  });

  it('degrades to an empty list rather than crashing on a missing payload', () => {
    const { result } = setupWith(undefined);

    expect(result.current.actions).toEqual([]);
    expect(result.current.total).toBe(0);
  });
});

describe('useScheduledActions — creating', () => {
  const payload = {
    title: 'Evening recap',
    action_prompt: 'Recap',
    days_of_week: [5],
    trigger_hour: 19,
    trigger_minute: 30,
  };

  it('posts to the collection and appends the created row', async () => {
    const created = action({ id: 'a2', title: 'Evening recap' });
    mutate.create.mockResolvedValue(created);
    const { result } = setup();

    await act(async () => {
      await result.current.createAction(payload);
    });

    expect(mutate.create).toHaveBeenCalledWith(ENDPOINT, payload);
    expect(applyUpdater(cache())).toEqual({
      scheduled_actions: [action(), created],
      total: 2,
    });
  });

  it('touches nothing when the server refuses the creation', async () => {
    mutate.create.mockResolvedValue(undefined);
    const { result } = setup();

    await act(async () => {
      await result.current.createAction(payload);
    });

    expect(setData).not.toHaveBeenCalled();
  });
});

describe('useScheduledActions — updating', () => {
  it('patches the row and replaces only that one', async () => {
    const updated = action({ title: 'Renamed' });
    mutate.update.mockResolvedValue(updated);
    const { result } = setup();

    await act(async () => {
      await result.current.updateAction('a1', { title: 'Renamed' });
    });

    expect(mutate.update).toHaveBeenCalledWith(`${ENDPOINT}/a1`, { title: 'Renamed' });
    const next = applyUpdater(cache({ scheduled_actions: [action(), action({ id: 'a2' })] }));
    expect(next?.scheduled_actions).toEqual([updated, action({ id: 'a2' })]);
  });

  it('leaves the cache alone when the update is refused', async () => {
    mutate.update.mockResolvedValue(undefined);
    const { result } = setup();

    await act(async () => {
      await result.current.updateAction('a1', { title: 'Renamed' });
    });

    expect(setData).not.toHaveBeenCalled();
  });
});

describe('useScheduledActions — deleting', () => {
  it('deletes the row and decrements the count', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.deleteAction('a1');
    });

    expect(mutate.remove).toHaveBeenCalledWith(`${ENDPOINT}/a1`);
    expect(
      applyUpdater(cache({ scheduled_actions: [action(), action({ id: 'a2' })], total: 2 }))
    ).toEqual({ scheduled_actions: [action({ id: 'a2' })], total: 1 });
  });
});

describe('useScheduledActions — toggling and running', () => {
  it('toggles through the dedicated route and swaps the row in', async () => {
    const toggled = action({ is_enabled: false });
    mutate.toggle.mockResolvedValue(toggled);
    const { result } = setup();

    await act(async () => {
      await result.current.toggleAction('a1');
    });

    expect(mutate.toggle).toHaveBeenCalledWith(`${ENDPOINT}/a1/toggle`);
    expect(applyUpdater(cache())?.scheduled_actions).toEqual([toggled]);
  });

  it('marks only the launched row as executing', async () => {
    mutate.execute.mockResolvedValue({ status: 'queued' });
    const { result } = setup();

    await act(async () => {
      await result.current.executeAction('a1');
    });

    expect(mutate.execute).toHaveBeenCalledWith(`${ENDPOINT}/a1/execute`);
    const next = applyUpdater(
      cache({ scheduled_actions: [action(), action({ id: 'a2' })], total: 2 })
    );
    expect(next?.scheduled_actions.map(a => a.status)).toEqual(['executing', 'active']);
  });

  it('does not mark anything when the run could not be queued', async () => {
    mutate.execute.mockResolvedValue(undefined);
    const { result } = setup();

    await act(async () => {
      await result.current.executeAction('a1');
    });

    expect(setData).not.toHaveBeenCalled();
  });
});

describe('useScheduledActions — updaters on an empty cache', () => {
  it.each([
    [
      'create',
      async (h: ReturnType<typeof useScheduledActions>) =>
        h.createAction({
          title: 't',
          action_prompt: 'p',
          days_of_week: [1],
          trigger_hour: 8,
          trigger_minute: 0,
        }),
    ],
    [
      'update',
      async (h: ReturnType<typeof useScheduledActions>) => h.updateAction('a1', { title: 't' }),
    ],
    ['delete', async (h: ReturnType<typeof useScheduledActions>) => h.deleteAction('a1')],
    ['toggle', async (h: ReturnType<typeof useScheduledActions>) => h.toggleAction('a1')],
    ['execute', async (h: ReturnType<typeof useScheduledActions>) => h.executeAction('a1')],
  ])('%s writes nothing while the cache is still empty', async (_label, run) => {
    Object.values(mutate).forEach(m => m.mockResolvedValue(action()));
    const { result } = setup();

    await act(async () => {
      await run(result.current);
    });

    // Every updater must return `prev` untouched — writing `{}` here would
    // wipe the list the next render reads.
    expect(applyUpdater(undefined)).toBeUndefined();
  });
});

describe('useScheduledActions — auto refresh', () => {
  it('polls at the resting cadence and stops on unmount', () => {
    vi.useFakeTimers();
    const { unmount } = setup();

    vi.advanceTimersByTime(AUTO_REFRESH_INTERVAL_MS);
    expect(refetch).toHaveBeenCalledTimes(1);

    unmount();
    vi.advanceTimersByTime(AUTO_REFRESH_INTERVAL_MS * 4);
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('speeds up while a run is executing', () => {
    vi.useFakeTimers();
    setup(cache({ scheduled_actions: [action({ status: 'executing' })] }));

    vi.advanceTimersByTime(EXECUTING_REFRESH_INTERVAL_MS);
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('keeps the resting cadence when nothing is executing', () => {
    vi.useFakeTimers();
    setup();

    vi.advanceTimersByTime(EXECUTING_REFRESH_INTERVAL_MS);
    expect(refetch).not.toHaveBeenCalled();
  });
});
