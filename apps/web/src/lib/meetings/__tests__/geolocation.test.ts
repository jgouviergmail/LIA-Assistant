/**
 * The recording position is read only when geolocation is ALREADY granted,
 * never prompts, and never delays the start past its timeout.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { bestEffortPosition } from '../geolocation';

type PositionCallback = (position: {
  coords: { latitude: number; longitude: number; accuracy: number };
}) => void;

function installPermissions(state: string) {
  Object.defineProperty(navigator, 'permissions', {
    value: { query: vi.fn(async () => ({ state })) },
    configurable: true,
  });
}

function installGeolocation(impl: (ok: PositionCallback, fail: (e: unknown) => void) => void) {
  Object.defineProperty(navigator, 'geolocation', {
    value: { getCurrentPosition: vi.fn(impl) },
    configurable: true,
  });
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  Reflect.deleteProperty(navigator, 'permissions');
  Reflect.deleteProperty(navigator, 'geolocation');
});

describe('bestEffortPosition', () => {
  it('never prompts: an unresolved permission yields null without touching geolocation', async () => {
    installPermissions('prompt');
    const getCurrentPosition = vi.fn();
    Object.defineProperty(navigator, 'geolocation', {
      value: { getCurrentPosition },
      configurable: true,
    });
    expect(await bestEffortPosition()).toBeNull();
    expect(getCurrentPosition).not.toHaveBeenCalled();
  });

  it('returns the coordinates when already granted', async () => {
    installPermissions('granted');
    installGeolocation(ok => ok({ coords: { latitude: 48.85, longitude: 2.35, accuracy: 12 } }));
    expect(await bestEffortPosition()).toEqual({ lat: 48.85, lon: 2.35, accuracy_m: 12 });
  });

  it('gives up after the timeout rather than delaying the recording', async () => {
    installPermissions('granted');
    installGeolocation(() => undefined); // never answers
    const pending = bestEffortPosition();
    await vi.advanceTimersByTimeAsync(3500);
    expect(await pending).toBeNull();
  });

  it('a position error yields null', async () => {
    installPermissions('granted');
    installGeolocation((_ok, fail) => fail(new Error('unavailable')));
    expect(await bestEffortPosition()).toBeNull();
  });
});
