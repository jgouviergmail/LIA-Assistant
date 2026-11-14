import type { TFunction } from 'i18next';

/**
 * What became of every entry of an imported export (`POST /memories/import`).
 * The counts are exact and add up to `total`: nothing of the file is silently
 * dropped.
 */
export interface MemoryImportReport {
  /** Every entry the file held. */
  total: number;
  /** Memories created. */
  imported: number;
  /** Entries whose content the account already held. */
  already_present: number;
  /** Entries whose content the file itself already held. */
  duplicates: number;
  /** Entries the write bounds refuse (too long, unknown category…). */
  invalid: number;
}

/**
 * The one line an import ends on: how many memories were imported — always,
 * even none — then each way an entry was left out, with its own count. What
 * did not happen is not said.
 *
 * @param report - The API's answer.
 * @param t - The screen's translator.
 * @returns The line, in the language of the screen.
 */
export function memoryImportSummary(report: MemoryImportReport, t: TFunction): string {
  const left: [string, number][] = [
    ['memories.import_already_present', report.already_present],
    ['memories.import_duplicates', report.duplicates],
    ['memories.import_invalid', report.invalid],
  ];
  return [
    t('memories.import_imported', { n: report.imported }),
    ...left.filter(([, count]) => count > 0).map(([key, count]) => t(key, { n: count })),
  ].join(' · ');
}
