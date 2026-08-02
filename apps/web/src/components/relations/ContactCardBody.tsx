'use client';

/**
 * The address-book entry of a relationship, in full.
 *
 * Its own module rather than a block inside `RelationProviderSections`: a card
 * that shows two fields out of ten is a card the reader stops trusting, so this
 * renders every block the provider stored — and that is enough code to deserve
 * a file of its own.
 *
 * Three rules the layout encodes:
 *
 * - **an empty block is not rendered.** Nothing here says "no postal address":
 *   `relations`, `links`, `important_dates` and `messaging` simply do not exist
 *   outside Google, and a placeholder would read as "the address book holds
 *   nothing" — a negative nobody verified (ADR-184).
 * - **provider labels are translated when we know them, shown as-is when we do
 *   not.** An address book holds custom labels; inventing a translation for
 *   "Maison de campagne" is not an option, and dropping it loses information.
 * - **one column, always.** These are labelled values of unpredictable length
 *   (a postal address, a URL); a two-column grid on a 320 px screen either
 *   overflows or truncates, and a truncated address is a wrong address.
 */

import {
  AtSign,
  BriefcaseBusiness,
  Cake,
  CalendarHeart,
  Link2,
  type LucideIcon,
  MapPin,
  MessageCircle,
  Phone,
  Quote,
  Users,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { partialDateLabel } from '@/lib/briefing-utils';
import type { ContactCard, ContactValue } from '@/hooks/useRelations';

/** Only these two schemes are turned into a link — `javascript:` never is. */
const SAFE_LINK = /^https?:\/\//i;

/**
 * Localize a provider label, keeping the provider's own word as a fallback.
 *
 * `home`, `work`, `spouse`, `anniversary`… are vocabulary, not prose, and the
 * six locales carry the ones we know. Anything else is what the user typed into
 * their address book and is shown untouched.
 */
function useLabel(): (label: string | null) => string | null {
  const { t } = useTranslation();
  return (label: string | null) => {
    if (!label) return null;
    const key = label.trim().toLowerCase();
    return t(`relations.contact_label.${key}`, { defaultValue: label });
  };
}

/** One labelled value of the contact card. */
function ContactValueRow({
  icon: Icon,
  value,
  label,
  href,
}: {
  icon: LucideIcon;
  value: string;
  label: string | null;
  href?: string;
}) {
  return (
    <p className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm text-foreground/90">
      <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
      {/* `break-words`, NOT `break-all`: the same row now carries mailboxes and
          URLs (one long unbreakable token, which must be split or it pushes the
          card off a 320 px screen) AND postal addresses and people's names,
          which `break-all` would chop mid-word — "12 rue des Li/las". This
          wraps on spaces first and only splits a token that cannot fit alone. */}
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="min-w-0 break-words underline decoration-dotted underline-offset-2 hover:text-foreground"
        >
          {value}
        </a>
      ) : (
        // `min-w-0` is what makes `break-words` reachable at all: a flex item
        // defaults to `min-width: auto`, so its min-content width stays the
        // full unbroken token and the row overflows before wrapping is ever
        // considered. (`break-all` shrank min-content by itself — which is why
        // dropping it without this would have traded one bug for another.)
        <span className="min-w-0 break-words">{value}</span>
      )}
      {label && (
        <span className="rounded-full bg-muted px-2 py-px text-[10px] font-medium uppercase text-muted-foreground">
          {label}
        </span>
      )}
    </p>
  );
}

/** One block of labelled values — rendered only when the provider stored some. */
function ContactBlock({
  icon,
  values,
  format,
  linkify = false,
}: {
  icon: LucideIcon;
  values: ContactValue[];
  format?: (value: string) => string;
  linkify?: boolean;
}) {
  const translate = useLabel();
  if (values.length === 0) return null;
  return (
    <>
      {values.map((entry, index) => (
        <ContactValueRow
          // The provider allows the same value twice under two labels, so the
          // value alone is not a key.
          key={`${entry.value}-${entry.label ?? ''}-${index}`}
          icon={icon}
          value={format ? format(entry.value) : entry.value}
          label={translate(entry.label)}
          href={linkify && SAFE_LINK.test(entry.value) ? entry.value : undefined}
        />
      ))}
    </>
  );
}

