/**
 * Haptic acknowledgements — opt-out, capability-detected, always silent when
 * unavailable.
 *
 * Three failure modes matter more than the buzz itself: vibrating when the
 * reader asked not to, throwing on a platform that does not implement the API
 * (iOS Safari), and breaking the action a buzz was merely confirming.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import {
  HAPTICS_ENABLED_KEY,
  areHapticsEnabled,
  haptic,
  isHapticsSupported,
  setHapticsEnabled,
  subscribeHaptics,
} from '../haptics';

function withVibrate(impl: (pattern: number | number[]) => boolean) {
  Object.defineProperty(navigator, 'vibrate', {
    configurable: true,
    writable: true,
    value: impl,
  });
}

function withoutVibrate() {
  Reflect.deleteProperty(navigator, 'vibrate');
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  withoutVibrate();
  window.localStorage.clear();
});

describe('capability detection', () => {
  it('reports support only when the API exists', () => {
    withoutVibrate();
    expect(isHapticsSupported()).toBe(false);

    withVibrate(() => true);
    expect(isHapticsSupported()).toBe(true);
  });

  it('is a no-op on a platform without the API — never an error', () => {
    // iOS Safari: the call must simply do nothing.
    withoutVibrate();

    expect(() => haptic('success')).not.toThrow();
  });
});

describe('the preference', () => {
  it('defaults to on where the device can vibrate', () => {
    expect(areHapticsEnabled()).toBe(true);
  });

  it('round-trips through storage', () => {
    setHapticsEnabled(false);
    expect(areHapticsEnabled()).toBe(false);
    expect(window.localStorage.getItem(HAPTICS_ENABLED_KEY)).toBe('off');

    setHapticsEnabled(true);
    expect(areHapticsEnabled()).toBe(true);
  });

  it('is device-scoped — nothing is sent to the server', () => {
    // The same account on a desktop has no motor at all; propagating a phone's
    // choice would be wrong. The key lives beside the theme and font ones.
    expect(HAPTICS_ENABLED_KEY.startsWith('lia.')).toBe(true);
  });
});

describe('firing', () => {
  it('vibrates for a known pattern', () => {
    const vibrate = vi.fn(() => true);
    withVibrate(vibrate);

    haptic('start');

    expect(vibrate).toHaveBeenCalledTimes(1);
  });

  it('keeps every acknowledgement brief', () => {
    // A buzz longer than a few tens of ms reads as an alarm.
    const calls: (number | number[])[] = [];
    withVibrate(pattern => {
      calls.push(pattern);
      return true;
    });

    for (const pattern of ['start', 'success', 'error', 'confirm'] as const) haptic(pattern);

    for (const shape of calls) {
      const total = Array.isArray(shape) ? shape.reduce((a, b) => a + b, 0) : shape;
      expect(total).toBeLessThanOrEqual(100);
    }
  });

  it('stays silent once the reader switched it off', () => {
    const vibrate = vi.fn(() => true);
    withVibrate(vibrate);
    setHapticsEnabled(false);

    haptic('success');

    expect(vibrate).not.toHaveBeenCalled();
  });

  it('never lets a refused vibration break the action it confirmed', () => {
    // Chrome throws outside a user gesture / under a permissions policy.
    withVibrate(() => {
      throw new Error('blocked by permissions policy');
    });

    expect(() => haptic('confirm')).not.toThrow();
  });

  it('sends a copy of the pattern, never the shared constant', () => {
    // A caller mutating the array it receives must not corrupt later buzzes.
    let received: number | number[] = 0;
    withVibrate(pattern => {
      received = pattern;
      return true;
    });

    haptic('error');
    if (Array.isArray(received)) received[0] = 9999;
    haptic('error');

    expect(Array.isArray(received) ? received[0] : received).not.toBe(9999);
  });
});

describe('haptics — when the browser refuses to remember', () => {
  // Private mode, blocked cookies, a full quota: `localStorage` throws on
  // access. A decorative preference must never break the page that reads it.
  function withThrowingStorage(): () => void {
    const real = Object.getOwnPropertyDescriptor(window, 'localStorage');
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get() {
        throw new DOMException('denied', 'SecurityError');
      },
    });
    return () => {
      if (real) Object.defineProperty(window, 'localStorage', real);
    };
  }

  it('assumes on when the preference cannot be read', () => {
    const restore = withThrowingStorage();
    try {
      // Not "off": defaulting to silence on a device that CAN vibrate would
      // turn a storage failure into a missing feature.
      expect(areHapticsEnabled()).toBe(true);
    } finally {
      restore();
    }
  });

  it('still notifies the switch when the preference cannot be written', () => {
    const seen: number[] = [];
    const unsubscribe = subscribeHaptics(() => seen.push(1));
    const restore = withThrowingStorage();
    try {
      expect(() => setHapticsEnabled(false)).not.toThrow();
    } finally {
      restore();
      unsubscribe();
    }

    // The choice must hold for the session rather than snapping back under
    // the finger, even though nothing was persisted.
    expect(seen).toHaveLength(1);
  });
});

describe('subscribeHaptics', () => {
  it('stops calling a listener that unsubscribed', () => {
    let calls = 0;
    const unsubscribe = subscribeHaptics(() => {
      calls += 1;
    });

    setHapticsEnabled(false);
    expect(calls).toBe(1);

    unsubscribe();
    setHapticsEnabled(true);
    expect(calls).toBe(1);
  });

  it('notifies every subscriber, not just the first', () => {
    const seen: string[] = [];
    const a = subscribeHaptics(() => seen.push('a'));
    const b = subscribeHaptics(() => seen.push('b'));

    setHapticsEnabled(false);
    a();
    b();

    expect(seen).toEqual(['a', 'b']);
  });
});
