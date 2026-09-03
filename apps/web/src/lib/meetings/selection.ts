/**
 * Row selection on the meetings list (ADR-259) — what is specific to meetings.
 *
 * The server skips live captures and processing jobs in a bulk delete; the
 * page refuses to select them in the first place so the count it announces is
 * the count it will delete. The set arithmetic is shared (`lib/selection`).
 */

import type { MeetingStatus, MeetingSummary } from '@/types/meetings';

export { pageSelectionState, toggleId, type PageSelectionState } from '@/lib/selection';

/** Statuses the bulk delete skips (mirrors `bulk.py::_UNDELETABLE`). */
const UNSELECTABLE_STATUSES: readonly MeetingStatus[] = ['recording', 'interrupted', 'processing'];

/** Whether a row may join a bulk delete. */
export function isSelectable(meeting: Pick<MeetingSummary, 'status'>): boolean {
  return !UNSELECTABLE_STATUSES.includes(meeting.status);
}
