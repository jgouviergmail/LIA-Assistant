/**
 * How a chat row says it belongs to a live session (ADR-299), read from the
 * metadata the API archives — one place, so the bubble, the glyph and the
 * summary card agree.
 */
import {
  isLiveOutcome,
  isLiveRelayFate,
  type LiveOutcome,
  type LiveRelayFate,
  type LiveSessionMode,
} from './types';

export const LIVE_TURN_MESSAGE_TYPE = 'live_turn';
export const LIVE_SESSION_SUMMARY_MESSAGE_TYPE = 'live_session_summary';

export interface LiveSummaryFigures {
  outcome: LiveOutcome | null;
  durationSeconds: number;
  delegations: number;
  voiceTurns: number;
  extensions: number;
  /** A DIRECT session archived no exchange: the card counts none (ADR-300 wave 4). */
  mode: LiveSessionMode;
  /** What became of a DIRECT session's words (ADR-301); null on a delegated session. */
  relay: LiveRelayFate | null;
  /** The recap of the words when the relay could not run — so nothing said is lost; null otherwise. */
  relaySummary: string | null;
}

type Metadata = Record<string, unknown> | undefined;

function asNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

/** A row spoken or delegated during a live session (both roles). */
export function isLiveRow(metadata: Metadata): boolean {
  if (!metadata) return false;
  return typeof metadata.live_session_id === 'string' && metadata.live_session_id.length > 0;
}

/** The end-of-session card. */
export function isLiveSummary(metadata: Metadata): boolean {
  return metadata?.type === LIVE_SESSION_SUMMARY_MESSAGE_TYPE;
}

/** The figures of a summary row, tolerant of what an older row may lack. */
export function liveSummaryOf(metadata: Metadata): LiveSummaryFigures {
  // The card's own key (`live_summary`): the origin stamp of a relayed turn
  // writes under `live_session`, so the two never share a shape (ADR-301).
  const session =
    metadata && typeof metadata.live_summary === 'object' && metadata.live_summary !== null
      ? (metadata.live_summary as Record<string, unknown>)
      : {};
  // A row written by a newer API may name an outcome this build cannot label.
  const outcome = isLiveOutcome(session.outcome) ? session.outcome : null;
  return {
    outcome,
    durationSeconds: asNumber(session.duration_seconds),
    delegations: asNumber(session.delegations),
    voiceTurns: asNumber(session.voice_turns),
    extensions: asNumber(session.extensions),
    // A row written before the mode existed is a delegated session's.
    mode: session.mode === 'direct' ? 'direct' : 'delegated',
    relay: isLiveRelayFate(session.relay) ? session.relay : null,
    relaySummary:
      typeof session.relay_summary === 'string' && session.relay_summary.trim()
        ? session.relay_summary.trim()
        : null,
  };
}

/**
 * The refusals a start can name: the API's codes (`domains/live/errors.py`,
 * read by its guard) plus the one the browser raises itself.
 */
export const LIVE_ERROR_CODES = [
  'connector_missing',
  'session_in_progress',
  'instance_busy',
  'mint_rate_limited',
  'provider_refused',
  'voice_unknown',
  'thinking_level_unknown',
  'model_unpriced',
  'mode_unsupported',
  'session_not_found',
  'session_expired',
  'credential_invalid',
  'unsupported_browser',
] as const;

export type LiveErrorCode = (typeof LIVE_ERROR_CODES)[number];

const CODED_ERRORS: ReadonlySet<string> = new Set(LIVE_ERROR_CODES);

/** The i18n key of a start failure: its code when the API named one, else the generic line. */
export function liveErrorKey(error: string | null): string {
  return error && CODED_ERRORS.has(error) ? `live.error.${error}` : 'live.error.start';
}
