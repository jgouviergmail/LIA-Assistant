/**
 * The live session's states, as a pure function (ADR-299, spec A6).
 *
 *   idle → minting → connecting → live ⇄ reconnecting → ending → ended
 *                                   live ⇄ standby → connecting (ADR-329)
 *
 * Asleep (`standby`) the session holds no provider connection and bills
 * nothing; its wake word listens, and a wake opens a NEW connection.
 *
 * Every way a session ends is a NAMED outcome (`LiveOutcome`), decided by the
 * controller and carried to the API's `end`; this module only says which
 * state follows which event, and what a socket close means.
 */
import { LIVE_RECONNECT_ATTEMPTS } from '@/lib/constants';

export type LiveStatus =
  | 'idle'
  | 'minting'
  | 'connecting'
  | 'live'
  | 'reconnecting'
  | 'standby'
  | 'ending'
  | 'ended';

export type LiveEvent =
  | 'start'
  | 'minted'
  | 'setup_complete'
  | 'socket_closed'
  | 'standby'
  | 'wake'
  | 'end'
  | 'failed'
  | 'ended';

export type CloseDecision = 'reconnect' | 'provider_closed' | 'resumption_failed';

const TRANSITIONS: Record<LiveEvent, Partial<Record<LiveStatus, LiveStatus>>> = {
  start: { idle: 'minting', ended: 'minting' },
  minted: { minting: 'connecting' },
  setup_complete: { connecting: 'live', reconnecting: 'live' },
  socket_closed: { connecting: 'reconnecting', live: 'reconnecting' },
  // From `connecting` too: a wake the provider refused twice goes back to sleep.
  standby: { live: 'standby', connecting: 'standby' },
  wake: { standby: 'connecting' },
  end: {
    minting: 'ending',
    connecting: 'ending',
    live: 'ending',
    reconnecting: 'ending',
    standby: 'ending',
    ending: 'ending',
  },
  failed: {
    minting: 'ending',
    connecting: 'ending',
    live: 'ending',
    reconnecting: 'ending',
    standby: 'ending',
    ending: 'ending',
  },
  ended: {
    idle: 'ended',
    minting: 'ended',
    connecting: 'ended',
    live: 'ended',
    reconnecting: 'ended',
    standby: 'ended',
    ending: 'ended',
    ended: 'ended',
  },
};

/** The state after `event`, or the same state when the event means nothing there. */
export function transition(status: LiveStatus, event: LiveEvent): LiveStatus {
  return TRANSITIONS[event][status] ?? status;
}

/** What to do when the socket closed while the session should go on. */
export function closeDecision(
  code: number,
  resumptionHandle: string | null,
  attempts: number
): CloseDecision {
  if (code === 1000) return 'provider_closed';
  if (!resumptionHandle) return 'provider_closed';
  return attempts >= LIVE_RECONNECT_ATTEMPTS ? 'resumption_failed' : 'reconnect';
}

/** Longest technical detail sent with the end (the API's own bound). */
export const LIVE_END_DETAIL_MAX_CHARS = 200;

/**
 * The words a connect rejects with when the socket closed before the setup:
 * the code, and the provider's reason when it gave one — what the API's log
 * shows as the session's `detail`.
 */
export function closeWords(code: number, reason: string): string {
  const trimmed = reason.trim();
  return trimmed ? `live_socket_closed_${code}: ${trimmed}` : `live_socket_closed_${code}`;
}

/** The provider's own word on a close, for the API's log: `close 1007: Request contains…`. */
export function closeDetail(code: number, reason: string): string {
  const words = reason.trim();
  return (words ? `close ${code}: ${words}` : `close ${code}`).slice(0, LIVE_END_DETAIL_MAX_CHARS);
}

/** The API no longer holds this session (404): superseded, or past its cap and grace. */
export function isSessionGone(error: unknown): boolean {
  return (
    typeof error === 'object' && error !== null && (error as { status?: unknown }).status === 404
  );
}

/** True while a session claims the microphone and the chat composer — asleep included. */
export function isSessionOpen(status: LiveStatus): boolean {
  return (
    status === 'connecting' ||
    status === 'live' ||
    status === 'reconnecting' ||
    status === 'standby'
  );
}
