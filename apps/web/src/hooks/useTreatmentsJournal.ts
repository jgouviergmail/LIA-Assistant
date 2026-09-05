'use client';

/**
 * useTreatmentsJournal — what LIA looked at (ADR-263, lot 4).
 *
 * The second of the two transparency registers, read through the same rhythm
 * as the first (`useRegisterJournal`). Its filter is a CAPABILITY rather than
 * an outcome: "did it read my emails" is the question this register answers,
 * and "did it succeed" is the one the other answers.
 *
 * The filter travels to the SERVER, so the total describes the list on screen.
 */

import {
  REGISTER_PAGE_SIZE,
  useRegisterJournal,
  type UseRegisterJournalResult,
} from '@/hooks/useRegisterJournal';
import type { TreatmentEntry } from '@/types/treatments';

/** Rows per request — the same rhythm as the action register. */
export const TREATMENTS_PAGE_SIZE = REGISTER_PAGE_SIZE;

export type UseTreatmentsJournalResult = UseRegisterJournalResult<TreatmentEntry>;

/**
 * Read the consultation register.
 *
 * @param toolName - Restrict to one capability, or every capability.
 */
export function useTreatmentsJournal(toolName?: string): UseTreatmentsJournalResult {
  return useRegisterJournal<TreatmentEntry>(
    (offset, limit) =>
      `/effects/treatments/journal?offset=${offset}&limit=${limit}` +
      (toolName ? `&tool_name=${encodeURIComponent(toolName)}` : ''),
    toolName ?? 'all',
    'useTreatmentsJournal'
  );
}
