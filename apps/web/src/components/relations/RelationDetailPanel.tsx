'use client';

/**
 * RelationDetailPanel — the 360° view of one relationship (N-09, restyled).
 *
 * Identity header (large avatar, peers badge, star), a row of quick actions,
 * the LIA connection block when one exists, then sectioned CARDS — open loops
 * with an age pill, dated calls, relayed peer messages, memories as bordered
 * notes. Every section shows a preview and reveals the rest on demand, with
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
  ArrowDownLeft,
  ArrowLeft,
  ArrowUpRight,
  ChevronDown,
  Handshake,
  RefreshCw,
  ListTodo,
  MessageSquare,
  PhoneCall,
  Star,
  StickyNote,
} from 'lucide-react';
import { Children, useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { RelationAvatar } from '@/components/relations/RelationAvatar';
import {
  CONTEXT_SECTIONS,
  ProviderContactSection,
  ProviderEmailsSection,
  ProviderEventsSection,
  ProviderNote,
  providerNoteKey,
} from '@/components/relations/RelationProviderSections';
import { CollapsibleSection, SectionBadge } from '@/components/relations/CollapsibleSection';
import { RelationMergePanel } from '@/components/relations/RelationMergePanel';
import { RelationScopeSection, useScopeDraft } from '@/components/relations/RelationScopeSection';
import { chatDraftHref, chatIntentHref, timeAgoLabel } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import {
  useRelationMerge,
  useRelationContext,
  useRelationDetail,
  type RelationContext,
  type RelationDetail,
  type RelationOverviewScope,
  type RelationPeerLink,
  type RelationPeerMessage,
  type RelationShare,
} from '@/hooks/useRelations';

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
      {visible}
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
 * One relayed message. The direction is carried by TRANSLATED TEXT, never by
 * the arrow alone — the icon is decorative. A message with no text says so
 * plainly instead of rendering an empty line (honesty rule).
 */
function PeerMessageItem({ message }: { message: RelationPeerMessage }) {
  const { t } = useTranslation();
  const received = message.direction === 'received';
  const DirectionIcon = received ? ArrowDownLeft : ArrowUpRight;

  return (
    <div className="border-l-2 border-primary/40 pl-3">
      <p className="flex flex-wrap items-baseline gap-2">
        <span className="inline-flex items-center gap-1 text-sm font-medium text-primary">
          <DirectionIcon className="h-3.5 w-3.5" aria-hidden="true" />
          {received ? t('relations.peer_message_received') : t('relations.peer_message_sent')}
        </span>
        <span className="text-[11px] text-muted-foreground">
          {timeAgoLabel(t, message.occurred_at)}
        </span>
      </p>
      {message.content ? (
        <p className="mt-0.5 whitespace-pre-line text-sm text-foreground/90">{message.content}</p>
      ) : (
        // Full muted-foreground, never a diluted /80: at 12px the faded pair
        // measures 3.51:1, under the 4.5:1 AA floor (axe, production bundle).
        <p className="mt-0.5 text-xs italic text-muted-foreground">
          {t('relations.peer_message_no_content')}
        </p>
      )}
    </div>
  );
}

/**
 * The LIA connection behind this relationship (peers spec §11, D2).
 *
 * Read-only by contract: sharing is granted and revoked in the Connections
 * settings. Both directions are shown — stating only what the user set up
 * would describe half of a two-sided arrangement. Share labels reuse the
 * settings table so one wording serves both screens.
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
            className="rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary"
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
          <span className="text-[11px] font-normal text-muted-foreground">
            {t('relations.peer_link_since', { when: timeAgoLabel(t, link.connected_since) })}
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

/** Open commitments, oldest-first as the API ranks them, with an age pill. */
function OpenLoopsSection({
  loops,
  total,
}: {
  loops: RelationDetail['open_loops'];
  total: number;
}) {
  const { t } = useTranslation();
  if (loops.length === 0) return null;
  return (
    <SectionCard icon={ListTodo} title={t('relations.section_open_loops')} total={total}>
      {loops.map(loop => (
        <p
          key={loop.id}
          className="flex flex-wrap items-baseline gap-2 border-l-2 border-amber-500/40 pl-3 text-sm text-foreground/90"
        >
          {loop.subject}
          {/* amber-800 for the AA floor at this size — see RelationCardList. */}
          <span className="rounded-full border border-amber-500/25 bg-amber-500/10 px-2 py-px text-[10px] font-medium text-amber-800 dark:text-amber-300">
            {t('relations.days_open', { count: loop.days_open })}
          </span>
        </p>
      ))}
    </SectionCard>
  );
}

