/**
 * live-message — how a row says it belongs to a live session, read one way.
 */
import { describe, it, expect } from 'vitest';

import {
  isLiveRow,
  isLiveSummary,
  liveErrorKey,
  liveSummaryOf,
  wakeRefusalKey,
} from '../live-message';

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
      standbys: 0,
      standbyRecaps: [],
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
      standbys: 0,
      standbyRecaps: [],
    });
    expect(liveSummaryOf({ live_summary: { duration_seconds: 'x' } }).durationSeconds).toBe(0);
  });

  it("reads a session's sleeps and the recaps its standbys could not relay (ADR-329)", () => {
    const figures = liveSummaryOf({
      type: 'live_session_summary',
      live_summary: {
        mode: 'direct',
        standbys: 3,
        standby_recaps: [' Asked for the weather. ', '', 42, null, 'Asked for a reminder.'],
      },
    });
    expect(figures.standbys).toBe(3);
    // Only non-blank strings, trimmed: a malformed entry never reaches the card.
    expect(figures.standbyRecaps).toEqual(['Asked for the weather.', 'Asked for a reminder.']);
    expect(liveSummaryOf({ live_summary: { standby_recaps: 'not a list' } }).standbyRecaps).toEqual(
      []
    );
  });

  it('names a coded wake refusal by its code and anything else as a wake that failed', () => {
    expect(wakeRefusalKey('mint_rate_limited')).toBe('live.error.mint_rate_limited');
    expect(wakeRefusalKey('instance_busy')).toBe('live.error.instance_busy');
    expect(wakeRefusalKey(null)).toBe('live.wake.refused');
    expect(wakeRefusalKey('live_socket_closed_1011')).toBe('live.wake.refused');
  });

  it('names a coded start failure by its code and anything else generically', () => {
    expect(liveErrorKey('connector_missing')).toBe('live.error.connector_missing');
    expect(liveErrorKey('instance_busy')).toBe('live.error.instance_busy');
    expect(liveErrorKey('Network request failed')).toBe('live.error.start');
    expect(
      liveErrorKey(
        'Error: live_socket_closed_1008: The provided API key has an IP address restriction.'
      )
    ).toBe('live.error.key_ip_restricted');
    expect(liveErrorKey(null)).toBe('live.error.start');
  });
});
