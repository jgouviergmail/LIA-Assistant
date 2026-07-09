/**
 * voiceModeStore — voice mode state machine, error handling and persistence.
 *
 * The setError tests pin the DOCUMENTED contract ("On error, go back to
 * listening if enabled, else idle") and the invariant that clearing an error
 * never corrupts the state machine — both were silently violated before the
 * 2026-07 test-foundation fix (state became literally `undefined` on
 * setError(null) because Object.assign copies explicit undefined values).
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';

import { useVoiceModeStore } from '@/stores/voiceModeStore';
import { VOICE_MODE_ENABLED_KEY } from '@/lib/constants';

function resetStore(): void {
  useVoiceModeStore.setState({
    isEnabled: false,
    state: 'idle',
    isKwsReady: false,
    isKwsLoading: false,
    isKwsListening: false,
    error: null,
    lastWakeWordTime: null,
  });
}

beforeEach(() => {
  localStorage.clear();
  resetStore();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('voiceModeStore — enable / disable / toggle', () => {
  it('enable switches to listening and clears any error', () => {
    useVoiceModeStore.setState({ error: new Error('previous') });

    useVoiceModeStore.getState().enable();

    const s = useVoiceModeStore.getState();
    expect(s.isEnabled).toBe(true);
    expect(s.state).toBe('listening');
    expect(s.error).toBeNull();
  });

  it('disable returns to idle and stops the KWS mic flag', () => {
    useVoiceModeStore.setState({ isEnabled: true, state: 'speaking', isKwsListening: true });

    useVoiceModeStore.getState().disable();

    const s = useVoiceModeStore.getState();
    expect(s.isEnabled).toBe(false);
    expect(s.state).toBe('idle');
    expect(s.isKwsListening).toBe(false);
    expect(s.error).toBeNull();
  });

  it('toggle flips in both directions with the matching state', () => {
    useVoiceModeStore.getState().toggle();
    expect(useVoiceModeStore.getState().isEnabled).toBe(true);
    expect(useVoiceModeStore.getState().state).toBe('listening');

    useVoiceModeStore.getState().toggle();
    expect(useVoiceModeStore.getState().isEnabled).toBe(false);
    expect(useVoiceModeStore.getState().state).toBe('idle');
  });
});

describe('voiceModeStore — state machine and KWS flags', () => {
  it('setState walks the machine through its stations', () => {
    for (const station of ['listening', 'recording', 'processing', 'speaking', 'idle'] as const) {
      useVoiceModeStore.getState().setState(station);
      expect(useVoiceModeStore.getState().state).toBe(station);
    }
  });

  it('setKwsReady / setKwsLoading / setKwsListening update their flags independently', () => {
    useVoiceModeStore.getState().setKwsReady(true);
    useVoiceModeStore.getState().setKwsLoading(true);
    useVoiceModeStore.getState().setKwsListening(true);

    const s = useVoiceModeStore.getState();
    expect(s.isKwsReady).toBe(true);
    expect(s.isKwsLoading).toBe(true);
    expect(s.isKwsListening).toBe(true);
  });

  it('recordWakeWord stamps the detection time', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-09T12:00:00Z'));

    useVoiceModeStore.getState().recordWakeWord();

    expect(useVoiceModeStore.getState().lastWakeWordTime).toBe(
      new Date('2026-07-09T12:00:00Z').getTime()
    );
  });

  it('reset returns to idle but preserves the enabled preference', () => {
    useVoiceModeStore.setState({
      isEnabled: true,
      state: 'speaking',
      error: new Error('x'),
      lastWakeWordTime: 123,
      isKwsListening: true,
    });

    useVoiceModeStore.getState().reset();

    const s = useVoiceModeStore.getState();
    expect(s.state).toBe('idle');
    expect(s.error).toBeNull();
    expect(s.lastWakeWordTime).toBeNull();
    expect(s.isKwsListening).toBe(false);
    expect(s.isEnabled).toBe(true);
  });
});

describe('voiceModeStore — setError contract', () => {
  it('on error while enabled: stores the error and falls back to listening', () => {
    useVoiceModeStore.setState({ isEnabled: true, state: 'recording' });
    const err = new Error('mic lost');

    useVoiceModeStore.getState().setError(err);

    const s = useVoiceModeStore.getState();
    expect(s.error).toBe(err);
    expect(s.state).toBe('listening');
  });

  it('on error while disabled: stores the error and stays idle (documented contract)', () => {
    useVoiceModeStore.setState({ isEnabled: false, state: 'idle' });

    useVoiceModeStore.getState().setError(new Error('permission denied'));

    const s = useVoiceModeStore.getState();
    expect(s.error).not.toBeNull();
    expect(s.state).toBe('idle');
  });

  it('clearing the error preserves the current machine state (never undefined)', () => {
    useVoiceModeStore.setState({ isEnabled: true, state: 'speaking' });

    useVoiceModeStore.getState().setError(null);

    const s = useVoiceModeStore.getState();
    expect(s.error).toBeNull();
    expect(s.state).toBe('speaking');
  });
});

describe('voiceModeStore — persistence', () => {
  it('persists ONLY the enabled preference (partialize)', () => {
    useVoiceModeStore.getState().enable();
    useVoiceModeStore.getState().setKwsReady(true);

    const raw = localStorage.getItem(VOICE_MODE_ENABLED_KEY);
    expect(raw).not.toBeNull();
    const persisted = JSON.parse(raw!);
    expect(persisted.state).toEqual({ isEnabled: true });
  });

  it('rehydrates isEnabled=true as the listening state (merge)', async () => {
    localStorage.setItem(
      VOICE_MODE_ENABLED_KEY,
      JSON.stringify({ state: { isEnabled: true }, version: 0 })
    );

    vi.resetModules();
    const fresh = await import('@/stores/voiceModeStore');

    const s = fresh.useVoiceModeStore.getState();
    expect(s.isEnabled).toBe(true);
    expect(s.state).toBe('listening');
  });

  it('falls back to the current state when the persisted payload is empty (merge)', async () => {
    localStorage.setItem(VOICE_MODE_ENABLED_KEY, JSON.stringify({ state: {}, version: 0 }));

    vi.resetModules();
    const fresh = await import('@/stores/voiceModeStore');

    const s = fresh.useVoiceModeStore.getState();
    expect(s.isEnabled).toBe(false);
    expect(s.state).toBe('idle');
  });
});
