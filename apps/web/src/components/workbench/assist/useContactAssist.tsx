'use client';

/**
 * What LIA can do on an open contact (ADR-372): the list under its bar's last icon, and the answer's
 * place in the detail. What the latest messages say comes with the message that says it: the person
 * ticks what they keep, and the editor opens on it. Nothing reaches the card by itself.
 */
import { UserRoundSearch } from 'lucide-react';
import Link from 'next/link';
import { useState, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { useAuth } from '@/hooks/useAuth';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { ASSIST_PATHS, type ContactValuesAnswer, type ProposedValue } from '@/lib/workbench/assist';
import { contactName, historyMailHref } from '@/lib/workbench/contacts';
import { dayIn, formatDay } from '@/lib/workbench/tasks';
import type { WorkbenchContact } from '@/lib/workbench/types';

import type { AssistOffer } from '../DetailBar';
import { useToolBridges } from '../useToolBridges';
import { AssistPanel } from './AssistPanel';
import { readyLine, remindLine } from './lines';
import { useAssistCall } from './useAssistCall';

export interface ContactAssist extends AssistOffer {
  /** The answer, first in the detail. */
  panel: ReactNode;
}

/** The values found, each with the message that says it. */
function FoundValues({
  lng,
  values,
  onUse,
}: {
  lng: Language;
  values: readonly ProposedValue[];
  onUse: (kept: readonly ProposedValue[]) => void;
}) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const [left, setLeft] = useState<ReadonlySet<number>>(new Set());
  const kept = values.filter((_, index) => !left.has(index));
  const toggled = (index: number) =>
    setLeft(current => {
      const next = new Set(current);
      if (!next.delete(index)) next.add(index);
      return next;
    });
  return (
    <div className="space-y-2">
      <ul className="space-y-2">
        {values.map((found, index) => (
          <li key={`${found.field}:${found.value}`} className="flex items-start gap-2">
            <Checkbox
              id={`found-${index}`}
              className="mt-0.5"
              checked={!left.has(index)}
              onChange={() => toggled(index)}
            />
            <div className="min-w-0 flex-1">
              <label htmlFor={`found-${index}`} className="block break-words">
                <span className="text-muted-foreground">
                  {t(`workbench.assist.contacts.fields.${found.field}`)}
                </span>{' '}
                {found.value}
              </label>
              <Link
                href={historyMailHref(found.message_id, false, lng)}
                className="block truncate text-xs text-primary hover:underline"
              >
                {found.received_at
                  ? `${found.subject} · ${formatDay(dayIn(user?.timezone, new Date(found.received_at)), lng)}`
                  : found.subject}
              </Link>
            </div>
          </li>
        ))}
      </ul>
      <Button
        size="sm"
        aria-disabled={kept.length === 0 || undefined}
        onClick={() => kept.length > 0 && onUse(kept)}
      >
        {t('workbench.assist.contacts.use')}
      </Button>
    </div>
  );
}

/**
 * @param lng - The reader's language.
 * @param contact - The contact read, once it is.
 * @param onFound - Opens the editor on what the person kept; left out for a card they cannot change.
 * @returns The offer of its bar, and the answer's place; nothing while it is being read.
 */
export function useContactAssist(
  lng: Language,
  contact: WorkbenchContact | undefined,
  onFound?: (values: readonly ProposedValue[]) => void
): ContactAssist {
  const { t } = useTranslation(lng);
  const { ask, remind, assists } = useToolBridges(lng);
  const completion = useAssistCall<ContactValuesAnswer>(contact?.id ?? null);
  if (!contact) return { lines: [], panel: null };
  const name = contactName(contact) || t('workbench.contacts.no_name');
  const completes = assists && onFound !== undefined && contact.emails.length > 0;
  return {
    lines: [
      ...(completes
        ? [
            {
              label: t('workbench.assist.contacts.complete'),
              icon: UserRoundSearch,
              onSelect: () => {
                void completion.run(ASSIST_PATHS.contactComplete, { contact_id: contact.id });
              },
            },
          ]
        : []),
      remindLine(t, t('workbench.assist.remind.words.contact', { name }), remind),
      readyLine(t, 'contact', { name }, ask),
    ],
    busy: completion.state.status === 'running',
    panel: onFound && (
      <AssistPanel
        lng={lng}
        title={t('workbench.assist.contacts.complete_title')}
        call={completion}
      >
        {answer => (
          <FoundValues
            lng={lng}
            values={answer.values}
            onUse={kept => {
              onFound(kept);
              completion.stop();
            }}
          />
        )}
      </AssistPanel>
    ),
  };
}
