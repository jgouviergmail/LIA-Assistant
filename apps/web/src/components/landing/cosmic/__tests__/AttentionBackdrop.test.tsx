/**
 * The landing's « attention + latent space » canvas is mounted only once the
 * browser is idle (never in the way of the first paint — after `load` where the
 * idle API is missing), is destroyed with the component (no canvas, listener
 * or frame left after a navigation, the pending idle request cancelled), drops
 * its attention column on a phone, and reads the music's beat and the page's
 * pause from `<html>`.
 */

import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { LiaBackgroundOptions } from '@/lib/landing/attention-background';

const { mountMock, destroyMock, setMock } = vi.hoisted(() => ({
  mountMock: vi.fn(),
  destroyMock: vi.fn(),
  setMock: vi.fn(),
}));

vi.mock('@/lib/landing/attention-background', () => ({
  mountLiaBackground: mountMock,
}));

import { AttentionBackdrop } from '../AttentionBackdrop';

let idleCallbacks: IdleRequestCallback[];
let cancelIdle: ReturnType<typeof vi.fn>;
let mobileListeners: Array<(event: MediaQueryListEvent) => void>;

function stubMatchMedia(mobile: boolean) {
  mobileListeners = [];
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: mobile,
      media: query,
      addEventListener: (_: string, cb: (event: MediaQueryListEvent) => void) =>
        mobileListeners.push(cb),
      removeEventListener: (_: string, cb: (event: MediaQueryListEvent) => void) => {
        mobileListeners = mobileListeners.filter(listener => listener !== cb);
      },
    }))
  );
}

function runIdle() {
  const callbacks = idleCallbacks.splice(0);
  for (const cb of callbacks) cb({ didTimeout: false, timeRemaining: () => 50 });
}

function mountedOptions(): Partial<LiaBackgroundOptions> {
  expect(mountMock).toHaveBeenCalledTimes(1);
  return mountMock.mock.calls[0][0] as Partial<LiaBackgroundOptions>;
}

beforeEach(() => {
  idleCallbacks = [];
  mountMock.mockReset().mockReturnValue({ set: setMock, refresh: vi.fn(), destroy: destroyMock });
  destroyMock.mockReset();
  setMock.mockReset();
  // The id is the callback's position + 1, so a cancel can be traced to its request.
  vi.stubGlobal('requestIdleCallback', (cb: IdleRequestCallback) => idleCallbacks.push(cb));
  cancelIdle = vi.fn((id: number) => {
    idleCallbacks[id - 1] = () => undefined;
  });
  vi.stubGlobal('cancelIdleCallback', cancelIdle);
  stubMatchMedia(false);
});

afterEach(() => {
  // Unmount while the idle and media stubs the cleanup calls still exist.
  cleanup();
  vi.unstubAllGlobals();
  document.documentElement.style.removeProperty('--beat');
  document.documentElement.classList.remove('dark');
  delete document.documentElement.dataset.motion;
});

describe('AttentionBackdrop', () => {
  it('mounts on idle, inside its own decorative host, with the landing sections', () => {
    const { getByTestId } = render(<AttentionBackdrop />);
    expect(mountMock).not.toHaveBeenCalled();

    runIdle();
    const options = mountedOptions();
    const host = getByTestId('attention-backdrop');
    expect(host.getAttribute('aria-hidden')).toBe('true');
    expect(options.mount).toBe(host);
    expect(options.sections).toBe('main .landing-section');
    expect(options.intensityAttention).toBe(1);
    expect(options.intensityLatent).toBe(0.5);
    // The token column without the heads' curves.
    expect(options.attentionHeads).toBe(false);
    // Behind the content, above the cosmos backdrop's grain (-2).
    expect(options.zIndex).toBe(-1);
    // A device that cannot afford the motion gets a still background.
    expect(options.frameBudgetMs).toBe(5);
    // The labels drawn into the canvas are translated, one per cluster / head.
    expect(options.labels).toHaveLength(6);
    expect(options.labels?.[0]).toBe('landing.cosmos.attention.labels.emails');
    expect(options.headNames).toHaveLength(4);
  });

  it('destroys the canvas on unmount, and never mounts when unmounted before idle', () => {
    const first = render(<AttentionBackdrop />);
    runIdle();
    first.unmount();
    expect(destroyMock).toHaveBeenCalledTimes(1);
    expect(mobileListeners).toHaveLength(0);

    mountMock.mockClear();
    const second = render(<AttentionBackdrop />);
    second.unmount();
    // The pending idle request itself is cancelled — not merely ignored by a
    // guard: under StrictMode the host is re-attached and would mount twice.
    expect(cancelIdle).toHaveBeenCalledWith(idleCallbacks.length);
    runIdle();
    expect(mountMock).not.toHaveBeenCalled();
  });

  it('waits for the page load where the idle API is missing (WebKit), and cancels it too', () => {
    vi.stubGlobal('requestIdleCallback', undefined);
    vi.useFakeTimers();
    try {
      const readyState = vi.spyOn(document, 'readyState', 'get').mockReturnValue('loading');
      const first = render(<AttentionBackdrop />);
      vi.advanceTimersByTime(50);
      expect(mountMock).not.toHaveBeenCalled();
      readyState.mockReturnValue('complete');
      window.dispatchEvent(new Event('load'));
      vi.advanceTimersByTime(0);
      expect(mountMock).toHaveBeenCalledTimes(1);
      first.unmount();

      mountMock.mockClear();
      readyState.mockReturnValue('loading');
      const second = render(<AttentionBackdrop />);
      second.unmount();
      window.dispatchEvent(new Event('load'));
      vi.advanceTimersByTime(10);
      expect(mountMock).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('drops the attention column on a phone, and follows a breakpoint change', () => {
    stubMatchMedia(true);
    render(<AttentionBackdrop />);
    runIdle();
    expect(mountedOptions().intensityAttention).toBe(0);

    mobileListeners[0]({ matches: false } as MediaQueryListEvent);
    expect(setMock).toHaveBeenCalledWith({ intensityAttention: 1 });
  });

  it('reads the theme class and the music beat from <html>', () => {
    render(<AttentionBackdrop />);
    runIdle();
    const options = mountedOptions();

    expect(options.isDark?.()).toBe(false);
    document.documentElement.classList.add('dark');
    expect(options.isDark?.()).toBe(true);

    expect(options.beatGain).toBeGreaterThan(0);
    expect(options.beat?.()).toBe(0);
    document.documentElement.style.setProperty('--beat', '0.750');
    expect(options.beat?.()).toBe(0.75);
  });

  it("follows the page's pause control (WCAG 2.2.2), read at every frame", () => {
    render(<AttentionBackdrop />);
    runIdle();
    const options = mountedOptions();

    expect(options.paused?.()).toBe(false);
    document.documentElement.dataset.motion = 'paused';
    expect(options.paused?.()).toBe(true);
  });
});
