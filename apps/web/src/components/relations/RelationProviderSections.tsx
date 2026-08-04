'use client';

/**
 * The three provider-backed sections of the 360° view (Bloc C).
 *
 * Exported one by one rather than as a block: the reader asked for a precise
 * order — contact card, commitments, memories, calls, mail, meetings — which
 * interleaves them with the database-local sections. A single block could not
 * honour that.
 *
 * What makes these different from the local ones:
 *
 * - **no counts.** A provider page cannot prove how many rows exist behind it,
 *   and ADR-185 forbids a count that is not exact. Mail and meetings state
 *   their WINDOW instead — the scope of the answer.
 * - **"could not look" is not "found nothing".** A missing connector, a card
 *   with no address and an empty result are three different sentences.
 * - **they are cached** (up to six hours for the address book), so each one
 *   carries a refresh control: without it, a correction made in the address
 *   book stays invisible for half a day.
 */

import { useState } from 'react';
import { CalendarDays, Contact, Mail, RefreshCw, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { directionTone } from '@/lib/status-tone';

import { CollapsibleSection, SectionBadge } from '@/components/relations/CollapsibleSection';
import { ContactCardBody } from '@/components/relations/ContactCardBody';
import { chatIntentHref, dateTimeRangeLabel, timeAgoLabel } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import { cn } from '@/lib/utils';
import type {
  ContactCard,
  ContextSection,
  ContextStatus,
  ExchangedEmail,
  RelationContext,
  SharedEvent,
} from '@/hooks/useRelations';

/** Section keys, mirroring the backend's `?refresh=` vocabulary. */
export const CONTEXT_SECTIONS = ['contact', 'emails', 'events'] as const;
export type ContextSectionKey = (typeof CONTEXT_SECTIONS)[number];

/** True when a section holds something worth a card. */
export function hasPayload(section: ContextSection | undefined): boolean {
  return (
    section !== undefined &&
    section.status === 'ok' &&
    (section.contact !== null || section.emails.length > 0 || section.events.length > 0)
  );
}

/** The refresh control every cached section carries. */
function RefreshButton({
  label,
  busy,
  onRefresh,
}: {
  label: string;
  busy: boolean;
  onRefresh: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onRefresh}
      // `aria-disabled`, never `disabled`: a control disabled while focused is
      // blurred by the browser and leaves the tab order.
      aria-disabled={busy}
      aria-label={label}
      title={label}
      className={cn(
        'shrink-0 inline-flex min-h-11 min-w-11 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        busy && 'cursor-not-allowed opacity-50'
      )}
    >
      <RefreshCw className={cn('h-3.5 w-3.5', busy && 'animate-spin')} aria-hidden="true" />
    </button>
  );
}

/**
 * The subjects the summary request carries — ONLY the ticked ones.
 *
 * Pure and exported so the selection semantics can be asserted without going
 * through i18n: the component test would otherwise read an untranslated key
 * and prove nothing about which messages were actually handed over.
 *
 * Order follows the LIST, not the click order: the reader asked about a
 * conversation, and a chronological request reads like one.
 */
export function selectedSubjects(emails: ExchangedEmail[], selected: string[]): string {
  return emails
    .filter(email => selected.includes(email.id))
    .map(email => `« ${email.subject} »`)
    .join(', ');
}

export function ProviderContactSection({
  section,
  busy,
  onRefresh,
}: {
  section: ContextSection | undefined;
  busy: boolean;
  onRefresh: () => void;
}) {
  const { t, i18n } = useTranslation();
  if (!hasPayload(section) || !section?.contact) return null;
  const card: ContactCard = section.contact;

  return (
    <CollapsibleSection
      icon={Contact}
      title={t('relations.section_contact')}
      action={
        <RefreshButton label={t('relations.refresh_section')} busy={busy} onRefresh={onRefresh} />
      }
    >
      <ContactCardBody card={card} locale={i18n.language} />
    </CollapsibleSection>
  );
}

/**
 * Mail exchanged, with a selection that can be handed to the chat.
 *
 * The summary link uses `?intent=` (auto-sent, ADR-173) and not `?draft=`:
 * ticking messages and pressing a named button IS the deliberate act, exactly
 * like "prepare a 360° point". `?draft=` stays reserved for anything that
 * writes to a HUMAN — a summary is asked of LIA, about the user's own mailbox.
 */
