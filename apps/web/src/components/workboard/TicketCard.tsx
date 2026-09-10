'use client';
/**
 * One ticket on the board (ADR-276).
 *
 * What it states, and what it deliberately does NOT:
 *
 * - **No status control.** The card sits IN its column, and below `lg` the
 *   column is named right above the list — repeating it on every card cost a
 *   whole row of vertical space for a fact already on screen. The column is
 *   changed by dragging the card, or in the panel that opens on a tap.
 * - **The WHOLE card is the handle.** A dedicated grip is a 16 px target on a
 *   phone; the card is the thing a finger reaches for, and the title keeps
 *   being the door — a press that travels 8 px is a drag, a press that does
 *   not is a tap. A draggable card is therefore named for what picking it up
 *   does, never for its title: the title button inside it already carries that
 *   name, and two controls answering to one name is a screen reader's dead end.
 * - **Who holds it, first.** The holder sits at the TOP of the card, above the
 *   title, with the actions menu at the right (owner arbitration, 2026-09-09):
 *   a board is scanned for « whose is this » before it is read. The bell sits
 *   UNDER the title, before the due date (owner, 2026-09-10): whether the
 *   chat will speak and by when are read as one line.
 * - **A late ticket keeps its date, and its outline breathes.** « En retard »
 *   is a second line under the date, never a replacement: the date says by
 *   when, the line says that it passed — its icon boxed like the bell above
 *   it, so the word starts exactly under the date. And the card wears an
 *   INNER frame, drawn inside its borders so the priority edge stays outside
 *   it, that breathes from the normal border colour to red where motion is
 *   welcome, and stands still, red, where it is not (owner, 2026-09-10).
 * - **Where nothing drags, the whole card is the door — and the column and
 *   the holder are LISTS on it.** Below `lg` the title button stretches over
 *   the card through a pseudo-element, the menu and the two lists raised above
 *   it: a finger landing on the date or the bell opens the ticket, and the
 *   lists — the column, then the holder UNDER it, every item wearing its
 *   glyph before its name — sit between the title and the date and are how a
 *   ticket moves when it cannot be dragged (owner, 2026-09-10). Where it
 *   can, the column is the drag and the card carries no list repeating the
 *   header it sits under.
 * - **The priority is the edge, never a badge.** The leading edge ranks it
 *   and `urgent` sits on its own ground; a badge saying « Élevée » repeated
 *   what the edge already showed (owner, 2026-09-09). The name stays for a
 *   reader who cannot see the colour, visually hidden.
 * - **A step counter only when the page holds the whole board.** A count shown
 *   to somebody is exact or it does not exist (ADR-185).
 * - **A skipped run says nothing.** Quota refused it or the conversation was
 *   busy: reporting « échoué » would accuse LIA of something it never tried.
 */
