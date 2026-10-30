'use client';

/**
 * RelationDetailPanel — the 360° view of one relationship (N-09, restyled).
 *
 * Identity header (large avatar, peers badge, star), a row of quick actions,
 * then sectioned CARDS whose items are plain rows split by a hairline, each
 * titled by when it happened, with no icon before it — open loops, memories,
 * calls, relayed peer messages — and the LIA connection block last, when one
 * exists. Every section shows a preview and reveals the rest on demand, with
 * its EXACT total on the pill.
 *
 * Read-only aggregation, with two chat deep links whose difference is
 * load-bearing:
 *
 * - "run the 360° point" — the button lives in the SCOPE section, next to the
 *   checkboxes that decide what it will read; it uses `?intent=`, which is
 *   AUTO-SENT (ADR-173), because the click on a named action button IS the
 *   deliberate act. A second copy in the header would have been a shortcut
 *   past the very choice the section exists to offer;
 * - every quick action uses `?draft=`, which only PREFILLS the composer.
 *   Calling someone, relaying them a message or booking a commitment must
 *   never leave without the user pressing send (peers A4 for the relay), so
 *   `?intent=` is forbidden there.
 *
 * The best-effort identity match is stated, never hidden (honesty rule).
 */

import {
  ArrowLeft,
  Check,
  ChevronDown,
  CircleSlash,
  Handshake,
  ListTodo,
  MessageSquare,
  Pencil,
  PhoneCall,
  RefreshCw,
  Send,
  Star,
  StickyNote,
} from 'lucide-react';
import { Children, useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import Link from 'next/link';
import { settingsSectionHref } from '@/lib/settings-sections';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { directionTone } from '@/lib/status-tone';

import { toast } from 'sonner';

import { CommitmentEditor } from '@/components/commitments/CommitmentEditor';
import { useCommitmentActions } from '@/hooks/useCommitmentActions';
import type { OpenLoopPatch } from '@/hooks/useOpenLoops';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { RelationAvatar } from '@/components/relations/RelationAvatar';
import { RelationSmsSection } from './RelationSmsSection';
import {
  CONTEXT_SECTIONS,
  contactCardOf,
  ProviderContactSection,
  ProviderEmailsSection,
  ProviderEventsSection,
  ProviderNote,
  providerNoteKey,
} from '@/components/relations/RelationProviderSections';
import {
  CollapsibleSection,
  SectionBadge,
  SectionRow,
  SectionRowTitle,
  SectionRows,
} from '@/components/relations/CollapsibleSection';
import { RelationDebriefSection } from '@/components/relations/RelationDebriefSection';
import { RelationTimelineSection } from '@/components/relations/RelationTimelineSection';
import { RelationMergePanel } from '@/components/relations/RelationMergePanel';
import { RelationScopeSection, useScopeDraft } from '@/components/relations/RelationScopeSection';
import { RelationWhen } from '@/components/relations/RelationWhen';
import { chatDraftHref, chatIntentHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import {
  useRelationMerge,
  useRelationContext,
  useRelationDebrief,
  useRelationDetail,
  type ContactCard,
  type RelationContext,
  type RelationDetail,
  type RelationOverviewScope,
  type RelationPeerLink,
  type RelationPeerMessage,
  type RelationShare,
} from '@/hooks/useRelations';
import {
  contactActionGroups,
  type ContactActionGroup,
  type QuickAction,
} from '@/lib/relations/contact-actions';
import { useApplicationConnectors } from '@/hooks/useApplicationConnectors';
import { TELEPHONY_CONNECTOR_TYPES } from '@/components/settings/connectors/constants';
import { isConnectorActive } from '@/components/settings/connectors/types';

/** Items a section shows before the reader asks for more. */
const SECTION_PREVIEW_COUNT = 10;

/**
 * One section of the 360° view, with progressive disclosure.
 *
 * The pill carries the EXACT total, not the number of rendered rows: a
 * section that holds 137 commitments and renders 10 must say 137. What it
 * cannot show — because the API caps its page — is stated in words rather
 * than truncated silently.
 */
function SectionCard({
  icon: Icon,
  title,
  total,
  children,
}: {
  icon: typeof Handshake;
  title: string;
  /** Exact number of items that exist, server-side. */
  total: number;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const items = Children.toArray(children);
  const visible = expanded ? items : items.slice(0, SECTION_PREVIEW_COUNT);
  const collapsed = items.length - visible.length;
  const beyondThePage = total - items.length;

  return (
    <CollapsibleSection icon={Icon} title={title} badge={<SectionBadge>{total}</SectionBadge>}>
      <SectionRows>{visible}</SectionRows>
      {collapsed > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="mt-3 inline-flex items-center gap-1 rounded-lg px-1 text-xs font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
          {t('relations.show_more', { count: collapsed })}
        </button>
      )}
      {/* Shown as soon as the page holds nothing more to reveal — NOT only
          once expanded. With a section cap of 10 or less there is no "show
          more" button at all, and the pill would then claim 137 above ten
          rows with nothing accounting for the gap. */}
      {collapsed === 0 && beyondThePage > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">
          {t('relations.more_not_shown', { count: beyondThePage })}
        </p>
      )}
    </CollapsibleSection>
  );
}

/**
 * One relayed message, titled like a mail row: the direction as TRANSLATED
 * TEXT in a toned badge, then when — no icon leads the row (owner request
 * 2026-10-21). A message with no text says so plainly instead of rendering an
 * empty line (honesty rule).
 */
function PeerMessageItem({ message }: { message: RelationPeerMessage }) {
  const { t } = useTranslation();
  const received = message.direction === 'received';

  return (
    <SectionRow className="[overflow-wrap:anywhere]">
      <SectionRowTitle>
        {/* One tone per direction. Both sides used to be the same primary
            blue, so nothing but the wording separated them while scanning.
            The word stays — the tone is what makes the two sides legible at
            a glance. */}
        <Badge variant={directionTone(message.direction)} size="sm">
          {received ? t('relations.peer_message_received') : t('relations.peer_message_sent')}
        </Badge>
        <RelationWhen start={message.occurred_at} />
      </SectionRowTitle>
      <p
        className={cn(
          'min-w-0 whitespace-pre-line',
          message.content ? 'text-sm text-foreground/90' : 'text-xs italic text-muted-foreground'
        )}
      >
        {message.content || t('relations.peer_message_no_content')}
      </p>
    </SectionRow>
  );
}

/**
 * The LIA connection behind this relationship (peers spec §11, D2).
 *
 * Read-only by contract: sharing is granted and revoked in the Connections
 * settings. Both directions are shown — stating only what the user set up
 * would describe half of a two-sided arrangement. Share labels reuse the
 * settings table so one wording serves both screens.
 *
 * Rendered below the grid rather than inside a column, so it closes the sheet
 * at every width instead of only on a desktop (2026-08-03).
 */
function PeerLinkSection({ link }: { link: RelationPeerLink | null }) {
  const { t } = useTranslation();
  if (!link) return null;

  const badges = (shares: RelationShare[], emptyLabel: string) =>
    shares.length > 0 ? (
      <span className="flex flex-wrap gap-1.5">
        {shares.map(share => (
          <span
            key={`${share.domain}_${share.level}`}
            className="rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 text-px-11 font-medium text-primary"
          >
            {t(`settings.peers.shares.badge.${share.domain}_${share.level}`)}
          </span>
        ))}
      </span>
    ) : (
      <span className="text-xs text-muted-foreground">{emptyLabel}</span>
    );

  return (
    <section className="rounded-xl border border-primary/25 bg-primary/5 p-4">
      <h3 className="flex flex-wrap items-center gap-2 text-sm font-semibold text-foreground">
        <Handshake className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {t('relations.peer_link_title')}
        {link.connected_since && (
          <span className="text-px-11 font-normal text-muted-foreground">
            {t('relations.peer_link_connected')} <RelationWhen start={link.connected_since} />
          </span>
        )}
      </h3>
      <dl className="mt-3 space-y-2 text-sm">
        <div className="flex flex-wrap items-baseline gap-2">
          <dt className="text-xs text-muted-foreground">{t('settings.peers.shares.my_title')}</dt>
          <dd>{badges(link.shared_by_me, t('relations.peer_link_nothing_shared'))}</dd>
        </div>
        <div className="flex flex-wrap items-baseline gap-2">
          <dt className="text-xs text-muted-foreground">
            {t('settings.peers.shares.their_title')}
          </dt>
          <dd>{badges(link.shared_with_me, t('settings.peers.shares.their_empty'))}</dd>
        </div>
      </dl>
    </section>
  );
}

/**
 * Open commitments, oldest-first as the API ranks them, each titled by when it
 * was recorded — how long ago and the moment, like a mail row (owner request
 * 2026-10-21). The title replaced an "open for N days" pill that stated the
 * same age a second time on the same row.
 */
function OpenLoopsSection({
  loops,
  total,
  lng,
  onChanged,
}: {
  loops: RelationDetail['open_loops'];
  total: number;
  lng: string;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  // One editor at a time: two open forms would compete for the same list.
  const [editingId, setEditingId] = useState<string | null>(null);
  const { pendingId, close, update } = useCommitmentActions(onChanged);

  if (loops.length === 0) return null;

  const act = async (id: string, action: 'done' | 'dismissed') => {
    if (!(await close(id, action))) toast.error(t('common.error'));
  };

  const save = async (id: string, patch: OpenLoopPatch) => {
    if (await update(id, patch)) {
      setEditingId(null);
      toast.success(t('settings.open_loops.edit_saved'));
      return;
    }
    toast.error(t('common.error'));
  };

  const relaunch = (loop: RelationDetail['open_loops'][number]) => {
    // Same intent as the Settings ledger — a commitment behaves identically
    // wherever the user meets it.
    const intent = t(
      loop.direction === 'waiting_on_other'
        ? 'dashboard.briefing.intents.loop_waiting'
        : 'dashboard.briefing.intents.loop_owed',
      { subject: loop.subject }
    );
    openChatDeepLink(chatDraftHref(lng as Language, intent));
  };

  return (
    <SectionCard icon={ListTodo} title={t('relations.section_open_loops')} total={total}>
      {loops.map(loop =>
        editingId === loop.id ? (
          <SectionRow key={loop.id}>
            <CommitmentEditor
              lng={lng as Language}
              subject={loop.subject}
              dueHint={loop.due_hint}
              saving={pendingId === loop.id}
              onCancel={() => setEditingId(null)}
              onSave={patch => void save(loop.id, patch)}
            />
          </SectionRow>
        ) : (
          <SectionRow key={loop.id} className="flex items-start gap-2">
            <div className="min-w-0 flex-1 [overflow-wrap:anywhere]">
              <SectionRowTitle>
                <RelationWhen start={loop.opened_at} />
              </SectionRowTitle>
              <p className="text-sm text-foreground/90">{loop.subject}</p>
            </div>
            <span className="flex shrink-0 items-center gap-1">
              <CommitmentButton
                icon={Pencil}
                label={t('settings.open_loops.edit', { subject: loop.subject })}
                title={t('settings.open_loops.edit_label')}
                onClick={() => setEditingId(loop.id)}
              />
              <CommitmentButton
                icon={Check}
                label={t('settings.open_loops.done', { subject: loop.subject })}
                title={t('settings.open_loops.done_label')}
                hover="hover:text-green-600"
                busy={pendingId === loop.id}
                onClick={() => void act(loop.id, 'done')}
              />
              <CommitmentButton
                icon={Send}
                label={t('settings.open_loops.relaunch', { subject: loop.subject })}
                title={t('settings.open_loops.relaunch_label')}
                onClick={() => relaunch(loop)}
              />
              <CommitmentButton
                icon={CircleSlash}
                label={t('settings.open_loops.dismiss', { subject: loop.subject })}
                title={t('settings.open_loops.dismiss_label')}
                hover="hover:text-orange-600"
                busy={pendingId === loop.id}
                onClick={() => void act(loop.id, 'dismissed')}
              />
            </span>
          </SectionRow>
        )
      )}
    </SectionCard>
  );
}

/** One commitment action. `aria-disabled` keeps it focusable while busy. */
function CommitmentButton({
  icon: Icon,
  label,
  title,
  onClick,
  busy = false,
  hover = 'hover:text-primary',
}: {
  icon: typeof Check;
  label: string;
  title: string;
  onClick: () => void;
  busy?: boolean;
  hover?: string;
}) {
  return (
    <button
      type="button"
      onClick={() => {
        // A `disabled` control that HAS focus blurs and leaves the tab order
        // mid-interaction, so the guard lives here rather than in the DOM.
        if (busy) return;
        onClick();
      }}
      aria-disabled={busy}
      aria-label={label}
      title={title}
      className={`rounded-md border border-border bg-background/80 p-1.5 ${
        busy ? 'opacity-40' : `hover:bg-background ${hover}`
      }`}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden />
    </button>
  );
}

/** Past calls — the objective and the outcome summary, never the number (D-8). */
function CallsSection({
  calls,
  total,
  lng,
}: {
  calls: RelationDetail['recent_calls'];
  total: number;
  lng: string;
}) {
  const { t } = useTranslation();
  if (calls.length === 0) return null;
  return (
    <SectionCard icon={PhoneCall} title={t('relations.section_calls')} total={total}>
      {calls.map(call => (
        <SectionRow key={call.id} className="py-1.5">
          <Link
            href={`${settingsSectionHref(lng, 'telephony-calls')}&call=${encodeURIComponent(call.id)}`}
            className="-mx-2 block min-w-0 rounded-md px-2 py-1.5 transition-colors [overflow-wrap:anywhere] hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {/* The title is WHEN the call happened, like a mail row (owner
                request 2026-10-21): how long ago, then the day, the date and
                the hour. No icon leads any line of the row; the direction
                badge does — LIA placed every call, so it is « sent », in the
                tone the relayed messages and e-mails use. */}
            <SectionRowTitle>
              <Badge variant={directionTone('sent')} size="sm">
                {t('relations.peer_message_sent')}
              </Badge>
              <RelationWhen start={call.created_at} />
            </SectionRowTitle>
            {/* NOT a badge. A call objective is a full instruction — "ask her
                why she does not use LIA, in three or four questions" — and a
                pill is sized for a word: `Badge` pins its height, so three
                lines of text spilled out of a 16 px capsule and read as struck
                through (measured on a real card, 2026-08-04). */}
            <p className="text-sm text-foreground/90">{call.objective}</p>
            {call.summary && (
              <p className="mt-1 whitespace-pre-line text-xs leading-relaxed text-muted-foreground">
                {call.summary}
              </p>
            )}
          </Link>
        </SectionRow>
      ))}
    </SectionCard>
  );
}

