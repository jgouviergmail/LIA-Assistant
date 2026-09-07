'use client';

/**
 * InitiativeJournal — what LIA did without being asked.
 *
 * A fourth reading, not a fourth register. ADR-263 settled that an ACTION and a
 * CONSULTATION are different objects and must not share one list; an
 * initiative is neither — it is an ORIGIN. A briefing that reads your mail is a
 * consultation; a heartbeat that writes to you is an action. So this view
 * stacks the two registers, each filtered to the one authorship that belongs to
 * nobody's request.
 *
 * Why a separate tab rather than a mixed list: a sweep runs on its own
 * schedule and can outnumber by far the handful of things a person actually
 * asked for. Measured 2026-09-07 on production, over fourteen days: 319
 * heartbeat runs against 22 conversational turns. Merged, the lines that matter
 * would be unreadable.
 *
 * And the partition is watertight in the other direction too: `mine` holds
 * everything the person set in motion — what they typed, the routines they
 * wrote, the sub-agents those delegated to — so nothing moves out of the two
 * lists where their owner has always found it.
 */

import { useTranslation } from 'react-i18next';

import { EffectsJournal } from '@/components/effects/EffectsJournal';
import { TreatmentsJournal } from '@/components/effects/TreatmentsJournal';

export interface InitiativeJournalProps {
  /** Current URL locale segment (drives date/time formatting). */
  lng: string;
}

export function InitiativeJournal({ lng }: InitiativeJournalProps) {
  const { t } = useTranslation();

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">{t('registers.initiative_description')}</p>

      {/* The wording is handed DOWN rather than stacked on top: each journal
          renders its own header, so an outer heading here gave every list TWO
          titles — « Actions menées d'elle-même » above « Journal des actions »,
          « Sources consultées d'elle-même » above « Ce que LIA a consulté » —
          and two <h2> for one list (reported from the dev instance,
          2026-09-07). One heading each, saying what THIS tab holds. */}
      <EffectsJournal
        lng={lng}
        origin="initiative"
        heading={{
          title: t('registers.initiative_actions'),
          description: t('registers.initiative_actions_description'),
        }}
      />

      <TreatmentsJournal
        lng={lng}
        origin="initiative"
        heading={{
          title: t('registers.initiative_consultations'),
          description: t('registers.initiative_consultations_description'),
        }}
      />
    </div>
  );
}