import { AlertTriangle, Bell, BellOff, Pencil, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { RowActions, type RowAction } from '@/components/ui/row-actions';
import { HolderSelect } from '@/components/workboard/HolderSelect';
import { StatusSelect } from '@/components/workboard/StatusSelect';
import type { Language } from '@/i18n/settings';
import { getIntlLocale } from '@/i18n/settings';
import { priorityAccent, priorityGround } from '@/lib/status-tone';
import { cn } from '@/lib/utils';
import { runFailure } from '@/lib/workboard/errors';
import {
  assignPatch,
  assigneeParty,
  childProgress,
  heldBy,
  isOverdue,
  ownerParty,
  runState,
  type PartyLabel,
  type PeerName,
  type RunState,
} from '@/lib/workboard/display';
import { partyIcon } from '@/lib/workboard/icons';
import type { TicketRow, TicketUpdateBody } from '@/types/workboard';

export interface TicketCardProps {
  ticket: TicketRow;
  /** Every row the board holds — the step counter needs the whole set. */
  loaded: readonly TicketRow[];
  /** The EXACT number of rows the filter matches. */
  total: number;
  meId: string | undefined;
  peers: readonly PeerName[];
  lng: Language;
  onOpen: (id: string) => void;
  onFollowChange: (id: string, follow: boolean) => void;
  onDelete: (ticket: TicketRow) => void;
  /**
   * Where nothing drags, the column and the holder are lists on the card;
   * a surface that cannot act (a read-only list) passes neither, and the
   * card draws none.
   */
  onStatusChange?: (id: string, status: string) => void;
  onAssigneeChange?: (id: string, patch: TicketUpdateBody) => void;
  /**
   * Sortable attributes and listeners, when the board is draggable. Spread on
   * the whole card rather than on a grip: a 16 px target is not a touch
   * target, and the card is what a finger reaches for.
   */
  dragHandle?: React.HTMLAttributes<HTMLElement>;
  className?: string;
}

/** The party glyph at the badge's size — the registry's, so the holder list
    below wears the same mark (lot 20). */
const BADGE_GLYPH = 'h-3 w-3';

/** How a party reads on a card. */
function partyLabel(party: PartyLabel, t: (key: string) => string): string {
  switch (party.kind) {
    case 'lia':
      return t('workboard.party.lia');
    case 'me':
      return t('workboard.party.me');
    case 'peer':
      return party.name;
    case 'unknown':
      return t('workboard.party.unknown');
  }
}

/** The late frame (see the card's class list): inside the borders, breathing. */
const OVERDUE_FRAME =
  "before:pointer-events-none before:absolute before:inset-0 before:rounded-md before:border-2 before:border-destructive before:content-[''] motion-safe:before:animate-overdue-pulse";

/** Run states the column header already states, so the card never repeats them. */
const COLUMN_SAYS_IT = new Set(['running', 'waiting']);

const RUN_TONE = {
  failed: 'destructive',
  waiting: 'warning',
  running: 'info',
  succeeded: 'success',
} as const;

/**
 * Whether THIS account hears about the ticket in the chat — each side reads
 * its own flag. A state, not the toggle: the toggle lives in the row menu, and
 * a glyph that acted on click would be a control with no name. It carries its
 * name for readers who cannot see the shape.
 */
function FollowMark({ following }: { following: boolean }) {
  const { t } = useTranslation();
  const label = t(following ? 'workboard.card.followed' : 'workboard.card.not_followed');
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      className={cn(
        'inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border',
        following
          ? 'border-primary/30 bg-primary/10 text-primary'
          : 'border-border/60 text-muted-foreground'
      )}
    >
      {following ? (
        <Bell className="h-3 w-3" aria-hidden="true" />
      ) : (
        <BellOff className="h-3 w-3" aria-hidden="true" />
      )}
    </span>
  );
}

/** The card's first line: the holder, the owner when it is not me, the menu. */
function CardHead({
  holder,
  owner,
  iAmOwner,
  actions,
  menuLabel,
}: {
  holder: PartyLabel;
  owner: PartyLabel;
  iAmOwner: boolean;
  actions: RowAction[];
  menuLabel: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <Badge variant="outline" icon={partyIcon(holder.kind, BADGE_GLYPH)}>
        {partyLabel(holder, t)}
      </Badge>
      {!iAmOwner && (
        <span className="inline-flex min-w-0 items-center gap-1 truncate text-muted-foreground">
          {partyIcon(owner.kind, BADGE_GLYPH)}
          {t('workboard.party.owned_by', { name: partyLabel(owner, t) })}
        </span>
      )}
      {/* ONE « ⋮ » whatever the viewport: a column is ~208 px wide on every
          screen, and three inline icon buttons left the title 64 px. Raised
          above the stretched door a phone draws over the card (see the title
          button), so the menu stays the menu. */}
      <RowActions
        compact
        className="relative z-10 ms-auto"
        actions={actions}
        menuLabel={menuLabel}
      />
    </div>
  );
}

/**
 * Everything the card states under its title: whether the chat will speak,
 * the deadline, what a run did, the steps — and, on its own line, that the
 * deadline has passed.
 */