/** Messages relayed through the two assistants, newest first. */
function PeerMessagesSection({
  messages,
  total,
}: {
  messages: RelationPeerMessage[];
  total: number;
}) {
  const { t } = useTranslation();
  if (messages.length === 0) return null;
  return (
    <SectionCard icon={MessageSquare} title={t('relations.section_peer_messages')} total={total}>
      {messages.map(message => (
        <PeerMessageItem key={message.id} message={message} />
      ))}
    </SectionCard>
  );
}

/**
 * Secondary actions on a relationship — one place per action.
 *
 * Every one of them is a `?draft=` deep link: it PREFILLS the composer and
 * never sends. `?intent=` is auto-sent (QW-24/ADR-173) and stays reserved for
 * the header's "prepare a 360° point", where the click on a named button IS
 * the deliberate act. Writing to another human is never that.
 *
 * The message action appears only on a live connection: offering it after a
 * removal would promise a relay that cannot happen. After them, the address
 * book's actions, ONE entry per kind (`contactActionGroups`) — still
 * `?draft=`, the subject or the purpose is the person's to add. A call is
 * offered only on a NUMBER, and only while the account holds an active
 * telephony connector: the generic « call » that let LIA guess the number is
 * gone.
 *
 * Every label is short and none carries a value, so the bar has exactly two
 * shapes (owner request 2026-10-29, after the buttons sized by their address
 * fell apart at every width between a phone and a desktop): one row of
 * equal-width buttons when the SHEET is wide enough for the widest label of
 * the six languages, one full-width list with the labels on the left below
 * that (owner request 2026-10-22: a thumb gets a whole row, never a chip). A
 * container query, not a viewport breakpoint — the sheet's width is what the
 * row must fit in.
 */
