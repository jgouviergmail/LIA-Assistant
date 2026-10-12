import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { makeUser } from '@/__tests__/factories';
import { useSavedLastLocation, type LastLocationView } from '../useSavedLastLocation';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get } }));

const saved: LastLocationView = {
  stored: true,
  lat: 4,
  lon: 5,
  accuracy: 10,
  updated_at: '2026-10-06T10:00:00Z',
  stale: false,
};
beforeEach(() => {
  vi.resetAllMocks();
});

describe('saved location read lifetime', () => {
  it('does not show a position from a previous consent period when reenabled', async () => {
    get
      .mockResolvedValueOnce(saved)
      .mockImplementationOnce(() => new Promise<LastLocationView>(() => {}));
    const actor = makeUser({ id: 'one', use_last_known_location: true });
    const { result, rerender } = renderHook(
      ({ user, enabled }) => useSavedLastLocation(user, enabled),
      { initialProps: { user: actor, enabled: true } }
    );
    await waitFor(() => expect(result.current.stored).toEqual(saved));
    rerender({ user: makeUser({ id: 'one', use_last_known_location: false }), enabled: false });
    expect(result.current.stored).toBeNull();
    rerender({ user: makeUser({ id: 'one', use_last_known_location: true }), enabled: true });
    expect(result.current.stored).toBeNull();
  });
  it('never resurrects a position from a read started before its acknowledged deletion', async () => {
    let resolve: ((value: LastLocationView) => void) | undefined;
    get.mockImplementationOnce(
      () =>
        new Promise<LastLocationView>(done => {
          resolve = done;
        })
    );
    const actor = makeUser({ use_last_known_location: true });
    const { result } = renderHook(() => useSavedLastLocation(actor, true));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    act(() => result.current.clearStored());
    await act(async () => {
      resolve?.(saved);
    });
    expect(result.current.stored).toBeNull();
  });

  it('an old account callback cannot cancel the new account read', async () => {
    get.mockResolvedValueOnce(saved);
    let resolve: ((value: LastLocationView) => void) | undefined;
    get.mockImplementationOnce(
      () =>
        new Promise<LastLocationView>(done => {
          resolve = done;
        })
    );
    const first = makeUser({ id: 'one', use_last_known_location: true });
    const second = makeUser({ id: 'two', use_last_known_location: true });
    const { result, rerender } = renderHook(({ user }) => useSavedLastLocation(user, true), {
      initialProps: { user: first },
    });
    await waitFor(() => expect(result.current.stored).toEqual(saved));
    const oldClear = result.current.clearStored;
    rerender({ user: second });
    expect(result.current.stored).toBeNull();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    act(oldClear);
    await act(async () => {
      resolve?.({ ...saved, lat: 8 });
    });
    expect(result.current.stored?.lat).toBe(8);
  });
});
