/**
 * Watchdog on widget iframes — the failure signal that did not exist.
 *
 * The defect it closes: a frame the engine refuses (WebKit cancels the
 * navigation with no event) left a blank rectangle, no message and no log, so
 * a remote report carried zero information. These tests pin both the state
 * machine and the fact that the failure is reported with the two facts that
 * explain nearly every COEP refusal.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useRef } from 'react';

import { useFrameLoadWatchdog } from '../useFrameLoadWatchdog';
import { logger } from '@/lib/logger';

vi.mock('@/lib/logger', () => ({
  logger: { warn: vi.fn(), debug: vi.fn(), info: vi.fn(), error: vi.fn() },
}));

/** Mounts the hook against a real (detached) iframe element. */
function renderWatchdog(frame: HTMLIFrameElement | null, timeoutMs = 1000) {
  return renderHook(() => {
    const ref = useRef<HTMLIFrameElement | null>(frame);
    return useFrameLoadWatchdog(ref, { kind: 'skill', label: 'interactive-map', timeoutMs });
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useFrameLoadWatchdog', () => {
  it('starts pending and settles to loaded when the frame fires load', () => {
    const frame = document.createElement('iframe');
    const { result } = renderWatchdog(frame);

    expect(result.current).toBe('pending');
    act(() => {
      frame.dispatchEvent(new Event('load'));
    });
    expect(result.current).toBe('loaded');
  });

  it('settles to timeout when load never fires, and reports the diagnosis', () => {
    const frame = document.createElement('iframe');
    const { result } = renderWatchdog(frame);

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(result.current).toBe('timeout');
    expect(logger.warn).toHaveBeenCalledTimes(1);
    const [event, context] = vi.mocked(logger.warn).mock.calls[0];
    expect(event).toBe('widget_frame_load_timeout');
    expect(context).toMatchObject({ kind: 'skill', label: 'interactive-map', timeoutMs: 1000 });
    // Without these two the report is unactionable — they ARE the diagnosis.
    expect(context).toHaveProperty('crossOriginIsolated');
    expect(context).toHaveProperty('credentiallessSupported');
  });

  it('never fires the timeout after a successful load', () => {
    const frame = document.createElement('iframe');
    const { result } = renderWatchdog(frame);

    act(() => {
      frame.dispatchEvent(new Event('load'));
      vi.advanceTimersByTime(5000);
    });

    expect(result.current).toBe('loaded');
    expect(logger.warn).not.toHaveBeenCalled();
  });

  it('stays pending and arms nothing when there is no frame', () => {
    const { result } = renderWatchdog(null);
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(result.current).toBe('pending');
    expect(logger.warn).not.toHaveBeenCalled();
  });

  it('re-arms on retry: a settled outcome from a previous attempt reads as pending again', () => {
    const frame = document.createElement('iframe');
    const { result, rerender } = renderHook(
      ({ attempt }: { attempt: number }) => {
        const ref = useRef<HTMLIFrameElement | null>(frame);
        return useFrameLoadWatchdog(ref, {
          kind: 'skill',
          label: 'interactive-map',
          timeoutMs: 1000,
          attempt,
        });
      },
      { initialProps: { attempt: 0 } }
    );

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current).toBe('timeout');

    rerender({ attempt: 1 });
    expect(result.current).toBe('pending');

    act(() => {
      frame.dispatchEvent(new Event('load'));
    });
    expect(result.current).toBe('loaded');
  });

  describe("readiness: 'bridge-ready' (MCP Apps)", () => {
    /** Mounts the hook in handshake mode, with `isReady` controllable. */
    function renderBridgeWatchdog(frame: HTMLIFrameElement, ready = false) {
      return renderHook(
        ({ isReady }: { isReady: boolean }) => {
          const ref = useRef<HTMLIFrameElement | null>(frame);
          return useFrameLoadWatchdog(ref, {
            kind: 'mcp',
            label: 'excalidraw',
            readiness: 'bridge-ready',
            isReady,
            timeoutMs: 1000,
          });
        },
        { initialProps: { isReady: ready } }
      );
    }

    it('does NOT settle on the frame load event — the airlock shell always loads', () => {
      // Measured on WebKit: the shell loads, its four locks pass, the payload
      // executes and the bridge guard passes. A third-party widget that dies on
      // boot still leaves an opaque rectangle, and `load` cannot see it.
      const frame = document.createElement('iframe');
      const { result } = renderBridgeWatchdog(frame);

      act(() => {
        frame.dispatchEvent(new Event('load'));
      });
      expect(result.current).toBe('pending');

      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(result.current).toBe('timeout');
      expect(vi.mocked(logger.warn).mock.calls[0][1]).toMatchObject({
        kind: 'mcp',
        readiness: 'bridge-ready',
      });
    });

    it('recovers when the handshake arrives AFTER the timeout — the widget proved itself alive', () => {
      const frame = document.createElement('iframe');
      const { result, rerender } = renderBridgeWatchdog(frame);

      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(result.current).toBe('timeout');

      rerender({ isReady: true });
      expect(result.current).toBe('loaded');
    });

    it('arms no further timer once ready — a late timer would log a false failure', () => {
      const frame = document.createElement('iframe');
      const { rerender } = renderBridgeWatchdog(frame);

      rerender({ isReady: true });
      act(() => {
        vi.advanceTimersByTime(10_000);
      });

      expect(logger.warn).not.toHaveBeenCalled();
    });

    it('settles as soon as the widget speaks the protocol', () => {
      const frame = document.createElement('iframe');
      const { result, rerender } = renderBridgeWatchdog(frame);

      rerender({ isReady: true });
      expect(result.current).toBe('loaded');

      act(() => {
        vi.advanceTimersByTime(5000);
      });
      expect(result.current).toBe('loaded');
      expect(logger.warn).not.toHaveBeenCalled();
    });
  });

  it('clears its timer on unmount (no late state update, no phantom report)', () => {
    const frame = document.createElement('iframe');
    const { unmount } = renderWatchdog(frame);
    unmount();
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(logger.warn).not.toHaveBeenCalled();
  });
});
