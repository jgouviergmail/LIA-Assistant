/**
 * isWakeWordSupported — what the detector needs, and above all what it does
 * NOT: no `SharedArrayBuffer`, no cross-origin isolation (ADR-329). The
 * previous engine's predicate required both, and that predicate — not the
 * engine — is what lost the wake word on iOS and in the native shells.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { isWakeWordSupported } from '../support';

function stubEverythingTheDetectorNeeds(): void {
  vi.stubGlobal('Worker', function Worker() {});
  vi.stubGlobal('AudioContext', function AudioContext() {});
  vi.stubGlobal('AudioWorkletNode', function AudioWorkletNode() {});
  vi.stubGlobal('crypto', { subtle: { digest: vi.fn() } });
  setMediaDevices({ getUserMedia: vi.fn() });
}

/** jsdom defines no `navigator.mediaDevices`: a test sets the one it needs. */
function setMediaDevices(value: { getUserMedia: () => unknown } | undefined): void {
  Object.defineProperty(navigator, 'mediaDevices', { value, configurable: true });
}

describe('isWakeWordSupported', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    // jsdom has no microphone: the property exists only while a test defines it.
    Reflect.deleteProperty(navigator, 'mediaDevices');
  });

  it('runs without shared memory and without cross-origin isolation', () => {
    stubEverythingTheDetectorNeeds();
    vi.stubGlobal('SharedArrayBuffer', undefined);
    vi.stubGlobal('crossOriginIsolated', false);
    expect(isWakeWordSupported()).toBe(true);
  });

  it.each([
    ['a module worker', 'Worker'],
    ['an audio worklet', 'AudioWorkletNode'],
    ['an audio context', 'AudioContext'],
  ])('refuses a browser without %s', (_label, missing) => {
    stubEverythingTheDetectorNeeds();
    vi.stubGlobal(missing, undefined);
    expect(isWakeWordSupported()).toBe(false);
  });

  it('refuses a page outside a secure context: no digest to check a model, no microphone', () => {
    stubEverythingTheDetectorNeeds();
    vi.stubGlobal('crypto', {});
    expect(isWakeWordSupported()).toBe(false);
    stubEverythingTheDetectorNeeds();
    setMediaDevices(undefined);
    expect(isWakeWordSupported()).toBe(false);
  });
});
