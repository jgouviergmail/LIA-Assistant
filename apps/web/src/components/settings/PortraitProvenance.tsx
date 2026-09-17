'use client';

/**
 * What the portrait was compiled from (2026-09-16 design, part B).
 *
 * One line: the journal entries and every source that was USED, each with the
 * count the prompt received — figures from the payload, never computed here
 * (ADR-185). A source the person or the operator switched off is simply
 * absent; a source that could NOT be read is named on a second line, because
 * « I did not look » and « there was nothing » are different answers and only
 * the second may be left implicit (ADR-269's honesty contract).
 *
 * The fragments are joined with the locale's own list grammar
 * (`Intl.ListFormat`), so no locale carries an « and » key.
 */

import type { PortraitProvenance as Provenance } from '@/hooks/useJournals';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

/** The declared order of the sources, the prompt's own. */
const SOURCE_KEYS = ['memories', 'interests', 'habits', 'relation_debriefs'] as const;

export interface PortraitProvenanceProps {
  provenance: Provenance;
  lng: Language;
}

function joinList(parts: string[], lng: Language): string {
  try {
    return new Intl.ListFormat(lng, { style: 'long', type: 'conjunction' }).format(parts);
  } catch {
    return parts.join(', ');
  }
}

export function PortraitProvenance({ provenance, lng }: PortraitProvenanceProps) {
  const { t } = useTranslation(lng, 'translation');

  const used = SOURCE_KEYS.filter(key => provenance.sources[key]?.status === 'used');
  const unavailable = SOURCE_KEYS.filter(key => provenance.sources[key]?.status === 'unavailable');

  const parts = [
    { key: 'entries', count: provenance.journal_entries },
    ...used.map(key => ({ key, count: provenance.sources[key]?.used ?? 0 })),
  ];
  const fragments = parts.map(part => t(`journals.provenance.${part.key}`, { count: part.count }));
  const unavailableNames = unavailable.map(key => t(`journals.provenance.source.${key}`));

  return (
    <div className="space-y-0.5 text-[10px] text-muted-foreground">
      <p
        data-testid="portrait-provenance"
        data-parts={parts.map(part => `${part.key}:${part.count}`).join('|')}
      >
        {t('journals.provenance.compiled_from', { list: joinList(fragments, lng) })}
      </p>
      {unavailable.length > 0 && (
        <p data-testid="portrait-provenance-unavailable" data-sources={unavailable.join('|')}>
          {t('journals.provenance.unavailable', {
            sources: joinList(unavailableNames, lng),
            count: unavailable.length,
          })}
        </p>
      )}
    </div>
  );
}