function CardMeta({
  ticket,
  following,
  steps,
  run,
  late,
  locale,
}: {
  ticket: TicketRow;
  following: boolean;
  steps: { done: number; total: number } | null;
  run: ReturnType<typeof runState>;
  late: boolean;
  locale: string;
}) {
  const { t } = useTranslation();
  const dated = ticket.due_at;
  return (
    <div className="mt-2 space-y-1 text-[11px]">
      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
        {/* The bell leads the line and the date follows it (owner, 2026-09-10):
            « will the chat tell me, and by when » is one question. */}
        <FollowMark following={following} />
        {dated && (
          <span className="text-muted-foreground">
            {t('workboard.card.due', {
              date: new Intl.DateTimeFormat(locale, { dateStyle: 'short' }).format(new Date(dated)),
            })}
          </span>
        )}
        {/* Only what the COLUMN cannot say. `running` and `waiting` are read
            straight off the status, so their badge repeated the header the card
            sits under. A failure and a delivered result are not columns. */}
        {run && !COLUMN_SAYS_IT.has(run) && (
          <Badge variant={RUN_TONE[run]}>{t(`workboard.card.run_${run}`)}</Badge>
        )}
        {steps && <span className="text-muted-foreground">{t('workboard.card.steps', steps)}</span>}
      </div>
      {late && (
        // The date stays where it is; lateness is a SECOND line under it, never
        // a replacement — the date says by when, this says that it passed.
        <p className="flex items-center gap-1.5 font-medium text-destructive">
          {/* Boxed like the bell above it — the same 20 px column, the same
              gap — so the word starts exactly under the date (owner,
              2026-09-10). The icon is decorative: the sentence beside it
              already says « en retard », so a reader who cannot see colour or
              shape loses nothing. */}
          <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center">
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
          </span>
          <span>{t('workboard.card.overdue')}</span>
        </p>
      )}
    </div>
  );
}

/**
 * Why the last run failed — the SENTENCE, never the code.
 *
 * `last_run_error` stores `workboard_run_failed: TimeoutError…`; printing it
 * whole put a machine identifier in front of a person in six languages, while
 * the backend's own contract says the board resolves the code from the
 * locales. The technical half stays as the tooltip: evidence for whoever
 * wants it, never the heading.
 *
 * Its own block, like `CardHead` and `CardMeta`: the card composes, it does
 * not carry each block's conditions.
 */
function RunFailureLine({ ticket, run }: { ticket: TicketRow; run: RunState }) {
  const { t } = useTranslation();
  const failure = runFailure(t, ticket.last_run_error);
  if (!failure || run !== 'failed') return null;
  return (
    <p className="mt-2 truncate text-[11px] text-destructive" title={failure.detail ?? failure.label}>
      {failure.label}
    </p>
  );
}

