/**
 * The address book's own actions on a relationship (owner request 2026-10-21).
 *
 * One action per reachable value of the contact card: write to each email,
 * find the route to each postal address, have LIA call each number — the last
 * only while the account holds an active telephony connector, since a call
 * nothing can place is a promise the sheet cannot keep. Each one
 * is a `?draft=` deep link — it PREFILLS the composer and never sends: the
 * person completes the subject or the purpose and presses send, because
 * writing to or calling someone never leaves on a click.
 */

import type { TFunction } from 'i18next';
import { Mail, PhoneOutgoing, Route, type LucideIcon } from 'lucide-react';

import type { ContactCard, ContactValue } from '@/hooks/useRelations';

/** One quick action on a relationship: its button label and the request it prefills. */
export interface QuickAction {
  key: string;
  icon: LucideIcon;
  label: string;
  draft: string;
}

/** What a value of the contact card lets the person do. */
export type ContactActionKind = 'email' | 'route' | 'call';

/** The actions of one kind, in the card's order — one column on the sheet. */
export interface QuickActionColumn {
  kind: ContactActionKind;
  actions: QuickAction[];
}

/**
 * Each provider value on one line, once.
 *
 * A postal address often spans several lines, and the same mailbox can be
 * stored twice under two labels: one button per distinct value, whatever the
 * provider's layout.
 */
function distinctValues(values: ContactValue[]): string[] {
  const flat = values.map(entry => entry.value.replace(/\s+/g, ' ').trim()).filter(Boolean);
  return [...new Set(flat)];
}

/**
 * The actions a contact card offers, one column per kind (owner request
 * 2026-10-21: the buttons of one kind stand in one column).
 *
 * @param card - The address-book entry, or null when none was read.
 * @param t - The reader's translation function.
 * @param options.telephony - Whether the account holds an active telephony
 *   connector: without one, no number is offered a call.
 * @returns Emails, then postal addresses, then phone numbers — only the kinds
 *   the card holds, so no column is ever empty.
 */
export function contactQuickActions(
  card: ContactCard | null,
  t: TFunction,
  { telephony }: { telephony: boolean }
): QuickActionColumn[] {
  if (!card) return [];
  const columns: QuickActionColumn[] = [
    {
      kind: 'email',
      actions: distinctValues(card.emails).map(email => ({
        key: `email:${email}`,
        icon: Mail,
        label: t('relations.action_email', { email }),
        draft: t('relations.action_email_prefill', { email }),
      })),
    },
    {
      kind: 'route',
      actions: distinctValues(card.addresses).map(address => ({
        key: `route:${address}`,
        icon: Route,
        label: t('relations.action_route', { address }),
        draft: t('relations.action_route_prefill', { address }),
      })),
    },
    {
      kind: 'call',
      actions: (telephony ? distinctValues(card.phones) : []).map(phone => ({
        key: `call:${phone}`,
        icon: PhoneOutgoing,
        label: t('relations.action_lia_call', { phone }),
        draft: t('relations.action_lia_call_prefill', { phone }),
      })),
    },
  ];
  return columns.filter(column => column.actions.length > 0);
}
