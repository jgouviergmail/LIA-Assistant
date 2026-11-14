/**
 * What an import says once it is done: every entry of the file is accounted
 * for, with the exact count the API answered — never a rounded "some".
 */
import { createInstance } from 'i18next';
import { describe, expect, it } from 'vitest';

import { memoryImportSummary, type MemoryImportReport } from '@/lib/memories/import-summary';

/** A real translator whose wording shows the key and the count it was given. */
const language = createInstance();
await language.init({
  lng: 'en',
  resources: {
    en: {
      translation: {
        memories: {
          import_imported: 'imported={{n}}',
          import_already_present: 'already={{n}}',
          import_duplicates: 'duplicates={{n}}',
          import_invalid: 'invalid={{n}}',
        },
      },
    },
  },
});
const t = language.t;

const report = (over: Partial<MemoryImportReport> = {}): MemoryImportReport => ({
  total: 0,
  imported: 0,
  already_present: 0,
  duplicates: 0,
  invalid: 0,
  ...over,
});

describe('memoryImportSummary', () => {
  it('always says how many memories were imported, even none', () => {
    expect(memoryImportSummary(report(), t)).toBe('imported=0');
  });

  it('names each way an entry was left out, with its own count', () => {
    const summary = memoryImportSummary(
      report({ total: 18, imported: 12, already_present: 3, duplicates: 2, invalid: 1 }),
      t
    );

    expect(summary).toBe('imported=12 · already=3 · duplicates=2 · invalid=1');
  });

  it('says nothing of what did not happen', () => {
    expect(memoryImportSummary(report({ total: 5, imported: 4, invalid: 1 }), t)).toBe(
      'imported=4 · invalid=1'
    );
  });
});
