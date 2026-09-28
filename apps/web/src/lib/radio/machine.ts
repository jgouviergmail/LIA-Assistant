/**
 * The radio player's states, as a pure function (ADR-324).
 *
 *   idle → starting → waiting ⇄ playing ⇄ paused → ending → ended
 *
 * `waiting` is the station's music between two segments (the next one is still
 * being produced); `playing` is a segment on air. Every event that means
 * nothing in a state leaves it unchanged, so a late network answer can never
 * resurrect a stopped player.
 */

export type RadioStatus =
  | 'idle'
  | 'starting'
  | 'waiting'
  | 'playing'
  | 'paused'
  | 'ending'
  | 'ended';

export type RadioEvent =
  | 'start'
  | 'started'
  | 'segment_started'
  | 'drained'
  | 'paused'
  | 'resumed_segment'
  | 'resumed_waiting'
  | 'stop'
  | 'ended';

const TRANSITIONS: Record<RadioEvent, Partial<Record<RadioStatus, RadioStatus>>> = {
  start: { idle: 'starting', ended: 'starting' },
  started: { starting: 'waiting' },
  segment_started: { waiting: 'playing', playing: 'playing' },
  drained: { playing: 'waiting' },
  paused: { waiting: 'paused', playing: 'paused' },
  resumed_segment: { paused: 'playing' },
  resumed_waiting: { paused: 'waiting' },
  stop: { starting: 'ending', waiting: 'ending', playing: 'ending', paused: 'ending' },
  ended: {
    starting: 'ended',
    waiting: 'ended',
    playing: 'ended',
    paused: 'ended',
    ending: 'ended',
  },
};

const ON_AIR: ReadonlySet<RadioStatus> = new Set(['starting', 'waiting', 'playing', 'paused']);

/** The state after `event`, or the same state when the event means nothing there. */
export function transition(status: RadioStatus, event: RadioEvent): RadioStatus {
  return TRANSITIONS[event][status] ?? status;
}

/** True while a session runs: the antenna holds the audio output and the wake word stands aside. */
export function isOnAir(status: RadioStatus): boolean {
  return ON_AIR.has(status);
}
