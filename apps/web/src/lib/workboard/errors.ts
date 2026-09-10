/**
 * Backend `workboard_*` codes → localized messages (ADR-276).
 *
 * The API reports every guard failure as a stable machine code
 * (`domains/workboard/constants.py::WorkboardError`); this table is the ONLY
 * place they meet a translation key. An unknown code falls back to the generic
 * sentence — a raw `workboard_peer_cannot_edit_field` must never reach a
 * screen, and a code the frontend has not learnt yet is a message it cannot
 * write for the server.
 *
 * TWO families live here, and they are never one table: a REFUSAL answers a
 * request the person just made (`WorkboardError`, toasted), while a RUN
 * FAILURE is what a sweep stored on the ticket hours ago (`RunError`, read on
 * the card and in the panel). Both are codes for the same reason, and
 * `test_frontend_error_keys.py` holds each family to its own table.
 */
import { toast } from 'sonner';

/** Every code the board can answer with, and what it says to a person. */
export const WORKBOARD_ERROR_KEYS: Record<string, string> = {
  workboard_title_required: 'workboard.errors.title_required',
  workboard_title_too_long: 'workboard.errors.title_too_long',
  workboard_description_too_long: 'workboard.errors.description_too_long',
  workboard_comment_required: 'workboard.errors.comment_required',
  workboard_comment_too_long: 'workboard.errors.comment_too_long',
  workboard_depth_exceeded: 'workboard.errors.depth_exceeded',
  workboard_parent_not_owned: 'workboard.errors.parent_not_owned',
  workboard_too_many_tickets: 'workboard.errors.too_many_tickets',
  workboard_too_many_children: 'workboard.errors.too_many_children',
  workboard_assignee_not_connected: 'workboard.errors.assignee_not_connected',
  workboard_cross_account_delegation: 'workboard.errors.cross_account_delegation',
  workboard_peer_cannot_delete: 'workboard.errors.peer_cannot_delete',
  workboard_peer_cannot_edit_field: 'workboard.errors.peer_cannot_edit_field',
  workboard_peer_cannot_reassign: 'workboard.errors.peer_cannot_reassign',
  workboard_run_now_requires_lia: 'workboard.errors.run_now_requires_lia',
  workboard_max_runs_reached: 'workboard.errors.max_runs_reached',
  workboard_answer_required: 'workboard.errors.answer_required',
  workboard_status_invalid: 'workboard.errors.status_invalid',
  workboard_priority_invalid: 'workboard.errors.priority_invalid',
  workboard_dates_inverted: 'workboard.errors.dates_inverted',
  workboard_peers_disabled: 'workboard.errors.peers_disabled',
  workboard_not_found: 'workboard.errors.not_found',
};

/**
 * Why a run ended without an answer — the codes `last_run_error` stores.
 *
 * Written by the sweep (`RunError`), not by a request: the card and the detail
 * panel show these, so the raw string used to be read by a person. The code is
 * the sentence; whatever follows it is a bounded technical message kept as
 * evidence, never as the heading.
 */
export const WORKBOARD_RUN_ERROR_KEYS: Record<string, string> = {
  workboard_assignee_inactive: 'workboard.run_errors.assignee_inactive',
  workboard_empty_answer: 'workboard.run_errors.empty_answer',
  workboard_run_failed: 'workboard.run_errors.run_failed',
  workboard_run_reaped: 'workboard.run_errors.run_reaped',
};

const GENERIC_KEY = 'workboard.errors.generic';
const GENERIC_RUN_KEY = 'workboard.run_errors.generic';

/**
 * The translation key for one backend code.
 *
 * @param code - The `workboard_*` code, or null when the failure had no shape.
 * @returns The key to translate; the generic one for anything unknown.
 */
export function workboardErrorKey(code: string | null): string {
  return (code && WORKBOARD_ERROR_KEYS[code]) || GENERIC_KEY;
}

/** What a failed run says, and what it can show as evidence. */
export interface RunFailure {
  /** The localized sentence — always a sentence, never a code. */
  label: string;
  /** The bounded technical message the code carried, when it carried one. */
  detail: string | null;
}

/**
 * Read `last_run_error` into something a person can be shown.
 *
 * The stored shape is `code` or `code: message`. Only the FIRST separator is
 * read: a timeout's own message contains colons, and re-parsing them would cut
 * the evidence in half.
 *
 * @param t - Translation function from `useTranslation`.
 * @param raw - The stored `last_run_error`, or null.
 * @returns The sentence and its evidence, or null when the run stored nothing.
 */
export function runFailure(t: (key: string) => string, raw: string | null): RunFailure | null {
  const stored = raw?.trim();
  if (!stored) return null;
  const separator = stored.indexOf(': ');
  const code = separator === -1 ? stored : stored.slice(0, separator);
  const detail = separator === -1 ? null : stored.slice(separator + 2).trim() || null;
  const key = WORKBOARD_RUN_ERROR_KEYS[code];
  // A string that is not a code at all is evidence, not a heading: showing it
  // as the sentence is exactly what this function exists to stop.
  if (!key) return { label: t(GENERIC_RUN_KEY), detail: detail ?? stored };
  return { label: t(key), detail };
}

/**
 * Toast the localized message for a backend code.
 *
 * @param t - Translation function from `useTranslation`.
 * @param code - The `workboard_*` code, or null.
 */
export function toastWorkboardError(t: (key: string) => string, code: string | null): void {
  toast.error(t(workboardErrorKey(code)));
}
