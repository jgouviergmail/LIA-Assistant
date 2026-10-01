/**
 * useLiveSession — the React shell: one controller per mount, the latest
 * bindings, the visibility and unmount effects. The orchestration itself is
 * tested on the controller.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';

const h = vi.hoisted(() => ({
  instances: [] as Array<Record<string, ReturnType<typeof vi.fn>>>,
  deps: [] as Array<{
    chat: unknown;
    wakeLanguage: () => string | null;
    createWakeListener: (options: unknown) => unknown;
    chime: () => void;
  }>,
  wakeSupported: true,
}));

vi.mock('@/lib/live/session-controller', () => ({
  LiveSessionController: vi.fn(function (this: Record<string, unknown>, deps: unknown) {
    const instance = {
      start: vi.fn(async () => {}),
      end: vi.fn(async () => {}),
      toggleMute: vi.fn(),
      extend: vi.fn(async () => true),
      declineExtension: vi.fn(),
      standby: vi.fn(async () => {}),
      wake: vi.fn(async () => {}),
      pageHidden: vi.fn(),
      setChat: vi.fn(),
    };
    h.instances.push(instance);
    h.deps.push(deps as (typeof h.deps)[number]);
    return instance;
  }),
}));
vi.mock('@/lib/api-client', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/lib/live/transports', () => ({ createLiveTransport: vi.fn() }));
vi.mock('@/lib/live/pcm-player', () => ({ PcmStreamPlayer: vi.fn() }));
vi.mock('@/lib/live/mic-capture', () => ({ startMicCapture: vi.fn() }));
vi.mock('@/lib/audio/wake-word/support', () => ({ isWakeWordSupported: () => h.wakeSupported }));
vi.mock('@/lib/audio/wake-word/listener', () => ({
  WakeListener: vi.fn(function (this: Record<string, unknown>) {
    this.kind = 'wake-listener';
  }),
}));

import { useLiveStore } from '@/stores/liveStore';

import { useLiveSession, type LiveChatBindings } from '../useLiveSession';

function bindings(label: string): LiveChatBindings {
  return {
    sendMessage: vi.fn(async () => {
      void label;
    }),
    stop: vi.fn(async () => {}),
    appendMessage: vi.fn(),
    readAnswer: async () => ({ text: label, pendingQuestion: null }),
  };
}

describe('useLiveSession', () => {
  beforeEach(() => {
    h.instances.length = 0;
    h.deps.length = 0;
    useLiveStore.getState().reset();
  });

  it('builds one controller per mount and forwards the four actions', async () => {
    const { result, rerender } = renderHook(props => useLiveSession(props), {
      initialProps: bindings('a'),
    });
    rerender(bindings('b'));
    expect(h.instances).toHaveLength(1);
    await result.current.start();
    await result.current.end('ended');
    result.current.toggleMute();
    expect(h.instances[0].start).toHaveBeenCalledTimes(1);
    expect(h.instances[0].end).toHaveBeenCalledWith('ended');
    expect(h.instances[0].toggleMute).toHaveBeenCalledTimes(1);
    await result.current.extend();
    result.current.declineExtension();
    expect(h.instances[0].extend).toHaveBeenCalledTimes(1);
    expect(h.instances[0].declineExtension).toHaveBeenCalledTimes(1);
  });

  it('forwards standby and wake, and hands the controller the wake word of the interface language (ADR-329)', async () => {
    const { result } = renderHook(props => useLiveSession(props), {
      initialProps: bindings('a'),
    });
    await result.current.standby();
    await result.current.wake();
    expect(h.instances[0].standby).toHaveBeenCalledWith('manual');
    expect(h.instances[0].wake).toHaveBeenCalledTimes(1);
    const deps = h.deps[0];
    expect(deps.wakeLanguage()).toBe('fr');
    expect(deps.createWakeListener({})).toMatchObject({ kind: 'wake-listener' });
    expect(typeof deps.chime).toBe('function');
    // A browser without the runtime gets no wake word: the button still wakes.
    h.wakeSupported = false;
    try {
      expect(deps.createWakeListener({})).toBeNull();
    } finally {
      h.wakeSupported = true;
    }
  });

  it('points the controller at the LATEST bindings, not the ones of the first render', () => {
    const first = bindings('first');
    const second = bindings('second');
    const { rerender } = renderHook(props => useLiveSession(props), { initialProps: first });
    expect(h.deps[0].chat).toBe(first);
    rerender(second);
    expect(h.instances[0].setChat).toHaveBeenLastCalledWith(second);
  });

  it('consumes a start asked from the header, at mount and later, in the mode asked', () => {
    useLiveStore.getState().requestStart();
    renderHook(() => useLiveSession(bindings('a')));
    expect(h.instances[0].start).toHaveBeenCalledTimes(1);
    expect(h.instances[0].start).toHaveBeenLastCalledWith('delegated');
    expect(useLiveStore.getState().pendingStart).toBeNull();
    act(() => useLiveStore.getState().requestStart('direct'));
    expect(h.instances[0].start).toHaveBeenCalledTimes(2);
    expect(h.instances[0].start).toHaveBeenLastCalledWith('direct');
    expect(useLiveStore.getState().pendingStart).toBeNull();
  });

  it('reports the page visibility and ends an open session on unmount', () => {
    const { unmount } = renderHook(() => useLiveSession(bindings('a')));
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
    expect(h.instances[0].pageHidden).toHaveBeenCalledWith(true);
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    document.dispatchEvent(new Event('visibilitychange'));
    expect(h.instances[0].pageHidden).toHaveBeenLastCalledWith(false);

    useLiveStore.getState().begin('s1');
    useLiveStore.getState().apply('minted');
    useLiveStore.getState().apply('setup_complete');
    unmount();
    expect(h.instances[0].end).toHaveBeenCalledWith('ended');
    document.dispatchEvent(new Event('visibilitychange'));
    expect(h.instances[0].pageHidden).toHaveBeenCalledTimes(2);
  });

  it('does not end anything on unmount when no session is open', () => {
    const { unmount } = renderHook(() => useLiveSession(bindings('a')));
    unmount();
    expect(h.instances[0].end).not.toHaveBeenCalled();
  });
});
