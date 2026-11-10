/**
 * Eligibility for selective meeting deletion (ADR-259).
 *
 * The server skips live captures and processing jobs in a bulk delete; the
 * page's individual delete action refuses them before sending an id.
 * The server remains authoritative if a row changes after it was displayed.
 */

import type { MeetingStatus, MeetingSummary } from '@/types/meetings';

export { pageSelectionState, toggleId, type PageSelectionState } from '@/lib/selection';

/** Statuses the bulk delete skips (mirrors `bulk.py::_UNDELETABLE`). */
const UNSELECTABLE_STATUSES: readonly MeetingStatus[] = ['recording', 'interrupted', 'processing'];

/** Whether a row may join a bulk delete. */
export function isSelectable(meeting: Pick<MeetingSummary, 'status'>): boolean {
  return !UNSELECTABLE_STATUSES.includes(meeting.status);
}