/** Past calls — the objective and the outcome summary, never the number (D-8). */
function CallsSection({ calls, total }: { calls: RelationDetail['recent_calls']; total: number }) {
  const { t } = useTranslation();
  if (calls.length === 0) return null;
  return (
    <SectionCard icon={PhoneCall} title={t('relations.section_calls')} total={total}>
      {calls.map(call => (
        <div key={call.id} className="border-l-2 border-sky-500/40 pl-3">
          <p className="flex flex-wrap items-baseline gap-2 text-sm text-foreground/90">
            {call.objective}
            <span className="text-[11px] text-muted-foreground">
              {timeAgoLabel(t, call.created_at)}
            </span>
          </p>
          {call.summary && <p className="mt-0.5 text-xs text-muted-foreground">{call.summary}</p>}
        </div>
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
 * removal would promise a relay that cannot happen.
 */
function QuickActions({ detail, lng }: { detail: RelationDetail; lng: string }) {
  const { t } = useTranslation();
  const name = detail.display_name;

  const actions: { key: string; icon: typeof Handshake; label: string; draft: string }[] = [
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
      key: 'call',
      icon: PhoneCall,
      label: t('relations.action_call'),
      draft: t('relations.action_call_prefill', { name }),
    },
    {
      key: 'loop',
      icon: ListTodo,
      label: t('relations.action_loop'),
      draft: t('relations.action_loop_prefill', { name }),
    },
  ];

  return (
    <div className="flex flex-wrap gap-2">
      {actions.map(({ key, icon: Icon, label, draft }) => (
        <button
          key={key}
          type="button"
          onClick={() => openChatDeepLink(chatDraftHref(lng, draft))}
          // `min-h-11`: these read as chips, but they are the card's primary
          // actions and were 30 px tall on a phone — wide enough to look
          // clickable, too short to hit reliably (measured 2026-08-01).
          className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-border/60 bg-card px-2.5 py-1.5 text-xs font-medium text-foreground/90 transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          {label}
        </button>
      ))}
    </div>
  );
}

/** Stored memories mentioning this person (best-effort substring match). */
function MemoriesSection({
  memories,
  total,
}: {
  memories: RelationDetail['memories'];
  total: number;
}) {
  const { t } = useTranslation();
  if (memories.length === 0) return null;
  return (
    <SectionCard icon={StickyNote} title={t('relations.section_memories')} total={total}>
      {memories.map(memory => (
        <p
          key={memory.id}
          className="rounded-lg border border-border/40 bg-muted/30 px-3 py-2 text-sm text-foreground/90"
        >
          {memory.content}
        </p>
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
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/50 bg-card p-4">
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
                className="inline-flex shrink-0 items-center gap-1 rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary"
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
 * LIA remembers, then the exchanges (calls, mail, meetings), and finally the
 * LIA-specific material. The provider-backed ones are INTERLEAVED rather than
 * appended: they arrive later than the database-local ones, but they belong
 * where the reader expects them, not where the network happens to put them.
 *
 * Extracted so the panel above reads as what it is — an order — and stays
 * under the frontend complexity ratchet.
 */
function RelationSections({
  detail,
  context,
  refreshing,
  lng,
  onRefresh,
  scope,
  saving,
  onScopeChange,
  onPrepare,
}: {
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
}) {
  return (
    <>
      <RelationScopeSection
        scope={scope}
        saving={saving}
        onChange={onScopeChange}
        onPrepare={onPrepare}
      />
      <ProviderContactSection
        section={context?.contact}
        busy={refreshing.includes('contact')}
        onRefresh={() => onRefresh(['contact'])}
      />
      <OpenLoopsSection loops={detail.open_loops} total={detail.open_loops_total} />
      <MemoriesSection memories={detail.memories} total={detail.memories_total} />
      <CallsSection calls={detail.recent_calls} total={detail.recent_calls_total} />
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
      <PeerMessagesSection messages={detail.peer_messages} total={detail.peer_messages_total} />
      <PeerLinkSection link={detail.peer_link} />
      <ProviderNote noteKey={providerNoteKey(context)} />
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
}: {
  name: string;
  lng: string;
  /** Star state from the overview (single source; the panel never re-reads). */
  isFavorite: boolean;
  onToggleFavorite: (name: string, nextValue: boolean) => void;
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

      {/* Best-effort caveat: shown on a normalized name match OR whenever a
          memory is attached — memories are matched by name substring, which
          can over-match even on an EXACT loop/call identity (a common first
          name landing in an unrelated note). Honesty over false precision. */}
      {(detail.identity_confidence === 'normalized' || detail.memories.length > 0) && (
        <p className="rounded-md border border-border/40 bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          {t('relations.identity_best_effort')}
        </p>
      )}

      <QuickActions detail={detail} lng={lng} />

      <RelationSections
        detail={detail}
        context={context}
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