function QuickActions({
  detail,
  card,
  lng,
}: {
  detail: RelationDetail;
  card: ContactCard | null;
  lng: string;
}) {
  const { t } = useTranslation();
  const name = detail.display_name;
  // The connectors page's own predicate: a call needs the account's ACTIVE
  // telephony connector, and an unanswered read offers none rather than one
  // nothing could place.
  const { data: connectorList } = useApplicationConnectors();
  const telephony = (connectorList?.connectors ?? []).some(
    connector =>
      TELEPHONY_CONNECTOR_TYPES.includes(
        connector.connector_type.toLowerCase() as (typeof TELEPHONY_CONNECTOR_TYPES)[number]
      ) && isConnectorActive(connector)
  );

  const actions: QuickAction[] = [
    ...(detail.is_peer
      ? [
          {
            key: 'message',
            icon: MessageSquare,
            // NOT the chat's `reply_prefill`: replying under a received bubble
            // and writing to someone from their card are different gestures,
            // and "reply to X" would be plainly false with nothing to reply to.
            label: t('relations.action_message'),
            draft: t('relations.action_message_prefill', { name }),
          },
        ]
      : []),
    {
      key: 'loop',
      icon: ListTodo,
      label: t('relations.action_loop'),
      draft: t('relations.action_loop_prefill', { name }),
    },
  ];

  const groups = contactActionGroups(card, t, { telephony });

  return (
    <div className="@container flex justify-center">
      {/* `auto-cols-fr` in a grid sized to its content: every column takes the
          widest button's width, so the row reads as one bar whatever the
          language. */}
      <div
        role="group"
        aria-label={t('relations.actions_group', { name })}
        className="grid w-full gap-2 @2xl:w-auto @2xl:auto-cols-fr @2xl:grid-flow-col"
      >
        {actions.map(action => (
          <QuickActionButton key={action.key} action={action} lng={lng} />
        ))}
        {groups.map(group => (
          <ContactActionEntry key={group.kind} group={group} lng={lng} />
        ))}
      </div>
    </div>
  );
}

