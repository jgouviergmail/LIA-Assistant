'use client';

/**
 * What LIA can do on an open contact (ADR-372): the list under its bar's last icon, and the answer's
 * place in the detail. What the latest messages say comes with the message that says it: the person
 * ticks what they keep, and the editor opens on it. Nothing reaches the card by itself.
 *
 * Since 2026-11-07 the list also calls the contact through LIA — one line per number, its kind
 * named, where the instance offers telephony and the account's connector is active: the chat opens
 * on the words, unsent, and its own card places the call — and writes to them with LIA, a new
 * message opening on « Write from an instruction ».
 */
import { PenLine, Phone, UserRoundSearch } from '@/lib/icons';
import Link from 'next/link';
import { useState, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { useAuth } from '@/hooks/useAuth';
import { useTelephonyCallable } from '@/hooks/useTelephonyCallable';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { ASSIST_PATHS, type ContactValuesAnswer, type ProposedValue } from '@/lib/workbench/assist';
import { CONTACT_KINDS, contactName, historyMailHref } from '@/lib/workbench/contacts';
import { dayIn, formatDay } from '@/lib/workbench/tasks';
import type { ContactValue, WorkbenchContact } from '@/lib/workbench/types';

import type { AssistOffer, DetailDeed } from '../DetailBar';
import { useToolBridges } from '../useToolBridges';
import { AssistPanel } from './AssistPanel';
import { readyLine, remindLine } from './lines';
import { useAssistCall } from '@/hooks/useAssistCall';

export interface ContactAssist extends AssistOffer {
  /** The answer, first in the detail. */
  panel: ReactNode;
}

/** The values found, each with the message that says it. */
interface NumberToCall {
  value: string;
  /** Its kind, when it names this number alone; else the number names itself. */
  kind: string | null;
}

/** A contact's numbers, each once, named by their kind unless another number shares it. */
function numbersToCall(phones: readonly ContactValue[]): NumberToCall[] {
  const once: ContactValue[] = [];
  for (const phone of phones) {
    if (!once.some(kept => kept.value === phone.value)) once.push(phone);
  }
  const kinds = once.map(phone =>
    phone.type && phone.type !== 'other' && CONTACT_KINDS.phones.includes(phone.type)
      ? phone.type
      : null
  );
  return once.map((phone, index) => {
    const kind = kinds[index];
    const alone = kind !== null && kinds.filter(other => other === kind).length === 1;
    return { value: phone.value, kind: alone ? kind : null };
  });
}

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
  const { ask, remind, assists, offers, go } = useToolBridges(lng);
  const callable = useTelephonyCallable();
  const completion = useAssistCall<ContactValuesAnswer>(contact?.id ?? null);
  if (!contact) return { lines: [], panel: null };
  const name = contactName(contact) || t('workbench.contacts.no_name');
  const completes = assists && onFound !== undefined && contact.emails.length > 0;
  const address = contact.emails[0]?.value;
  const calls: DetailDeed[] = callable
    ? numbersToCall(contact.phones).map(({ value, kind }) => ({
        label: t('workbench.assist.contacts.call', {
          name,
          which: kind ? t(`workbench.contacts.kinds.${kind}`) : value,
        }),
        icon: Phone,
        asks: true,
        onSelect: () => ask(t('workbench.assist.contacts.call_words', { name, number: value })),
      }))
    : [];
  const writes: DetailDeed[] =
    assists && address && offers('compose')
      ? [
          {
            label: t('workbench.assist.contacts.write_to', { name }),
            icon: PenLine,
            onSelect: () => go({ kind: 'compose', to: address, assisted: true }),
          },
        ]
      : [];
  return {
    lines: [
      ...writes,
      ...calls,
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