/**
 * True when the address book holds nothing but a name.
 *
 * A predicate rather than a chain of `&&` inside the component: it is the one
 * place allowed to say "there is nothing here", and it must be readable enough
 * that adding a block to the card without adding it here looks wrong.
 */
function isBlankCard(card: ContactCard): boolean {
  const texts = [card.nickname, card.organization, card.occupation, card.birthday, card.biography];
  const lists = [
    card.emails,
    card.phones,
    card.addresses,
    card.relations,
    card.links,
    card.important_dates,
    card.messaging,
  ];
  return texts.every(text => !text) && lists.every(list => list.length === 0);
}

/** Nickname and job line — what identifies the person before their contacts. */
function CardIdentity({ card }: { card: ContactCard }) {
  const { t } = useTranslation();
  const identity = [card.occupation, card.organization].filter(Boolean).join(' · ');
  if (!card.nickname && !identity) return null;
  return (
    // The job line leads: it is what a reader recognises a person by once the
    // name is already in the header above. The nickname follows it, quieter.
    <div className="flex flex-col gap-0.5">
      {identity && (
        <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <BriefcaseBusiness className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
          <span className="min-w-0 break-words">{identity}</span>
        </p>
      )}
      {card.nickname && (
        <p className="text-xs text-muted-foreground">
          {t('relations.contact_nickname', { name: card.nickname })}
        </p>
      )}
    </div>
  );
}

/**
 * Everything the address book holds about this person.
 *
 * @param card - The provider-backed contact card.
 * @param locale - BCP-47 locale, for the dates the card carries.
 */
export function ContactCardBody({ card, locale }: { card: ContactCard; locale: string }) {
  const { t } = useTranslation();
  const date = (value: string) => partialDateLabel(locale, value);

  const hasReach = card.emails.length + card.phones.length + card.addresses.length > 0;
  const hasDates = Boolean(card.birthday) || card.important_dates.length > 0;
  const hasTies = card.relations.length + card.links.length + card.messaging.length > 0;

  return (
    <div className="flex flex-col gap-3">
      <CardIdentity card={card} />
      {/* Grouped rather than piled: an address book answers three different
          questions — how do I reach them, which dates matter, who and what are
          they tied to. One flat stack of rows made the reader scan for the
          boundary between them; a bordered group per question shows it. */}
      <ContactGroup show={hasReach}>
        <ContactBlock icon={AtSign} values={card.emails} />
        <ContactBlock icon={Phone} values={card.phones} />
        <ContactBlock icon={MapPin} values={card.addresses} />
      </ContactGroup>
      <ContactGroup show={hasDates}>
        {card.birthday && (
          <ContactValueRow
            icon={Cake}
            value={date(card.birthday)}
            label={t('relations.contact_label.birthday')}
          />
        )}
        <ContactBlock icon={CalendarHeart} values={card.important_dates} format={date} />
      </ContactGroup>
      <ContactGroup show={hasTies}>
        <ContactBlock icon={Users} values={card.relations} />
        <ContactBlock icon={Link2} values={card.links} linkify />
        <ContactBlock icon={MessageCircle} values={card.messaging} />
      </ContactGroup>
      {card.biography && (
        <p className="flex gap-2 rounded-lg border-l-2 border-border/60 bg-muted/20 px-3 py-2 text-sm italic text-muted-foreground">
          <Quote className="mt-1 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span className="whitespace-pre-line">{card.biography}</span>
        </p>
      )}
      {isBlankCard(card) && (
        <p className="text-xs text-muted-foreground">{t('relations.contact_no_details')}</p>
      )}
    </div>
  );
}

/**
 * One themed group of contact rows.
 *
 * `show` is computed by the caller from the SAME lists it renders: a group whose
 * blocks all return null would otherwise draw an empty bordered box.
 */
function ContactGroup({ show, children }: { show: boolean; children: React.ReactNode }) {
  if (!show) return null;
  return (
    <div className="divide-y divide-border/40 overflow-hidden rounded-lg border border-border/40 bg-muted/10">
      {children}
    </div>
  );
}
