'use client';

import type { ChangeEvent } from 'react';
import type { TFunction } from 'i18next';

import type { MemoryLimits } from '@/hooks/useMemories';
import { memoryImportSummary, type MemoryImportReport } from '@/lib/memories/import-summary';

interface Toast {
  success: (message: string) => void;
  info: (message: string) => void;
  error: (message: string) => void;
}

/**
 * Bringing a memories export back, from the memories toolbar.
 *
 * The file picked is sent as it is — the API reads the two formats its own
 * export writes — and the answer is said whole: how many were imported, how
 * many were already there, how many were left out and why. A file larger than
 * the bound the API publishes is not sent at all; any other refusal is the
 * API's own sentence, in the person's language.
 *
 * @param importMemories - Sends one file and answers what became of its entries.
 * @param limits - The bounds the API publishes; undefined before the list answers.
 * @param toast - Where the outcome is said.
 * @param t - The screen's translator.
 * @returns The change handler of the file input the screen draws.
 */
export function useMemoryImportAction(
  importMemories: (file: File) => Promise<MemoryImportReport | undefined>,
  limits: MemoryLimits | undefined,
  toast: Toast,
  t: TFunction
): (event: ChangeEvent<HTMLInputElement>) => void {
  const send = async (file: File) => {
    const maxKilobytes = limits?.import_max_file_kb;
    if (maxKilobytes !== undefined && file.size > maxKilobytes * 1024) {
      toast.error(t('memories.import_too_large', { kilobytes: maxKilobytes }));
      return;
    }
    try {
      const report = await importMemories(file);
      if (!report) return;
      const summary = memoryImportSummary(report, t);
      // A file that brought nothing new is said, never called a success.
      if (report.imported > 0) toast.success(summary);
      else toast.info(summary);
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : t('memories.import_failed'));
    }
  };

  return (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Emptied at once: the same file picked again is a new choice, not no change.
    event.target.value = '';
    if (file) void send(file);
  };
}