export function TicketCard({
  ticket,
  loaded,
  total,
  meId,
  peers,
  lng,
  onOpen,
  onFollowChange,
  onDelete,
  onStatusChange,
  onAssigneeChange,
  dragHandle,
  className,
}: TicketCardProps) {
  const { t } = useTranslation();
  const locale = getIntlLocale(lng);

  const holder = assigneeParty(ticket, meId, peers);
  const owner = ownerParty(ticket, meId, peers);
  const iAmOwner = owner.kind === 'me';
  const late = isOverdue(ticket);
  const steps = childProgress(ticket, loaded, total);
  const run = runState(ticket);
  // Each side follows its OWN flag: the owner's bell is not the holder's.
  const following = iAmOwner ? ticket.follow_owner : ticket.follow_assignee;

  const actions: RowAction[] = [
    {
      key: 'open',
      label: t('workboard.card.open'),
      icon: Pencil,
      onSelect: () => onOpen(ticket.id),
    },
    {
      key: 'follow',
      label: following ? t('workboard.card.follow_off') : t('workboard.card.follow_on'),
      icon: following ? Bell : BellOff,
      onSelect: () => onFollowChange(ticket.id, !following),
    },
  ];
  // Only the owner may delete: offering the action to a holder would be a
  // question with one answer (`workboard_peer_cannot_delete`).
  if (iAmOwner) {
    actions.push({
      key: 'delete',
      label: t('workboard.card.delete'),
      icon: Trash2,
      tone: 'destructive',
      onSelect: () => onDelete(ticket),
    });
  }

  return (
    <article
      data-testid="ticket-card"
      data-ticket-id={ticket.id}
      className={cn(
        'relative rounded-lg border border-l-4 border-border/60 bg-card/80 p-3 shadow-sm',
        'focus-within:ring-2 focus-within:ring-ring',
        // The edge RANKS the priority — the only place it is said in colour.
        priorityAccent(ticket.priority),
        // `urgent` and `high` share an edge tone family; the ground is what
        // separates them across a whole board without shouting on one card.
        priorityGround(ticket.priority),
        // Late is stated three ways: the edge stays the priority's, so lateness
        // gets its own frame, its own icon and its own sentence. The frame is a
        // pseudo-element on the PADDING box — `inset-0` is measured from the
        // inner edge of the borders, by definition — so on the left it starts
        // AFTER the priority edge, which stays outside it in its own tone, and
        // elsewhere it sits just inside the 1 px border. It breathes from the
        // card's normal border colour to red only where motion is welcome:
        // under `prefers-reduced-motion` it stands still, red — the animation's
        // end state rather than its absence (owner, 2026-09-10). Under the
        // content and the stretched door, and no target for a finger.
        late && OVERDUE_FRAME,
        dragHandle && 'cursor-grab touch-none active:cursor-grabbing',
        className
      )}
      // Two controls must never share one name. Once the listeners are on
      // the card, the card IS a drag control (dnd-kit gives it `role="button"`
      // and `aria-roledescription="sortable"`), and the title button inside it
      // is the door — so the card is named for what PICKING IT UP does, and
      // the title keeps naming what OPENING it does.
      aria-label={
        dragHandle ? t('workboard.card.drag_card', { title: ticket.title }) : ticket.title
      }
      {...dragHandle}
    >
      <CardHead
        holder={holder}
        owner={owner}
        iAmOwner={iAmOwner}
        actions={actions}
        menuLabel={t('workboard.card.actions')}
      />

      <button
        type="button"
        // The title stays the door. It stops the pointer and the keys from
        // reaching the card's drag listeners, so opening a ticket can never
        // be read as the start of a drag. Where nothing drags (below `lg`)
        // the door STRETCHES over the whole card through a pseudo-element,
        // so a finger landing on the date or the bell opens the ticket too —
        // the menu sits above it (owner, 2026-09-10).
        className={cn(
          'mt-2 block w-full min-w-0 text-left text-sm font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          !dragHandle && "after:absolute after:inset-0 after:content-['']"
        )}
        onPointerDown={event => event.stopPropagation()}
        onKeyDown={event => event.stopPropagation()}
        onClick={() => onOpen(ticket.id)}
      >
        {ticket.title}
      </button>
      {/* The edge ranks the priority for a reader who sees colour; the word
          is here for one who does not — visually hidden, never a badge, and
          outside the meta row so a card with nothing else to say keeps no
          empty row under its title. */}
      <span className="sr-only">{t(`workboard.priority.${ticket.priority}`)}</span>

      {!dragHandle && onStatusChange && onAssigneeChange && (
        // Raised above the stretched door, so the lists stay lists — the
        // column, then the holder UNDER it, never beside (owner, 2026-09-10):
        // two half-width lists on a phone truncate their own options. Each
        // is named with the ticket: a column of cards each saying « Colonne »
        // tells a screen reader nothing about which one.
        <div className="relative z-10 mt-2 space-y-2">
          <StatusSelect
            id={`wb-card-status-${ticket.id}`}
            label={t('workboard.card.column_of', { title: ticket.title })}
            value={ticket.status}
            onChange={status => onStatusChange(ticket.id, status)}
          />
          {iAmOwner && (
            <HolderSelect
              id={`wb-card-holder-${ticket.id}`}
              label={t('workboard.card.holder_of', { title: ticket.title })}
              value={heldBy(ticket)}
              peers={peers}
              onChange={choice => onAssigneeChange(ticket.id, assignPatch(choice))}
            />
          )}
        </div>
      )}

      <CardMeta
        ticket={ticket}
        following={following}
        steps={steps}
        run={run}
        late={late}
        locale={locale}
      />

      <RunFailureLine ticket={ticket} run={run} />
    </article>
  );
}