/**
 * The shape every button of the bar shares: a full row with its label on the
 * left in the list, centred in its column in the row. `min-h-11`: these are
 * the card's primary actions, and at 30 px on a phone they were wide enough to
 * look clickable, too short to hit reliably (measured 2026-08-01).
 */
const ACTION_BAR_BUTTON = 'min-h-11 w-full justify-start @2xl:justify-center';

/**
 * One kind of the address book: its one value acts directly, several open a
 * menu listing each with the labels the address book stored it under.
 */
function ContactActionEntry({ group, lng }: { group: ContactActionGroup; lng: string }) {
  const { icon: Icon, label, targets } = group;
  if (targets.length === 1) {
    const [target] = targets;
    return (
      <QuickActionButton
        action={{ key: target.key, icon: Icon, label, draft: target.draft }}
        value={target.value}
        lng={lng}
      />
    );
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="default" size="sm" className={ACTION_BAR_BUTTON}>
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          {label}
          <ChevronDown className="ml-auto h-3.5 w-3.5 @2xl:ml-0" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      {/* At least the trigger's width — in the list, the menu lines up with the
          row it opened from — and a value too long for the cap wraps on its
          spaces rather than leaving the screen. */}
      <DropdownMenuContent
        align="start"
        className="min-w-[var(--radix-dropdown-menu-trigger-width)] max-w-[min(24rem,calc(100vw-1rem))]"
      >
        {targets.map(target => (
          <DropdownMenuItem
            key={target.key}
            onSelect={() => openChatDeepLink(chatDraftHref(lng, target.draft))}
            className="whitespace-normal [overflow-wrap:anywhere]"
          >
            <Icon className="text-primary" aria-hidden="true" />
            <span className="min-w-0 flex-1">{target.value}</span>
            {target.tags.map(tag => (
              <span
                key={tag}
                className="shrink-0 rounded-full bg-muted px-2 py-px text-px-10 font-medium uppercase text-muted-foreground"
              >
                {tag}
              </span>
            ))}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * One quick action: a solid call to action that prefills the composer.
 *
 * @param value - The one value the action reaches, when it reaches one, since
 *   the label alone no longer says which: shown on hover and read as the
 *   button's DESCRIPTION — the name stays the visible label. Put in the name
 *   as well, a screen reader announced the value twice.
 */
function QuickActionButton({
  action,
  lng,
  value,
}: {
  action: QuickAction;
  lng: string;
  value?: string;
}) {
  const { icon: Icon, label, draft } = action;
  return (
    <Button
      type="button"
      // SOLID (ADR-207, owner arbitration 2026-08-05): a section's
      // constructive CTA takes the filled primary, like "+ Add" on
      // memories, MCP or scheduled actions. The earlier `outline` reading
      // (ADR-205) counted all 137 outline sites in one bucket — cancels
      // and filter presets included; at CTA altitude, solid is the
      // codebase's actual convention.
      variant="default"
      size="sm"
      title={value}
      onClick={() => openChatDeepLink(chatDraftHref(lng, draft))}
      className={ACTION_BAR_BUTTON}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {label}
    </Button>
  );
}

/** Stored memories mentioning this person (best-effort substring match). */
function MemoriesSection({
  memories,
  total,
  lng,
}: {
  memories: RelationDetail['memories'];
  total: number;
  lng: string;
}) {
  const { t } = useTranslation();
  if (memories.length === 0) return null;
  return (
    <SectionCard icon={StickyNote} title={t('relations.section_memories')} total={total}>
      {memories.map(memory => (
        // A LINK, not a dead paragraph. Reading "prefers morning meetings" here
        // and having no way to reach it meant finding Settings and the right
        // section by hand to correct or delete it.
        //
        // The destination is the SECTION, never the row: the memory list is
        // paginated and filterable, so a link promising to land on this exact
        // memory would be false the moment it sits on page three. `<Link>`
        // rather than a click handler — middle-click, open-in-new-tab and the
        // "link" role are what a navigation owes its reader.
        //
        // Titled by when it was kept, like a mail row — how long ago, then the
        // day, the date and the hour in bold — with no icon before it (owner
        // request 2026-10-21).
        <SectionRow key={memory.id} className="py-1.5">
          <Link
            href={settingsSectionHref(lng, 'memories')}
            className="-mx-2 block min-w-0 rounded-md px-2 py-1.5 transition-colors [overflow-wrap:anywhere] hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <SectionRowTitle>
              <RelationWhen start={memory.created_at} />
            </SectionRowTitle>
            <p className="text-sm text-foreground/90">{memory.content}</p>
          </Link>
        </SectionRow>
      ))}
    </SectionCard>
  );
}

/**
 * The identity header: who this is, and the three things you can do from here.
 *
 * Extracted from the panel to keep its complexity under the frontend ratchet
 * — the panel now reads as the ORDER of the sections, which is what it is.
 */
function RelationHeader({
  detail,
  isFavorite,
  refreshing,
  onBack,
  onToggleFavorite,
  onRefreshAll,
}: {
  detail: RelationDetail;
  isFavorite: boolean;
  refreshing: boolean;
  onBack: () => void;
  onToggleFavorite: () => void;
  onRefreshAll: () => void;
}) {
  const { t } = useTranslation();
  const starLabel = isFavorite
    ? t('relations.favorite_remove', { name: detail.display_name })
    : t('relations.favorite_add', { name: detail.display_name });

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onBack}
          aria-label={t('relations.back')}
          className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md text-muted-foreground hover:bg-muted/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </button>
        <RelationAvatar name={detail.display_name} size="lg" />
        <div className="min-w-0">
          <span className="flex items-center gap-2">
            <h2 className="truncate text-xl font-bold tracking-tight">{detail.display_name}</h2>
            {detail.is_peer && (
              <span
                className="inline-flex shrink-0 items-center gap-1 rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 text-px-10 font-semibold text-primary"
                title={t('relations.peer_badge_hint')}
              >
                <Handshake className="h-3 w-3" aria-hidden="true" />
                {t('relations.peer_badge')}
              </span>
            )}
          </span>
          <p className="text-xs text-muted-foreground">{t('relations.subtitle_detail')}</p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onToggleFavorite}
          aria-label={starLabel}
          aria-pressed={isFavorite}
          className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-border/60 transition-colors hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Star
            aria-hidden="true"
            className={cn(
              'h-4 w-4',
              isFavorite ? 'fill-amber-400 text-amber-400' : 'text-muted-foreground/60'
            )}
          />
        </button>
        {/* Global refresh: the provider sections are cached up to six hours,
            so the reader needs a way to say "look again" for all of them at
            once — the per-section controls handle the finer grain. */}
        <button
          type="button"
          onClick={onRefreshAll}
          aria-disabled={refreshing}
          aria-label={t('relations.refresh_all')}
          title={t('relations.refresh_all')}
          className={cn(
            'inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-border/60 text-muted-foreground transition-colors hover:bg-muted/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            refreshing && 'cursor-not-allowed opacity-50'
          )}
        >
          <RefreshCw aria-hidden="true" className={cn('h-4 w-4', refreshing && 'animate-spin')} />
        </button>
      </div>
    </div>
  );
}

/**
 * The sections, in the order the reader asked for.
 *
 * Contact card first — who this person IS — then what is open with them, what
 * LIA remembers, then the exchanges (calls, mail, meetings). The
 * provider-backed ones are INTERLEAVED rather than appended: they arrive later
 * than the database-local ones, but they belong where the reader expects them,
 * not where the network happens to put them.
 *
 * The LIA connection closes the sheet, below the grid and at full width, for
 * every viewport — see the comment at its call site for why the left column
 * could not hold it.
 *
 * Extracted so the panel above reads as what it is — an order — and stays
 * under the frontend complexity ratchet.
 */
function RelationSections({
  name,
  detail,
  context,
  refreshing,
  lng,
  onRefresh,
  scope,
  saving,
  onScopeChange,
  onPrepare,
  onCommitmentChanged,
}: {
  /** The name the card was opened with — what every read of it names. */
  name: string;
  detail: RelationDetail;
  context: RelationContext | null;
  /** Sections being re-read right now — only THEIR control spins. */
  refreshing: string[];
  lng: string;
  onRefresh: (sections: string[]) => void;
  scope: RelationOverviewScope;
  saving: boolean;
  onScopeChange: (scope: RelationOverviewScope) => void;
  onPrepare: () => void;
  /** Re-read the relation after a commitment changed — it also moves counters. */
  onCommitmentChanged: () => void;
}) {
  return (
    <>
      {/* Scope first: it decides what everything below is allowed to show. */}
      <RelationScopeSection
        scope={scope}
        saving={saving}
        onChange={onScopeChange}
        onPrepare={onPrepare}
      />
      {/* Every dated record on one line of time, full width under the scope
          (owner request 2026-10-24): folded, it reads nothing. */}
      <RelationTimelineSection name={name} detail={detail} context={context} lng={lng} />
      {/* Two columns from `lg`, one below — and the ORDER carries meaning.
          LEFT is the person: who they are (address book), then what the two of
          you owe each other, then what LIA remembers, then the exchanges.
          RIGHT is what connected accounts happen to know. A single stack of ten
          cards of equal weight made the human part indistinguishable from the
          plumbing; the DOM order still reads person-first for a screen reader,
          since the grid never reorders. Sections render nothing when empty, so
          the order holds whatever the account actually has.

          Nothing that must be LAST on a phone can live in either column: below
          `lg` the columns stack, so the left one's tail sits in the middle of
          the page. Such a block goes below the grid — see `PeerLinkSection`. */}
      <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
        <div className="flex flex-col gap-4">
          {/* First, always: the address book answers "which person is this?",
              and every section below assumes that answer. */}
          <ProviderContactSection
            section={context?.contact}
            busy={refreshing.includes('contact')}
            onRefresh={() => onRefresh(['contact'])}
          />
          <OpenLoopsSection
            loops={detail.open_loops}
            total={detail.open_loops_total}
            lng={lng}
            onChanged={onCommitmentChanged}
          />
          <MemoriesSection memories={detail.memories} total={detail.memories_total} lng={lng} />
          <CallsSection calls={detail.recent_calls} total={detail.recent_calls_total} lng={lng} />
          <PeerMessagesSection messages={detail.peer_messages} total={detail.peer_messages_total} />
        </div>
        <div className="flex flex-col gap-4">
          <RelationSmsSection
            messages={detail.sms ?? []}
            total={detail.sms_total ?? 0}
            available={detail.sms_available ?? false}
            lng={lng}
          />
          <ProviderEmailsSection
            section={context?.emails}
            personName={detail.display_name}
            windowDays={context?.email_window_days ?? 0}
            lng={lng}
            busy={refreshing.includes('emails')}
            onRefresh={() => onRefresh(['emails'])}
          />
          <ProviderEventsSection
            section={context?.events}
            windowDays={context?.window_days ?? 0}
            busy={refreshing.includes('events')}
            onRefresh={() => onRefresh(['events'])}
          />
        </div>
      </div>
      <ProviderNote noteKey={providerNoteKey(context)} />
      {/* Last of the sheet, at every width: a note ABOUT the relationship, not
          one of its contents.

          It used to close the LEFT column, which read correctly on a desktop
          and wrongly on a phone: below `lg` the two columns stack, so the block
          landed in the MIDDLE of the page, between the relayed messages and the
          mail. No `order-*` class can move it — it was a child of the left
          column, never a sibling of the right one's sections.

          A full-width band under the grid is therefore ONE DOM for every width.
          The alternative, a `hidden lg:block` pair, would hand assistive
          technology two headings for one block. */}
      <PeerLinkSection link={detail.peer_link} />
    </>
  );
}

export function RelationDetailPanel({
  name,
  lng,
  isFavorite,
  onToggleFavorite,
  candidates,
  onMerged,
  onBack,
  debriefEnabled,
  onDebriefToggle,
}: {
  name: string;
  lng: string;
  /** Star state from the overview (single source; the panel never re-reads). */
  isFavorite: boolean;
  onToggleFavorite: (name: string, nextValue: boolean) => void;
  /** Debrief switch from the overview — same single-source rule as the star. */
  debriefEnabled: boolean;
  onDebriefToggle: (next: boolean) => void;
  /** Every relationship of the overview — the merge candidates. */
  candidates: string[];
  /** Bring the overview back in sync: a merge turns two cards into one. */
  onMerged: () => void;
  onBack: () => void;
}) {
  const { t } = useTranslation();
  const { detail, loading, refetch } = useRelationDetail(name);
  const { merge, split, busy: merging } = useRelationMerge();

  const applyMerge = useCallback(
    async (source: string) => {
      const result = await merge(source, name);
      if (result.ok) {
        // Both surfaces: this card absorbs the other, and the list loses one.
        await Promise.resolve(refetch());
        onMerged();
      }
      return result;
    },
    [merge, name, refetch, onMerged]
  );

  const applySplit = useCallback(
    async (source: string) => {
      const result = await split(source);
      if (result.ok) {
        await Promise.resolve(refetch());
        onMerged();
      }
      return result;
    },
    [split, refetch, onMerged]
  );
  // ONE scope for both entry points. The header button and the panel's own
  // button must not diverge: a reader who ticks boxes here and presses the
  // header button would otherwise silently get their PREVIOUS scope.
  const { scope, setDraft, saving, commit } = useScopeDraft();
  // Its own query, deliberately: the connectors are slow and fallible, and the
  // 360° view must be on screen long before they answer.
  const {
    context,
    loading: contextLoading,
    refreshing,
    refreshSections,
  } = useRelationContext(name);

  // The debrief is read at once (that read never builds) and BUILT only once
  // the provider sections have settled: it draws on the very caches they just
  // filled, so racing them would pay the external quota twice for one card.
  const {
    debrief,
    loading: debriefLoading,
    building: debriefBuilding,
    rebuild: rebuildDebrief,
  } = useRelationDebrief(name, { enabled: debriefEnabled, providerReady: !contextLoading });

  // Here — unlike the overview — staging the spinner on `loading` is CORRECT,
  // and must stay: this panel is keyed on a person, so when `name` changes the
  // still-loaded `detail` belongs to the PREVIOUS one. Rendering it under the
  // new name would show one person's commitments as another's. The overview
  // has no such hazard (a refetch returns the same list), which is why it
  // keeps its content mounted instead.
  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <LoadingSpinner className="h-6 w-6" />
      </div>
    );
  }
  if (!detail) return null;

  const prepIntent = t('relations.prepare_intent', { name: detail.display_name });
  /**
   * Save the scope, THEN open the chat.
   *
   * Awaited on purpose: the `?intent=` carries prose only, so the tool reads
   * the stored scope. Navigating first would race the write and hand the
   * assistant the previous selection with nothing on screen saying so. A
   * failed write still opens the chat — the stored scope is then what applies,
   * which is a worse answer than the reader asked for but never a silent
   * hang on a button that promised to do something.
   */
  const prepare = async () => {
    if (saving || scope.sections.length === 0) return;
    await commit();
    // The sentence is what the user reads; the directive is what the backend
    // GUARANTEES to run (ADR-191). Prose alone cannot carry a guarantee —
    // measured in production, the 360° tool scored 0.853, the best of the whole
    // catalogue, and the plan called the generic mail tool instead. The subject
    // is the name on screen, so what runs is what was displayed.
    // A REAL navigation, never `router.push`: the App Router restores the
    // search params of the entry it already holds for this route, so a second
    // 360° in the same session left with the FIRST person's URL (measured in
    // production 2026-08-01 — see `openChatDeepLink`).
    openChatDeepLink(
      chatIntentHref(lng, prepIntent, {
        capability: 'person_overview',
        subject: detail.display_name,
      })
    );
  };
  // The connection block counts: saying "nothing tracked" above a panel that
  // states since when you are connected and what you share would contradict
  // itself on screen.
  const isEmpty =
    detail.open_loops.length === 0 &&
    detail.recent_calls.length === 0 &&
    detail.peer_messages.length === 0 &&
    (detail.sms_total ?? 0) === 0 &&
    detail.memories.length === 0 &&
    detail.peer_link === null;

  return (
    <div className="space-y-5">
      <RelationHeader
        detail={detail}
        isFavorite={isFavorite}
        refreshing={contextLoading}
        onBack={onBack}
        onToggleFavorite={() => onToggleFavorite(detail.display_name, !isFavorite)}
        onRefreshAll={() => refreshSections([...CONTEXT_SECTIONS])}
      />

      {/* Right under who this is, above the debrief (owner request
          2026-10-29): what you can do with someone is read with their name,
          not after the synthesis. The caveat below stays next to the evidence
          it qualifies. */}
      <QuickActions detail={detail} card={contactCardOf(context)} lng={lng} />

      {/* Best-effort caveat: shown on a normalized name match OR whenever a
          memory is attached — memories are matched by name substring, which
          can over-match even on an EXACT loop/call identity (a common first
          name landing in an unrelated note). Honesty over false precision. */}
      {(detail.identity_confidence === 'normalized' || detail.memories.length > 0) && (
        <p className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          {t('relations.identity_best_effort')}
        </p>
      )}

      {/* The first section: it is the answer the reader came for. Everything
          below is the evidence they would otherwise have had to assemble
          themselves. */}
      <RelationDebriefSection
        debrief={debrief}
        loading={debriefLoading}
        building={debriefBuilding}
        enabled={debriefEnabled}
        lng={lng}
        onRebuild={rebuildDebrief}
        onToggle={onDebriefToggle}
      />

      <RelationSections
        name={name}
        detail={detail}
        context={context}
        onCommitmentChanged={() => void Promise.resolve(refetch())}
        refreshing={refreshing}
        lng={lng}
        onRefresh={refreshSections}
        scope={scope}
        saving={saving}
        onScopeChange={setDraft}
        onPrepare={prepare}
      />

      {isEmpty && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          {t('relations.detail_empty')}
        </p>
      )}

      {/* Last: merging CORRECTS what is above it, so it reads after the card
          rather than competing with it for attention. */}
      <RelationMergePanel
        displayName={detail.display_name}
        mergedFrom={detail.merged_from ?? []}
        candidates={candidates}
        busy={merging}
        onMerge={applyMerge}
        onSplit={applySplit}
      />
    </div>
  );
}
