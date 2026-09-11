'use client';
/**
 * One ticket, in full (ADR-276).
 *
 * A real `Dialog`, not a `div role="dialog"`: focus trapping, `Esc`, and the
 * return of focus to the card come with the primitive and would each be a
 * separate defect hand-rolled.
 *
 * **The body is KEYED by the ticket id.** Opening another ticket remounts it,
 * so the fetched detail, the first-load flag and a half-typed comment reset by
 * construction — there is no effect resetting state, which is what a comment
 * box left holding the previous ticket's draft would have needed. « State that
 * depends on a prop » is a key, not an effect.
 *
 * **Seven panels, one frame.** Details, settings, last run, cost, steps,
 * comments, history — each a `Panel` with its theme icon, each on its own
 * line at the full width (owner feedback, 2026-09-09: parts of the detail
 * were not aligned and read as a column of headings; and the cost is ONE
 * line by contract, which half a dialog could not hold).
 *
 * Two rules the rights impose, enforced here as well as by the service:
 *
 * - **The title and the description are the OWNER's words.** A holder who is
 *   not the owner reads them; they do not edit them
 *   (`workboard_peer_cannot_edit_field`). Rendering an input that can only
 *   ever be refused is a question with one answer.
 * - **« Run now » exists only for a ticket LIA holds** (the service refuses it
 *   otherwise: `workboard_run_now_requires_lia`).
 */
