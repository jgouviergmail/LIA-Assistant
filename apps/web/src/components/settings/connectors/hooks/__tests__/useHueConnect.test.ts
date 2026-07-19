/**
 * useHueConnect — the Philips Hue pairing flow: discovery, the 30-second
 * press-link countdown (an interval that must be cleared on success, on reset
 * **and** on unmount), the pair → activate handshake, and the remote OAuth
 * redirect. Every failure path reports through `onError` rather than throwing.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderHook, act, waitFor } from '@/__tests__/test-utils';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get, post } }));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));

import { useHueConnect } from '../useHueConnect';

const BRIDGE = { id: 'b1', internalipaddress: '192.168.0.42' };

let originalLocation: Location;

beforeEach(() => {
  vi.clearAllMocks();
  originalLocation = window.location;
  Object.defineProperty(window, 'location', {
    value: { href: '' },
    writable: true,
    configurable: true,
  });
});

afterEach(() => {
  Object.defineProperty(window, 'location', { value: originalLocation, configurable: true });
  vi.useRealTimers();
});

describe('useHueConnect — discovery', () => {
  it('moves to the bridge list when the network answers', async () => {
    post.mockResolvedValue({ bridges: [BRIDGE] });
    const { result } = renderHook(() => useHueConnect());

    await act(async () => {
      await result.current.discoverBridges();
    });

    expect(post).toHaveBeenCalledWith('/connectors/philips-hue/discover');
    expect(result.current.step).toBe('discover');
    expect(result.current.bridges).toEqual([BRIDGE]);
    expect(result.current.isLoading).toBe(false);
  });

  it('stays on the mode screen and explains an empty network', async () => {
    post.mockResolvedValue({ bridges: [] });
    const { result } = renderHook(() => useHueConnect());

    await act(async () => {
      await result.current.discoverBridges();
    });

    expect(result.current.step).toBe('mode');
    expect(result.current.error).toBe('settings.connectors.hue.no_bridges_found');
  });

  it('reports a discovery failure to the caller', async () => {
    post.mockRejectedValue(new Error('network unreachable'));
    const onError = vi.fn();
    const { result } = renderHook(() => useHueConnect({ onError }));

    await act(async () => {
      await result.current.discoverBridges();
    });

    expect(result.current.error).toBe('network unreachable');
    expect(onError).toHaveBeenCalledWith('network unreachable');
    expect(result.current.isLoading).toBe(false);
  });
});

describe('useHueConnect — press-link countdown', () => {
  beforeEach(() => vi.useFakeTimers());

  it('counts down from 30 and stops at zero', () => {
    const { result } = renderHook(() => useHueConnect());

    act(() => result.current.startPairing());
    expect(result.current.step).toBe('pair');
    expect(result.current.countdown).toBe(30);

    act(() => void vi.advanceTimersByTime(3_000));
    expect(result.current.countdown).toBe(27);

    act(() => void vi.advanceTimersByTime(60_000));
    expect(result.current.countdown).toBe(0);
  });

  it('stops ticking once the user leaves the flow', () => {
    const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval');
    const { result } = renderHook(() => useHueConnect());

    act(() => result.current.startPairing());
    act(() => result.current.reset());

    expect(clearIntervalSpy).toHaveBeenCalled();
    expect(result.current.step).toBe('mode');
    expect(result.current.countdown).toBe(30);
  });

  it('clears the interval when the component goes away mid-pairing', () => {
    const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval');
    const { result, unmount } = renderHook(() => useHueConnect());

    act(() => result.current.startPairing());
    clearIntervalSpy.mockClear();
    unmount();

    expect(clearIntervalSpy).toHaveBeenCalled();
  });
});

describe('useHueConnect — pairing', () => {
  it('activates the bridge with the keys the pairing returned', async () => {
    post
      .mockResolvedValueOnce({
        success: true,
        application_key: 'app-key',
        client_key: 'client-key',
        bridge_id: 'b1',
      })
      .mockResolvedValueOnce({});
    const onSuccess = vi.fn();
    const { result } = renderHook(() => useHueConnect({ onSuccess }));

    await act(async () => {
      await result.current.pairBridge('192.168.0.42');
    });

    expect(post).toHaveBeenNthCalledWith(1, '/connectors/philips-hue/pair', {
      bridge_ip: '192.168.0.42',
    });
    expect(post).toHaveBeenNthCalledWith(2, '/connectors/philips-hue/activate/local', {
      bridge_ip: '192.168.0.42',
      application_key: 'app-key',
      client_key: 'client-key',
      bridge_id: 'b1',
    });
    expect(result.current.step).toBe('success');
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(result.current.isPairing).toBe(false);
  });

  it('surfaces the reason the bridge refused, without activating', async () => {
    post.mockResolvedValue({ success: false, error: 'link button not pressed' });
    const { result } = renderHook(() => useHueConnect());

    await act(async () => {
      await result.current.pairBridge('192.168.0.42');
    });

    expect(result.current.error).toBe('link button not pressed');
    expect(result.current.step).not.toBe('success');
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('falls back to the generic wording when the refusal carries no reason', async () => {
    post.mockResolvedValue({ success: false });
    const { result } = renderHook(() => useHueConnect());

    await act(async () => {
      await result.current.pairBridge('192.168.0.42');
    });

    expect(result.current.error).toBe('settings.connectors.hue.pairing_error');
  });

  it('reports a pairing that threw', async () => {
    post.mockRejectedValue(new Error('timeout'));
    const onError = vi.fn();
    const { result } = renderHook(() => useHueConnect({ onError }));

    await act(async () => {
      await result.current.pairBridge('192.168.0.42');
    });

    expect(result.current.error).toBe('timeout');
    expect(onError).toHaveBeenCalledWith('timeout');
    expect(result.current.isPairing).toBe(false);
  });
});

describe('useHueConnect — remote account', () => {
  it('hands the browser over to the provider consent screen', async () => {
    get.mockResolvedValue({ authorization_url: 'https://hue.example/oauth' });
    const { result } = renderHook(() => useHueConnect());

    await act(async () => {
      await result.current.connectRemote();
    });

    expect(get).toHaveBeenCalledWith('/connectors/philips-hue/authorize');
    expect(window.location.href).toBe('https://hue.example/oauth');
  });

  it('stays put when the provider returns no URL', async () => {
    get.mockResolvedValue({ authorization_url: '' });
    const { result } = renderHook(() => useHueConnect());

    await act(async () => {
      await result.current.connectRemote();
    });

    expect(window.location.href).toBe('');
  });

  it('reports a failed authorization request', async () => {
    get.mockRejectedValue(new Error('oauth down'));
    const onError = vi.fn();
    const { result } = renderHook(() => useHueConnect({ onError }));

    await act(async () => {
      await result.current.connectRemote();
    });

    expect(result.current.error).toBe('oauth down');
    expect(onError).toHaveBeenCalledWith('oauth down');
    expect(result.current.isLoading).toBe(false);
  });
});

describe('useHueConnect — reset', () => {
  it('wipes the discovered bridges and the error', async () => {
    post.mockResolvedValue({ bridges: [BRIDGE] });
    const { result } = renderHook(() => useHueConnect());
    await act(async () => {
      await result.current.discoverBridges();
    });
    act(() => result.current.setSelectedBridge('192.168.0.42'));

    act(() => result.current.reset());

    await waitFor(() => expect(result.current.step).toBe('mode'));
    expect(result.current.bridges).toEqual([]);
    expect(result.current.selectedBridge).toBeNull();
    expect(result.current.error).toBeNull();
  });
});
