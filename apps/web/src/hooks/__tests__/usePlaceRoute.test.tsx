import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient, ApiError } from '@/lib/api-client';
import { readGrantedPosition } from '@/lib/browser-geolocation';
import { GEOLOCATION_ENABLED_KEY } from '@/lib/constants';
import { usePlaceRoute } from '../usePlaceRoute';

vi.mock('@/lib/browser-geolocation', () => ({ readGrantedPosition: vi.fn() }));
const response = {
  origin_source: 'home',
  origin_as_of: null,
  travel_mode: 'WALK',
  polyline: '??_ibE_ibE',
  distance_meters: 1200,
  duration_seconds: 180,
};
const east = { lat: 0, lng: 1 };
const west = { lat: 0, lng: -1 };

beforeEach(() => {
  localStorage.clear();
  vi.mocked(readGrantedPosition).mockResolvedValue(null);
  vi.spyOn(apiClient, 'post').mockResolvedValue(response);
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe('account-owned place routes', () => {
  it('never reads location or makes a paid call on mount and reuses a recent selected route', async () => {
    const { result } = renderHook(() => usePlaceRoute('one'));
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(readGrantedPosition).not.toHaveBeenCalled();
    await act(async () => {
      await result.current.load('east', east);
    });
    expect(result.current.state.result?.origin_source).toBe('home');
    await act(async () => {
      await result.current.load('east', east);
    });
    expect(apiClient.post).toHaveBeenCalledOnce();
    expect(readGrantedPosition).not.toHaveBeenCalled();
  });

  it('uses current coordinates only after application opt-in, preserving zero coordinates', async () => {
    localStorage.setItem(GEOLOCATION_ENABLED_KEY, 'true');
    const origin = { lat: 0, lon: 0, accuracy: 15, timestamp: Date.now() };
    vi.mocked(readGrantedPosition).mockResolvedValue(origin);
    const { result } = renderHook(() => usePlaceRoute('one'));
    await act(async () => {
      await result.current.load('east', east);
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      '/connectors/google-maps/place-route',
      { destination: east, origin },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('aborts superseded reads and ignores a response that still arrives after the newer route', async () => {
    let finish!: (value: unknown) => void;
    vi.mocked(apiClient.post).mockImplementationOnce(
      () =>
        new Promise(resolve => {
          finish = resolve;
        })
    );
    const { result } = renderHook(() => usePlaceRoute('one'));
    let first!: ReturnType<typeof result.current.load>;
    act(() => {
      first = result.current.load('east', east);
    });
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledOnce());
    const signal = vi.mocked(apiClient.post).mock.calls[0][2]?.signal;
    await act(async () => {
      await result.current.load('west', west);
    });
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      finish({ ...response, distance_meters: 9000 });
      await first;
    });
    expect(result.current.state.ref).toBe('west');
    expect(result.current.state.result?.distance_meters).toBe(1200);
  });

  it('does not issue a second call for the same pending selection', async () => {
    let finish!: (value: unknown) => void;
    vi.mocked(apiClient.post).mockImplementationOnce(
      () =>
        new Promise(resolve => {
          finish = resolve;
        })
    );
    const { result } = renderHook(() => usePlaceRoute('one'));
    let first!: ReturnType<typeof result.current.load>;
    act(() => {
      first = result.current.load('east', east);
    });
    await act(async () => {
      expect(await result.current.load('east', east)).toBeNull();
    });
    expect(apiClient.post).toHaveBeenCalledOnce();
    await act(async () => {
      finish(response);
      await first;
    });
    expect(result.current.state.status).toBe('ready');
  });

  it('names a missing origin and allows an explicit retry', async () => {
    vi.mocked(apiClient.post).mockRejectedValueOnce(
      new ApiError('No origin', 422, {
        detail: { code: 'place_route_origin_unavailable', message: 'No origin' },
      })
    );
    const { result } = renderHook(() => usePlaceRoute('one'));
    await act(async () => {
      await result.current.load('east', east);
    });
    expect(result.current.state.error).toBe('origin');
    await act(async () => {
      await result.current.load('east', east, true);
    });
    expect(result.current.state.status).toBe('ready');
  });

  it.each([
    { ...response, polyline: 'invalid' },
    { ...response, distance_meters: -1 },
    { ...response, origin_source: 'last_known', origin_as_of: null },
  ])('rejects unusable route facts without retaining an old route', async raw => {
    vi.mocked(apiClient.post).mockResolvedValue(raw);
    const { result } = renderHook(() => usePlaceRoute('one'));
    await act(async () => {
      await result.current.load('east', east);
    });
    expect(result.current.state.status).toBe('error');
    expect(result.current.state.result).toBeNull();
  });

  it('expires cached trips and refreshes on explicit request', async () => {
    const clock = vi.spyOn(Date, 'now').mockReturnValue(1000);
    const { result } = renderHook(() => usePlaceRoute('one'));
    await act(async () => {
      await result.current.load('east', east);
    });
    clock.mockReturnValue(122_000);
    await act(async () => {
      await result.current.load('east', east);
    });
    await act(async () => {
      await result.current.load('east', east, true);
    });
    expect(apiClient.post).toHaveBeenCalledTimes(3);
  });

  it('clears owner data and refuses retained callbacks after switching or unmounting', async () => {
    const { result, rerender, unmount } = renderHook(({ owner }) => usePlaceRoute(owner), {
      initialProps: { owner: 'one' },
    });
    await act(async () => {
      await result.current.load('east', east);
    });
    const obsolete = result.current.load;
    rerender({ owner: 'two' });
    expect(result.current.state.result).toBeNull();
    await act(async () => {
      await obsolete('east', east);
    });
    expect(apiClient.post).toHaveBeenCalledOnce();
    rerender({ owner: 'one' });
    await act(async () => {
      await result.current.load('east', east);
    });
    expect(apiClient.post).toHaveBeenCalledTimes(2);
    const retained = result.current.load;
    unmount();
    await retained('west', west);
    expect(apiClient.post).toHaveBeenCalledTimes(2);
  });
});
