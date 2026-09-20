/**
 * live-message — how a row says it belongs to a live session, read one way.
 */
import { describe, it, expect } from 'vitest';

import { isLiveRow, isLiveSummary, liveErrorKey, liveSummaryOf } from '../live-message';

describe('live-message', () => {
  it('recognises a live row by its session stamp, both roles and the delegated request', () => {
    expect(isLiveRow({ type: 'live_turn', live_session_id: 'a' })).toBe(true);
    expect(isLiveRow({ run_id: 'r', live_session_id: 'a', spoken_text: 'hi' })).toBe(true);
    expect(isLiveRow({ run_id: 'r' })).toBe(false);
    expect(isLiveRow({ live_session_id: '' })).toBe(false);
    expect(isLiveRow(undefined)).toBe(false);
  });

  it('recognises the summary by its type and reads its figures tolerantly', () => {
    expect(isLiveSummary({ type: 'live_session_summary' })).toBe(true);
    expect(isLiveSummary({ type: 'live_turn' })).toBe(false);
    expect(
      liveSummaryOf({
        type: 'live_session_summary',
        live_summary: {
          outcome: 'expired',
          duration_seconds: 90,
          delegations: 1,
          voice_turns: 4,
          extensions: 2,
        },
      })
    ).toEqual({
      outcome: 'expired',
      durationSeconds: 90,
      delegations: 1,
      voiceTurns: 4,
      extensions: 2,
      mode: 'delegated',
      relay: null,
      relaySummary: null,
    });
    // The recap of the words when the relay could not run (ADR-301): a
    // string, or null — never an object or an empty line.
    expect(
      liveSummaryOf({
        type: 'live_session_summary',
        live_summary: { mode: 'direct', relay: 'busy', relay_summary: 'Asked for a reminder.' },
      }).relaySummary
    ).toBe('Asked for a reminder.');
    expect(
      liveSummaryOf({
        type: 'live_session_summary',
        live_summary: { mode: 'direct', relay: 'busy', relay_summary: '  ' },
      }).relaySummary
    ).toBeNull();
    // The mode travels with the figures; a row older than it is a delegated session's.
    expect(
      liveSummaryOf({ type: 'live_session_summary', live_summary: { mode: 'direct' } }).mode
    ).toBe('direct');
    // A direct session's relay fate (ADR-301) is read on the closed vocabulary only.
    expect(
      liveSummaryOf({
        type: 'live_session_summary',
        live_summary: { mode: 'direct', relay: 'answered' },
      }).relay
    ).toBe('answered');
    expect(
      liveSummaryOf({ type: 'live_session_summary', live_summary: { relay: 'teleported' } }).relay
    ).toBeNull();
    // An outcome this build cannot label (a newer API) reads as none, never as a raw key.
    expect(
      liveSummaryOf({ type: 'live_session_summary', live_summary: { outcome: 'vanished' } }).outcome
    ).toBeNull();
    expect(liveSummaryOf({ type: 'live_session_summary' })).toEqual({
      outcome: null,
      relay: null,
      relaySummary: null,
      durationSeconds: 0,
      delegations: 0,
      voiceTurns: 0,
      extensions: 0,
      mode: 'delegated',
    });
    expect(liveSummaryOf({ live_summary: { duration_seconds: 'x' } }).durationSeconds).toBe(0);
  });

  it('names a coded start failure by its code and anything else generically', () => {
    expect(liveErrorKey('connector_missing')).toBe('live.error.connector_missing');
    expect(liveErrorKey('instance_busy')).toBe('live.error.instance_busy');
    expect(liveErrorKey('Network request failed')).toBe('live.error.start');
    expect(liveErrorKey(null)).toBe('live.error.start');
  });
});