import { useCallback, useEffect, useState } from 'react';
import { FileText, PlayCircle, Send, SlidersHorizontal, Trash2, Undo2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { ExecutionModeField } from '@/components/workboard/ExecutionModeField';
import { HolderSelect } from '@/components/workboard/HolderSelect';
import { PrioritySelect } from '@/components/workboard/PrioritySelect';
import { StatusSelect } from '@/components/workboard/StatusSelect';
import {
  CommentsBlock,
  HistoryBlock,
  LastRunBlock,
  Panel,
  StepsBlock,
  TicketUsageBlock,
} from '@/components/workboard/TicketDetailSections';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { workboardApi } from '@/lib/workboard/api';
import { dueAtFromInput, dueDateInput } from '@/lib/workboard/dates';
import { assignPatch, heldBy, ownerParty, type PeerName } from '@/lib/workboard/display';
import { columnIcon } from '@/lib/workboard/icons';
import { type ExecutionMode, type TicketDetail, type TicketUpdateBody } from '@/types/workboard';

/** What the panel needs to act on a ticket. */
interface PanelActions {
  onClose: () => void;
  onPatch: (id: string, body: TicketUpdateBody) => Promise<{ ok: boolean }>;
  onComment: (id: string, body: string) => Promise<{ ok: boolean }>;
  onRunNow: (id: string) => Promise<{ ok: boolean }>;
  onDelete: (id: string, title: string) => void;
}

export interface TicketDetailPanelProps extends PanelActions {
  ticketId: string | null;
  meId: string | undefined;
  peers: readonly PeerName[];
  lng: Language;
  /** Bumped by the page after any write, so the panel re-reads the ticket. */
  revision?: number;
}

interface BodyProps extends PanelActions {
  ticketId: string;
  meId: string | undefined;
  peers: readonly PeerName[];
  lng: Language;
  revision: number;
}

/** The owner's two free-text fields, saved on blur. */
function OwnerFields({
  ticket,
  onPatch,
}: {
  ticket: TicketDetail['ticket'];
  onPatch: PanelActions['onPatch'];
}) {
  const { t } = useTranslation();
  return (
    <div className="mt-2 space-y-3">
      <div className="space-y-2">
        <Label htmlFor="wb-title">{t('workboard.form.title')}</Label>
        <Input
          id="wb-title"
          defaultValue={ticket.title}
          onBlur={event => {
            const next = event.target.value.trim();
            if (next && next !== ticket.title) void onPatch(ticket.id, { title: next });
          }}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="wb-description">{t('workboard.form.description')}</Label>
        <Textarea
          id="wb-description"
          rows={4}
          defaultValue={ticket.description ?? ''}
          onBlur={event => {
            if (event.target.value !== (ticket.description ?? '')) {
              void onPatch(ticket.id, { description: event.target.value });
            }
          }}
        />
      </div>
    </div>
  );
}

/**
 * Who holds the ticket, as a control.
 *
 * The owner may hand it to anybody they are connected to, to LIA, or take it
 * back; a peer holding it may only hand it BACK, which is the one thing the
 * service lets them do (`workboard_peer_cannot_reassign`). Offering a holder
 * the full list would be a menu whose every entry but one is refused.
 */
function AssigneeField({
  ticket,
  meId,
  peers,
  onPatch,
}: {
  ticket: TicketDetail['ticket'];
  meId: string | undefined;
  peers: readonly PeerName[];
  onPatch: PanelActions['onPatch'];
}) {
  const { t } = useTranslation();
  const iAmOwner = ticket.owner_user_id === meId;
  const held = heldBy(ticket);

  if (!iAmOwner) {
    return (
      <div className="space-y-2">
        <Label htmlFor="wb-hand-back">{t('workboard.form.assignee')}</Label>
        <Button
          id="wb-hand-back"
          variant="outline"
          className="h-10 w-full"
          onClick={() => void onPatch(ticket.id, { assignee_user_id: null })}
        >
          <Undo2 className="mr-2 h-4 w-4" aria-hidden="true" />
          {t('workboard.form.hand_back')}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* The select renders its OWN label, like `StatusSelect` beside it. */}
      <HolderSelect
        id="wb-assignee"
        hideLabel={false}
        label={t('workboard.form.assignee')}
        value={held}
        peers={peers}
        className="h-10 px-3 text-sm"
        onChange={choice => void onPatch(ticket.id, assignPatch(choice))}
      />
    </div>
  );
}

/** The column, the holder, the priority, the dates and the modes, written straight through. */
function TicketFields({
  ticket,
  meId,
  peers,
  onPatch,
}: {
  ticket: TicketDetail['ticket'];
  meId: string | undefined;
  peers: readonly PeerName[];
  onPatch: PanelActions['onPatch'];
}) {
  const { t } = useTranslation();
  // Whichever side of the ticket the reader is on: the owner subscribes with
  // `follow_owner`, a holder with `follow_assignee`, and the API reads the
  // caller's own flag from `follow` — one control, never two.
  const followed = ticket.owner_user_id === meId ? ticket.follow_owner : ticket.follow_assignee;
  return (
    <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
      <div className="space-y-2">
        {/* The select renders its OWN label: a second `<Label htmlFor>` beside
            it would give the control two accessible names. */}
        <StatusSelect
          id="wb-status"
          hideLabel={false}
          label={t('workboard.form.status')}
          value={ticket.status}
          className="h-10 text-sm"
          onChange={status => void onPatch(ticket.id, { status })}
        />
      </div>
      {/* The column and the holder FIRST: on a phone nothing drags, so these
          two lists are how a ticket moves (owner, 2026-09-10). */}
      <AssigneeField ticket={ticket} meId={meId} peers={peers} onPatch={onPatch} />
      <div className="space-y-2">
        {/* The same ranked list the form and the filter bar carry (D81). */}
        <PrioritySelect
          id="wb-priority"
          hideLabel={false}
          label={t('workboard.form.priority')}
          value={ticket.priority}
          className="h-10 px-3 text-sm"
          onChange={priority => void onPatch(ticket.id, { priority })}
        />
      </div>
      {/* A ticket is engaged for days: its deadline, the mode LIA runs it in
          and whether it speaks in the chat are all things a person changes
          mid-flight, so they live here and not only in the creation form. */}
      <div className="space-y-2">
        <Label htmlFor="wb-due">{t('workboard.form.due_at')}</Label>
        {/* The day is the READER's, at both ends: `dueDateInput` reads the
            stored instant in their zone (slicing the ISO string showed the
            UTC day, a day off west of Greenwich) and `dueAtFromInput` stores
            the END of the day they picked — midnight UTC made a ticket
            overdue at midday on its own due date. */}
        <Input
          id="wb-due"
          type="date"
          className="h-10"
          value={dueDateInput(ticket.due_at)}
          onChange={event => {
            const due = dueAtFromInput(event.target.value);
            void onPatch(ticket.id, due ? { due_at: due } : { clear_due_at: true });
          }}
        />
      </div>
      <ExecutionModeField
        id="wb-mode"
        value={ticket.execution_mode as ExecutionMode}
        onChange={mode => void onPatch(ticket.id, { execution_mode: mode })}
      />
      <div className="flex items-center gap-3 self-end pb-2">
        <Switch
          id="wb-follow"
          checked={followed}
          onCheckedChange={follow => void onPatch(ticket.id, { follow })}
          aria-label={t('workboard.form.follow')}
        />
        <Label htmlFor="wb-follow">{t('workboard.form.follow')}</Label>
      </div>
    </div>
  );
}

function TicketDetailBody({
  ticketId,
  meId,
  peers,
  lng,
  revision,
  onClose,
  onPatch,
  onComment,
  onRunNow,
  onDelete,
}: BodyProps) {
  const { t } = useTranslation();
  const locale = getIntlLocale(lng);
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [firstLoad, setFirstLoad] = useState(true);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void workboardApi
      .detail(ticketId)
      .then(payload => {
        if (!cancelled) setDetail(payload);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      })
      .finally(() => {
        if (!cancelled) setFirstLoad(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticketId, revision]);

  const send = useCallback(async () => {
    if (!comment.trim() || busy) return;
    setBusy(true);
    const result = await onComment(ticketId, comment.trim());
    setBusy(false);
    if (result.ok) setComment('');
  }, [busy, comment, onComment, ticketId]);

  if (firstLoad || !detail) {
    return (
      <>
        <DialogHeader>
          <DialogTitle>{t('workboard.detail.loading')}</DialogTitle>
        </DialogHeader>
        <Skeleton className="h-40 w-full" />
      </>
    );
  }

  const { ticket } = detail;
  const iAmOwner = ownerParty(ticket, meId, peers).kind === 'me';

  return (
    <>
      <DialogHeader>
        <DialogTitle className="pr-8 text-left">{ticket.title}</DialogTitle>
        <DialogDescription className="text-left">
          {iAmOwner ? t('workboard.detail.editable') : t('workboard.detail.read_only')}
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-3" aria-busy={busy}>
        {/* Lot 7: LIA put an action on the ticket and waits. The comment says
            what; this says HOW to answer, because nothing else on the screen
            does — a comment box and a « who holds it » control are not a
            protocol until somebody names it. */}
        {ticket.status === 'confirming' && (
          <p
            role="note"
            className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm"
          >
            {columnIcon('confirming', 'mt-0.5 h-4 w-4 shrink-0 text-warning')}
            <span>{t('workboard.detail.confirming_hint')}</span>
          </p>
        )}

        <Panel icon={FileText} title={t('workboard.detail.data')}>
          {iAmOwner ? (
            <OwnerFields ticket={ticket} onPatch={onPatch} />
          ) : (
            <p className="mt-2 whitespace-pre-line text-sm text-foreground/90">
              {ticket.description || t('workboard.history.none')}
            </p>
          )}
        </Panel>

        <Panel icon={SlidersHorizontal} title={t('workboard.detail.settings')}>
          <TicketFields ticket={ticket} meId={meId} peers={peers} onPatch={onPatch} />
        </Panel>

        {/* Each on its own line, at the full width: the cost is ONE line by
            contract, and half a dialog cannot hold it. Both render nothing
            until there is something to say. */}
        <LastRunBlock ticket={ticket} locale={locale} />
        <TicketUsageBlock ticket={ticket} />

        <StepsBlock steps={detail.children} />
        <CommentsBlock comments={detail.comments} locale={locale}>
          <div className="mt-2 flex gap-2">
            <Textarea
              rows={2}
              value={comment}
              aria-label={t('workboard.detail.comment_placeholder')}
              placeholder={t('workboard.detail.comment_placeholder')}
              onChange={event => setComment(event.target.value)}
            />
            <Button
              variant="outline"
              size="icon"
              aria-label={t('workboard.actions.comment')}
              aria-disabled={!comment.trim() || busy}
              onClick={send}
            >
              <Send className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        </CommentsBlock>
        <HistoryBlock events={detail.events} locale={locale} />

        <div className="flex flex-wrap justify-end gap-2 border-t border-border/60 pt-3">
          {ticket.assignee_kind === 'lia' && (
            <Button variant="outline" onClick={() => void onRunNow(ticket.id)}>
              <PlayCircle className="mr-2 h-4 w-4" aria-hidden="true" />
              {t('workboard.actions.run_now')}
            </Button>
          )}
          {iAmOwner && (
            <Button
              variant="outline"
              className="text-destructive"
              onClick={() => onDelete(ticket.id, ticket.title)}
            >
              <Trash2 className="mr-2 h-4 w-4" aria-hidden="true" />
              {t('workboard.card.delete')}
            </Button>
          )}
          <Button variant="outline" onClick={onClose}>
            {t('workboard.actions.close')}
          </Button>
        </div>
      </div>
    </>
  );
}

export function TicketDetailPanel({
  ticketId,
  revision = 0,
  onClose,
  ...rest
}: TicketDetailPanelProps) {
  return (
    <Dialog open={ticketId !== null} onOpenChange={open => (open ? undefined : onClose())}>
      <DialogContent className="max-h-[90dvh] max-w-2xl overflow-y-auto">
        {ticketId && (
          // The key is what resets the fetched detail, the first-load flag and
          // a half-typed comment when another ticket opens.
          <TicketDetailBody
            key={ticketId}
            ticketId={ticketId}
            revision={revision}
            onClose={onClose}
            {...rest}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
