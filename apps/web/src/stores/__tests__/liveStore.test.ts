/**
 * What the banner draws and what the eyes read: the observable state of a live
 * session. Nothing here talks to a socket; the controller writes, the UI reads.
 */
import { beforeEach, describe, expect, it } from 'vitest';

import { LIVE_CAPTIONS_MAX } from '@/lib/constants';

import { effectiveVoiceState, useLiveHoldsMicrophone, useLiveStore } from '../liveStore';
import { renderHook } from '@testing-library/react';

describe('liveStore', () => {
  beforeEach(() => {
    useLiveStore.getState().reset();
  });

  it('begin opens a fresh session and clears what the previous one left', () => {
    const store = useLiveStore.getState();
    store.pushCaption('user', 'old', true);
    store.finish('error', 'boom');
    store.begin('s1');
    const state = useLiveStore.getState();
    expect(state.status).toBe('minting');
    expect(state.sessionId).toBe('s1');
    expect(state.captions).toEqual([]);
    expect(state.outcome).toBeNull();
    expect(state.error).toBeNull();
  });

  it('a start request names its mode and is consumed once', () => {
    // ADR-300 wave 4: the header asks for a delegated OR a direct session; the
    // chat page consumes the request once and starts in that mode.
    const store = useLiveStore.getState();
    expect(store.consumeStart()).toBeNull();
    store.requestStart();
    expect(useLiveStore.getState().pendingStart).toBe('delegated');
    expect(store.consumeStart()).toBe('delegated');
    expect(store.consumeStart()).toBeNull();
    store.requestStart('direct');
    expect(store.consumeStart()).toBe('direct');
    expect(useLiveStore.getState().pendingStart).toBeNull();
  });

  it('begin records the mode of the session, delegated unless said', () => {
    const store = useLiveStore.getState();
    store.begin('s1');
    expect(useLiveStore.getState().mode).toBe('delegated');
    store.begin('s2', 'direct');
    expect(useLiveStore.getState().mode).toBe('direct');
    store.reset();
    expect(useLiveStore.getState().mode).toBe('delegated');
  });

  it('applies the machine: an event that means nothing leaves the state', () => {
    const store = useLiveStore.getState();
    store.begin('s1');
    store.apply('minted');
    store.apply('setup_complete');
    expect(useLiveStore.getState().status).toBe('live');
    store.apply('start');
    expect(useLiveStore.getState().status).toBe('live');
  });

  it('merges a growing turn of one role and opens a new line on a new turn', () => {
    const store = useLiveStore.getState();
    store.pushCaption('assistant', 'Hel', false);
    store.pushCaption('assistant', 'lo', false);
    store.pushCaption('user', 'Hi', false);
    store.pushCaption('user', ' again', true);
    expect(useLiveStore.getState().captions.map(c => [c.role, c.text])).toEqual([
      ['assistant', 'Hello'],
      ['user', 'Hi'],
      ['user', ' again'],
    ]);
  });

  it('keeps at most LIVE_CAPTIONS_MAX lines, the oldest dropped', () => {
    const store = useLiveStore.getState();
    for (let i = 0; i < LIVE_CAPTIONS_MAX + 5; i++) store.pushCaption('user', `line ${i}`, true);
    const captions = useLiveStore.getState().captions;
    expect(captions).toHaveLength(LIVE_CAPTIONS_MAX);
    expect(captions[0].text).toBe('line 5');
  });

  it('finish names the outcome, silences the voice and drops the go-away countdown', () => {
    const store = useLiveStore.getState();
    store.begin('s1');
    store.setVoiceState('speaking');
    store.setDelegating(true);
    store.setTimeLeft(1200);
    store.finish('provider_closed');
    const state = useLiveStore.getState();
    expect(state.status).toBe('ended');
    expect(state.outcome).toBe('provider_closed');
    expect(state.voiceState).toBe('idle');
    expect(state.delegating).toBe(false);
    expect(state.timeLeftMs).toBeNull();
    expect(state.sessionId).toBe('s1');
  });

  it('exposes the session id while ended so the summary card can name it, then reset clears it', () => {
    const store = useLiveStore.getState();
    store.begin('s1');
    store.finish('ended');
    expect(useLiveStore.getState().sessionId).toBe('s1');
    store.reset();
    expect(useLiveStore.getState().sessionId).toBeNull();
    expect(useLiveStore.getState().status).toBe('idle');
  });

  it('hands the eyes the session voice state only while it holds the microphone', () => {
    expect(effectiveVoiceState('listening')).toBe('listening');
    const store = useLiveStore.getState();
    store.begin('s1');
    store.apply('minted');
    store.apply('setup_complete');
    store.setVoiceState('speaking');
    expect(effectiveVoiceState('listening')).toBe('speaking');
    expect(renderHook(() => useLiveHoldsMicrophone()).result.current).toBe(true);
    store.finish('ended');
    expect(effectiveVoiceState('listening')).toBe('listening');
    expect(renderHook(() => useLiveHoldsMicrophone()).result.current).toBe(false);
  });
});
