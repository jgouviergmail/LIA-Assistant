/**
 * The address book's own actions on a relationship (owner requests 2026-10-21
 * and 2026-10-29).
 *
 * One entry per KIND of reachable value on the contact card: write to an
 * email, find the route to a postal address, have LIA call a number — the last
 * only while the account holds an active telephony connector, since a call
 * nothing can place is a promise the sheet cannot keep.
 *
 * An entry's label is a short verb that never carries the value. It once did
 * (« Itinéraire vers 12 rue… »), so the DATA sized every button, and each
 * relationship laid its actions out differently at each width (owner report
 * 2026-10-29). The values travel as the entry's TARGETS, each with the address
 * book's own labels (home, work…): one target acts directly, several open a
 * menu that lists them.
 *
 * Every target is a `?draft=` deep link: it PREFILLS the composer and never
 * sends — the person completes the subject or the purpose and presses send,
 * because writing to or calling someone never leaves on a click.
 */

import type { TFunction } from 'i18next';
import { Mail, PhoneOutgoing, Route, type LucideIcon } from 'lucide-react';

import type { ContactCard, ContactValue } from '@/hooks/useRelations';
import { localizeContactLabel } from '@/lib/relations/contact-label';

/** One quick action on a relationship: its button label and the request it prefills. */
export interface QuickAction {
  key: string;
  icon: LucideIcon;
  label: string;
  draft: string;
}

/** What a value of the contact card lets the person do. */
export type ContactActionKind = 'email' | 'route' | 'call';

/** One value an entry reaches, and the request it prefills. */
export interface ContactActionTarget {
  /** Unique within the sheet: the kind and the one-line value. */
  key: string;
  /** The value on one line, as the menu shows it. */
  value: string;
  /** The address book's labels for this value, localized — empty when it stored none. */
  tags: string[];
  /** The request the composer is prefilled with. */
  draft: string;
}

/** One entry of the action bar: a kind, its short label and the values it reaches. */
export interface ContactActionGroup {
  kind: ContactActionKind;
  icon: LucideIcon;
  /** The same short label whatever the values. */
  label: string;
  /** Never empty: one acts directly, several open a menu. */
  targets: ContactActionTarget[];
}

/** How each kind reads the card and words its request, in the card's order. */
const KINDS: ReadonlyArray<{
  kind: ContactActionKind;
  icon: LucideIcon;
  values: (card: ContactCard) => ContactValue[];
  label: string;
  prefill: (t: TFunction, value: string) => string;
}> = [
  {
    kind: 'email',
    icon: Mail,
    values: card => card.emails,
    label: 'relations.action_email',
    prefill: (t, email) => t('relations.action_email_prefill', { email }),
  },
  {
    kind: 'route',
    icon: Route,
    values: card => card.addresses,
    label: 'relations.action_route',
    prefill: (t, address) => t('relations.action_route_prefill', { address }),
  },
  {
    kind: 'call',
    icon: PhoneOutgoing,
    values: card => card.phones,
    label: 'relations.action_lia_call',
    prefill: (t, phone) => t('relations.action_lia_call_prefill', { phone }),
  },
];

/**
 * Each provider value on one line, once, with every label it was stored under.
 *
 * A postal address often spans several lines, and the same mailbox can be
 * stored twice under two labels: one target per distinct value, whatever the
 * provider's layout, and neither label lost.
 */
function distinctValues(values: ContactValue[], t: TFunction): Map<string, string[]> {
  const byValue = new Map<string, string[]>();
  for (const entry of values) {
    const value = entry.value.replace(/\s+/g, ' ').trim();
    if (!value) continue;
    const tags = byValue.get(value) ?? [];
    const tag = localizeContactLabel(t, entry.label);
    byValue.set(value, tag && !tags.includes(tag) ? [...tags, tag] : tags);
  }
  return byValue;
}

/**
 * The entries a contact card offers, one per kind it holds.
 *
 * @param card - The address-book entry, or null when none was read.
 * @param t - The reader's translation function.
 * @param options.telephony - Whether the account holds an active telephony
 *   connector: without one, no number is offered a call.
 * @returns Emails, then postal addresses, then phone numbers — only the kinds
 *   the card holds, so no entry is ever empty.
 */
export function contactActionGroups(
  card: ContactCard | null,
  t: TFunction,
  { telephony }: { telephony: boolean }
): ContactActionGroup[] {
  if (!card) return [];
  return KINDS.flatMap(spec => {
    if (spec.kind === 'call' && !telephony) return [];
    const targets = [...distinctValues(spec.values(card), t)].map(([value, tags]) => ({
      key: `${spec.kind}:${value}`,
      value,
      tags,
      draft: spec.prefill(t, value),
    }));
    if (targets.length === 0) return [];
    return [{ kind: spec.kind, icon: spec.icon, label: t(spec.label), targets }];
  });
}
