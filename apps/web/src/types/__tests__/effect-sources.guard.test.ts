/**
 * Every authorship a register row can carry has a translated badge.
 *
 * Found by a cold review rather than by a test, which is the point of this
 * file: `proactive` was added to the backend enum, rows started arriving with
 * it, and the badge rendered `effects.journal.source.proactive` — the raw key,
 * to the user. Nothing failed, because no test rendered a proactive row.
 *
 * The list is a runtime constant so the type can be derived from it and this
 * guard can iterate it. A union type alone is invisible at runtime, which is
 * exactly why the gap could exist.
 */

import { describe, expect, it } from 'vitest';

import de from '../../../locales/de/translation.json';
import en from '../../../locales/en/translation.json';
import es from '../../../locales/es/translation.json';
import fr from '../../../locales/fr/translation.json';
import italian from '../../../locales/it/translation.json';
import zh from '../../../locales/zh/translation.json';
import { EFFECT_SOURCES } from '@/types/effects';

/** All six, not a sample: a badge missing in Italian is a badge missing. */
const LOCALES: ReadonlyArray<readonly [string, Record<string, unknown>]> = [
  ['en', en as Record<string, unknown>],
  ['fr', fr as Record<string, unknown>],
  ['de', de as Record<string, unknown>],
  ['es', es as Record<string, unknown>],
  ['it', italian as Record<string, unknown>],
  ['zh', zh as Record<string, unknown>],
];

function sourceLabels(bundle: Record<string, unknown>): Record<string, string> {
  const effects = bundle.effects as { journal?: { source?: Record<string, string> } } | undefined;
  return effects?.journal?.source ?? {};
}

describe('effect source badges', () => {
  it.each(LOCALES)('names every authorship in %s', (_lng, bundle) => {
    const labels = sourceLabels(bundle);
    for (const source of EFFECT_SOURCES) {
      expect(labels[source], `no badge for "${source}"`).toBeTruthy();
    }
  });

  it.each(LOCALES)(
    'keeps no label for an authorship that no longer exists (%s)',
    (_lng, bundle) => {
      // The other direction: a label kept after its source was removed reads
      // as vocabulary the register still uses.
      const labels = sourceLabels(bundle);
      expect(Object.keys(labels).sort()).toEqual([...EFFECT_SOURCES].sort());
    }
  );
});