export function ProviderEmailsSection({
  section,
  personName,
  windowDays,
  lng,
  busy,
  onRefresh,
}: {
  section: ContextSection | undefined;
  personName: string;
  windowDays: number;
  lng: string;
  busy: boolean;
  onRefresh: () => void;
}) {
  const { t, i18n } = useTranslation();
  const [selected, setSelected] = useState<string[]>([]);
  const absolute = (iso: string | null) => dateTimeRangeLabel(i18n.language, iso);

  if (!hasPayload(section)) return null;
  const emails: ExchangedEmail[] = section?.emails ?? [];

  const toggle = (id: string) =>
    setSelected(previous =>
      previous.includes(id) ? previous.filter(other => other !== id) : [...previous, id]
    );

  // Counted against what is STILL on the page: a refresh can retire a message
  // whose id is still ticked, and a button offering to summarize three while
  // handing over two would be a claim the request contradicts.
  const selectedHere = emails.filter(email => selected.includes(email.id));

  const askForSummary = () => {
    const subjects = selectedSubjects(emails, selected);
    openChatDeepLink(
      chatIntentHref(lng, t('relations.emails_summary_intent', { name: personName, subjects }))
    );
  };

  return (
    <CollapsibleSection
      icon={Mail}
      title={t('relations.section_emails')}
      // Counted like every other section: without it, a folded block gave the
      // reader nothing to choose from. The number is what the section HOLDS
      // right now — these come from a live provider read, not from a stored
      // aggregate, so it describes exactly what unfolding will show.
      badge={<SectionBadge>{emails.length}</SectionBadge>}
      action={
        <RefreshButton label={t('relations.refresh_section')} busy={busy} onRefresh={onRefresh} />
      }
    >
      {emails.map(email => {
        const received = email.direction === 'received';
        const inputId = `relation-email-${email.id}`;
        // Every child sits DIRECTLY under the label. Nesting the text two
        // levels down leaves the checkbox unnamed for a screen reader (the
        // a11y ratchet refuses it, rightly) — and a wrapping flex row keeps
        // the whole line clickable, which is what the depth was buying.
        return (
          <label
            key={email.id}
            htmlFor={inputId}
            className="flex min-h-11 cursor-pointer flex-wrap items-baseline gap-x-2 gap-y-0.5 rounded-md border-l-2 border-primary/40 py-2 pl-3 hover:bg-muted/40"
          >
            <input
              id={inputId}
              type="checkbox"
              checked={selected.includes(email.id)}
              onChange={() => toggle(email.id)}
              // Named by its SUBJECT, not by the whole row: a screen reader
              // then announces "select « Devis chantier »" instead of reading
              // the direction and the date back before the useful part.
              aria-label={t('relations.emails_select', { subject: email.subject })}
              className="h-4 w-4 shrink-0 accent-primary"
            />
            {/* One tone per direction — sent and received were both primary
                blue, so nothing but the wording separated them while
                scanning. */}
            <Badge variant={directionTone(email.direction)} size="sm">
              {received ? t('relations.peer_message_received') : t('relations.peer_message_sent')}
            </Badge>
            {email.occurred_at && (
              <span className="text-[11px] text-muted-foreground">
                {timeAgoLabel(t, email.occurred_at)}
              </span>
            )}
            {/* The relative label says how long ago; this says WHEN — the one
                a reader needs before replying. Full `text-muted-foreground`,
                never a diluted `/80`: at 11px the faded pair measures 3.51:1,
                under the 4.5:1 AA floor (axe, production bundle) — the same
                trap already closed on the relayed-message placeholder. */}
            {absolute(email.occurred_at) && (
              <span className="text-[11px] tabular-nums text-muted-foreground">
                {absolute(email.occurred_at)}
              </span>
            )}
            {/* The SUBJECT is the row's own title and sat at the same weight
                as its excerpt. Emphasised rather than badged: a tag around a
                whole subject line would wrap into a coloured block, and this
                one has to stay readable at any length. */}
            <span className="w-full text-sm font-semibold text-foreground">{email.subject}</span>
            {/* The subject alone rarely says what an exchange was about
                ("Re: Re: point"). Two lines at most: the excerpt informs the
                row, it must not become it. Full `text-muted-foreground` — the
                diluted variants fall under the 4.5:1 AA floor at this size,
                the trap already closed on the timestamps above. */}
            {email.excerpt && (
              <span className="line-clamp-2 w-full text-xs leading-relaxed text-muted-foreground">
                {email.excerpt}
              </span>
            )}
          </label>
        );
      })}

      {selectedHere.length > 0 && (
        <button
          type="button"
          onClick={askForSummary}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-2.5 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
          {t('relations.emails_summarize', { count: selectedHere.length })}
        </button>
      )}

      {/* The scope, never a total: a window is not the whole mailbox. */}
      <p className="text-[11px] text-muted-foreground">
        {t('relations.emails_window', { count: windowDays })}
      </p>
    </CollapsibleSection>
  );
}

