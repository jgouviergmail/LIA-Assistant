/**
 * The live session machine is a pure function: which state follows which
 * event, and what a socket close means for a session that should go on.
 */
import { describe, it, expect } from 'vitest';

import { LIVE_RECONNECT_ATTEMPTS } from '@/lib/constants';

import { closeDecision, isSessionOpen, transition, type LiveStatus } from '../session-machine';

describe('live session machine', () => {
  it('walks the nominal path, reconnection included', () => {
    let s: LiveStatus = transition('idle', 'start');
    expect(s).toBe('minting');
    s = transition(s, 'minted');
    expect(s).toBe('connecting');
    s = transition(s, 'setup_complete');
    expect(s).toBe('live');
    s = transition(s, 'socket_closed');
    expect(s).toBe('reconnecting');
    s = transition(s, 'setup_complete');
    expect(s).toBe('live');
    s = transition(s, 'end');
    expect(s).toBe('ending');
    s = transition(s, 'ended');
    expect(s).toBe('ended');
    expect(transition(s, 'start')).toBe('minting');
  });

  it('ignores events that make no sense in a state', () => {
    expect(transition('idle', 'setup_complete')).toBe('idle');
    expect(transition('idle', 'end')).toBe('idle');
    expect(transition('ended', 'socket_closed')).toBe('ended');
    expect(transition('ending', 'setup_complete')).toBe('ending');
    expect(transition('live', 'start')).toBe('live');
    expect(transition('minting', 'socket_closed')).toBe('minting');
  });

  it('a failure anywhere before the end goes through ending', () => {
    expect(transition('minting', 'failed')).toBe('ending');
    expect(transition('reconnecting', 'failed')).toBe('ending');
    expect(transition('ended', 'failed')).toBe('ended');
  });

  it('decides what a close means', () => {
    expect(closeDecision(1006, 'h', 0)).toBe('reconnect');
    expect(closeDecision(1006, 'h', LIVE_RECONNECT_ATTEMPTS - 1)).toBe('reconnect');
    expect(closeDecision(1006, 'h', LIVE_RECONNECT_ATTEMPTS)).toBe('resumption_failed');
    expect(closeDecision(1006, null, 0)).toBe('provider_closed');
    expect(closeDecision(1000, 'h', 0)).toBe('provider_closed');
  });

  it('says which states hold a session (and the microphone)', () => {
    const open: LiveStatus[] = ['connecting', 'live', 'reconnecting'];
    const closed: LiveStatus[] = ['idle', 'minting', 'ending', 'ended'];
    for (const s of open) expect(isSessionOpen(s)).toBe(true);
    for (const s of closed) expect(isSessionOpen(s)).toBe(false);
  });
});
