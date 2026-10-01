/**
 * The live mode's browser predicates: what a session needs before anything is
 * minted, and the Apple mobile test that picks the audio wire and the standby
 * hint (ADR-299, ADR-329).
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { isAppleMobile, isLiveSupported } from '../support';

/** jsdom defines no `navigator.mediaDevices`: a test sets the one it needs. */
function setMediaDevices(value: { getUserMedia: () => unknown } | undefined): void {
  Object.defineProperty(navigator, 'mediaDevices', { value, configurable: true });
}

describe('live support predicates', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    // jsdom has no microphone: the property exists only while a test defines it.
    Reflect.deleteProperty(navigator, 'mediaDevices');
  });

  it('holds a session only with a socket, an audio worklet and a microphone', () => {
    vi.stubGlobal('AudioContext', function AudioContext() {});
    vi.stubGlobal('AudioWorkletNode', function AudioWorkletNode() {});
    setMediaDevices({ getUserMedia: vi.fn() });
    expect(isLiveSupported()).toBe(true);
    // An old WebView without a worklet: nothing is minted for it.
    vi.stubGlobal('AudioWorkletNode', undefined);
    expect(isLiveSupported()).toBe(false);
  });

  it('refuses a page served outside a secure context, where the microphone does not exist', () => {
    vi.stubGlobal('AudioContext', function AudioContext() {});
    vi.stubGlobal('AudioWorkletNode', function AudioWorkletNode() {});
    setMediaDevices(undefined);
    expect(isLiveSupported()).toBe(false);
  });

  it('recognises an iPhone, an iPad and an iPod, and nothing else', () => {
    const agent = vi.spyOn(navigator, 'userAgent', 'get');
    for (const device of ['iPhone', 'iPad', 'iPod']) {
      agent.mockReturnValue(`Mozilla/5.0 (${device}; CPU OS 18_0 like Mac OS X)`);
      expect(isAppleMobile()).toBe(true);
    }
    agent.mockReturnValue('Mozilla/5.0 (Linux; Android 15) Chrome/150.0');
    expect(isAppleMobile()).toBe(false);
  });
});