/** One meeting row — the role is TEXT, never a colour alone. */
function EventRow({ event, showRole }: { event: SharedEvent; showRole: boolean }) {
  const { t, i18n } = useTranslation();
  const slot = dateTimeRangeLabel(i18n.language, event.starts_at, event.ends_at);
  return (
    <div className="border-l-2 border-sky-500/40 pl-3">
      <p className="flex flex-wrap items-baseline gap-2 text-sm text-foreground/90">
        {event.summary}
        {event.starts_at && (
          <span className="text-[11px] text-muted-foreground">
            {timeAgoLabel(t, event.starts_at)}
          </span>
        )}
        {/* A meeting is a SLOT: the reader needs the day and both hours to
            know whether they can be there, not only how far off it is. */}
        {slot && <span className="text-[11px] tabular-nums text-muted-foreground">{slot}</span>}
        {showRole && (
          // The house badge rather than a grey inline span: a role is a fact
          // about the meeting, and it sat next to an "upcoming" pill that was
          // already tinted — two markers on one line, one of them looking
          // disabled.
          <Badge variant="default" size="sm">
            {event.role === 'organizer'
              ? t('relations.event_role_organizer')
              : t('relations.event_role_attendee')}
          </Badge>
        )}
        {!event.is_past && (
          <Badge variant="info" size="sm">
            {t('relations.event_upcoming')}
          </Badge>
        )}
      </p>
    </div>
  );
}

export function ProviderEventsSection({
  section,
  windowDays,
  busy,
  onRefresh,
}: {
  section: ContextSection | undefined;
  windowDays: number;
  busy: boolean;
  onRefresh: () => void;
}) {
  const { t } = useTranslation();
  if (!hasPayload(section)) return null;
  const events: SharedEvent[] = section?.events ?? [];
  // Apple exposes no organizer at all. Labelling everything "attendee" there
  // would state a role nobody verified, so the label is dropped instead.
  const showRole = events.some(event => event.organizer_known);

  return (
    <CollapsibleSection
      icon={CalendarDays}
      title={t('relations.section_events')}
      badge={<SectionBadge>{events.length}</SectionBadge>}
      action={
        <RefreshButton label={t('relations.refresh_section')} busy={busy} onRefresh={onRefresh} />
      }
    >
      {events.map(event => (
        <EventRow key={event.id} event={event} showRole={showRole} />
      ))}
      <p className="text-[11px] text-muted-foreground">
        {t('relations.events_window', { count: windowDays })}
      </p>
    </CollapsibleSection>
  );
}

/**
 * The one sentence a set of unusable sections is allowed to say — as a VALUE.
 *
 * Not a component: one that returns null still yields a truthy JSX element, so
 * a `=== null` guard would never fire and the block would render an empty
 * shell instead of disappearing.
 *
 * Ranked, because several can be true at once and the most actionable wins:
 * the address book first (it is what turns a name into an address, so without
 * it the other two report `no_address` and blaming the card would describe one
 * that does not exist), then the missing address, then a read failure. A mail
 * or calendar connector the user simply chose not to plug in stays silent — a
 * relationship page is not a settings page.
 */
export function providerNoteKey(context: RelationContext | null): string | null {
  if (context === null) return null;
  const statuses: ContextStatus[] = [
    context.contact.status,
    context.emails.status,
    context.events.status,
  ];
  if (context.contact.status === 'not_configured') return 'relations.provider_none';
  if (context.emails.status === 'no_address' || context.events.status === 'no_address') {
    return 'relations.provider_no_address';
  }
  if (statuses.includes('error')) return 'relations.provider_error';
  return null;
}

export function ProviderNote({ noteKey }: { noteKey: string | null }) {
  const { t } = useTranslation();
  if (noteKey === null) return null;
  return <p className="text-xs text-muted-foreground">{t(noteKey)}</p>;
}
