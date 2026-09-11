'use client';

import { CalendarCheck, CalendarClock } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Disclosure } from '@/components/ui/disclosure';
import { RefusalSwitches } from '@/components/settings/RefusalSwitches';

/**
 * At which anticipated instants LIA may come back (ADR-281).
 *
 * A distinct question from the source switches above it, and the panel keeps
 * them apart on purpose: the sources answer « what may LIA interrupt me
 * ABOUT », these answer « at which MOMENTS may LIA come back to me ». Folding
 * them into one list would offer two levels of switch for one effect.
 *
 * The list itself is the shared `RefusalSwitches`. What is specific here is the
 * vocabulary, the icons, and the meaning of a requirement: for a kind it is a
 * connector this account does not have — the server narrows it, since only the
 * server knows what is connected.
 */
export interface MomentKindSwitchesProps {
  /** Every kind, in display order (server-published). */
  allKinds: string[];
  /** Kinds the reader currently refuses. */
  disabledKinds: string[];
  /** What each kind is still waiting for, already narrowed by the server. */
  kindDependencies?: Record<string, string[]>;
  /** True while a write is in flight. */
  updating: boolean;
  /** Receives the FULL replacement refusal set. */
  onChange: (disabled: string[]) => void;
}

/** Icon per kind. An unlisted kind still renders, with a neutral glyph. */
const KIND_ICONS: Record<string, LucideIcon> = {
  event_followup: CalendarCheck,
};

export function MomentKindSwitches({
  allKinds,
  disabledKinds,
  kindDependencies,
  updating,
  onChange,
}: MomentKindSwitchesProps) {
  const { t } = useTranslation();

  return (
    <RefusalSwitches
      items={allKinds}
      refused={disabledKinds}
      unmetRequirements={kindDependencies}
      labelFor={kind => t(`moments.kind_${kind}`)}
      // A requirement is a connector category, and the source vocabulary
      // already names those on this very screen — so the two lists say
      // "Calendar" with the same word.
      requirementLabelFor={requirement => t(`heartbeat.source_${requirement}`)}
      // NOT the source switches' note. Theirs reads « …, which you have
      // switched off », true of a sibling source a reader refused and false
      // here: a kind waits on a connector the account never had, so that
      // sentence would tell someone they turned off a calendar they never
      // connected.
      requiresNote={requirements =>
        t('moments.requires_connector', { sources: requirements.join(', ') })
      }
      icons={KIND_ICONS}
      idPrefix="moment-kind"
      updating={updating}
      onChange={onChange}
    />
  );
}

/**
 * The whole section, fold included, so the settings panel gets one line.
 *
 * Rendered only when the deployment publishes a vocabulary: an instance with
 * the capability off has nothing to offer here, and an empty fold reads as a
 * feature that is broken rather than absent.
 */
export function MomentKindsSection({
  allKinds,
  disabledKinds,
  kindDependencies,
  updating,
  onChange,
}: MomentKindSwitchesProps) {
  const { t } = useTranslation();
  if (allKinds.length === 0) return null;

  return (
    <div className="border-t pt-4">
      <Disclosure
        icon={CalendarClock}
        title={t('moments.settings_title')}
        badge={disabledKinds.length > 0 ? disabledKinds.length : undefined}
      >
        <p className="mb-2 text-xs text-muted-foreground">{t('moments.settings_description')}</p>
        <MomentKindSwitches
          allKinds={allKinds}
          disabledKinds={disabledKinds}
          kindDependencies={kindDependencies}
          updating={updating}
          onChange={onChange}
        />
      </Disclosure>
    </div>
  );
}
