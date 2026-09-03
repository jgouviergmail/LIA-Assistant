/**
 * Screen wake lock for long foreground captures (ADR-258).
 *
 * A phone that dims and locks mid-meeting mutes the microphone on both mobile
 * platforms (measured: WKWebView suspends capture in the background, Android 9+
 * blocks background microphone access). The Wake Lock API keeps the screen on
 * while the recorder runs; it is released by the system whenever the page is
 * hidden, so the lock is re-requested each time the page becomes visible again.
 *
 * Best effort by design: browsers without the API (Firefox, older WebKit) get a
 * `null` handle and the recorder keeps working — the banner tells the user to
 * keep the screen on.
 */

export interface WakeLockHandle {
  /** Release the lock and stop re-acquiring it. */
  release(): Promise<void>;
}

interface WakeLockSentinelLike {
  release(): Promise<void>;
}

interface WakeLockLike {
  request(type: 'screen'): Promise<WakeLockSentinelLike>;
}

function wakeLockApi(): WakeLockLike | null {
  if (typeof navigator === 'undefined') return null;
  const candidate = (navigator as Navigator & { wakeLock?: WakeLockLike }).wakeLock;
  return candidate && typeof candidate.request === 'function' ? candidate : null;
}

/** Whether this browser exposes the Wake Lock API at all. */
export function isWakeLockSupported(): boolean {
  return wakeLockApi() !== null;
}

/**
 * Acquire a screen wake lock that survives visibility changes.
 *
 * @returns A handle to release it, or `null` when the API is absent or refused.
 */
export async function acquireWakeLock(): Promise<WakeLockHandle | null> {
  const api = wakeLockApi();
  if (api === null) return null;
  let sentinel: WakeLockSentinelLike | null = null;
  let released = false;

  const request = async () => {
    if (released) return;
    try {
      sentinel = await api.request('screen');
    } catch {
      // Refused (low battery, permission policy): keep working without it.
      sentinel = null;
    }
  };
  const onVisibility = () => {
    if (document.visibilityState === 'visible') void request();
  };

  await request();
  if (sentinel === null) return null;
  document.addEventListener('visibilitychange', onVisibility);

  return {
    async release() {
      released = true;
      document.removeEventListener('visibilitychange', onVisibility);
      const current = sentinel;
      sentinel = null;
      if (current) await current.release().catch(() => undefined);
    },
  };
}
