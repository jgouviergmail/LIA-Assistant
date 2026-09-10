'use client';
/**
 * The panels a ticket's detail is made of (ADR-276).
 *
 * Extracted from `TicketDetailPanel` so that one component is not a decision
 * tree: each block answers one question — what the last run did, what it has
 * cost, what the steps are, what has been said, what happened — and each is
 * small enough to read in one go. The panel composes them and owns the I/O.
 *
 * Every block is a `Panel`: the same frame, the same heading with its theme
 * icon, so the detail reads as a set of cards rather than a column of
 * headings of unequal weight (owner feedback, 2026-09-09: « la mise en forme
 * n'est pas propre »). A panel that has nothing to show renders nothing.
 */
import { Coins, History, ListTree, MessageSquare, Sparkles } from 'lucide-react';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { UsageLine, meterFigures, type Figure } from '@/components/workboard/UsageLine';
import { useAuth } from '@/hooks/useAuth';
import { lifecycleTone } from '@/lib/status-tone';
import { cn } from '@/lib/utils';
import { eventChanges, eventLabelKey, type EventChange } from '@/lib/workboard/display';
import { runFailure } from '@/lib/workboard/errors';
import type { CommentRow, EventRow, RunOutcome, TicketRow } from '@/types/workboard';

/** A block heading: a title always carries an icon, in the theme colour. */
function Heading({
  id,
  icon: Icon,
  children,
}: {
  id?: string;
  icon: typeof History;
  children: React.ReactNode;
}) {
  return (
    <h4 id={id} className="flex items-center gap-2 text-sm font-semibold">
      <Icon className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
      {children}
    </h4>
  );
}

export interface PanelProps {
  icon: typeof History;
  title: string;
  /** What sits at the heading's right — a date, a count — muted. */
  aside?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

/**
 * One framed section of the detail, named by its heading.
 *
 * A `section` labelled by its own heading, so the dialog's outline is a list
 * of named regions rather than an undifferentiated column. The frame is a
 * CARD — `bg-card` over the dialog's `bg-background`, a full-strength border
 * and a shadow: a muted wash at 20 % measured invisible in light mode
 * (owner, 2026-09-10 — 93 % lightness at a fifth over 95 % is 94,6 %).
 */
export function Panel({ icon, title, aside, children, className }: PanelProps) {
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      className={cn('rounded-xl border border-border bg-card p-3 shadow-sm', className)}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <Heading id={headingId} icon={icon}>
          {title}
        </Heading>
        {aside && <span className="text-xs text-muted-foreground">{aside}</span>}
      </div>
      {children}
    </section>
  );
}

/** Whether the ticket has spent anything at all — a row of zeros is noise. */
export function hasUsage(ticket: TicketRow): boolean {
  return (
    ticket.total_tokens_in + ticket.total_tokens_out + ticket.total_tokens_cache > 0 ||
    ticket.total_google_requests > 0
  );
}

/**
 * The tone of each verdict. A quota refusal and a run that stood aside for a
 * live conversation are NOT failures (ADR-272's logging rule): grey, the tone
 * of what did not happen. `Record` over the enum: a verdict the backend adds
 * fails to compile here rather than falling back to a colour.
 */
const OUTCOME_TONE: Record<RunOutcome, 'success' | 'warning' | 'destructive' | 'outline'> = {
  success: 'success',
  waiting: 'warning',
  confirming: 'warning',
  failed: 'destructive',
  skipped_quota: 'outline',
  skipped_busy: 'outline',
};

/**
 * What LIA's last run did, and what it cost.
 *
 * The VERDICT, in the panel's own words — never the column: a failed run
 * leaves the ticket in the column it was found in, so « À faire » under
 * « Dernière exécution » said nothing about the run (cold review, lot 15).
 * The cost comes from the SNAPSHOT the ticket carries (ADR-276 D18), never
 * from a join at render time on a register that outlives the account, and
 * follows the header's own « show figures » switch as the chat's per-message
 * line does; a skipped run spent nothing and carries none.
 */
export function LastRunBlock({ ticket, locale }: { ticket: TicketRow; locale: string }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const outcome = ticket.last_run_outcome;
  if (!outcome) return null;
  const runCost = ticket.last_run_cost_eur;
  const failure = runFailure(t, ticket.last_run_error);

  return (
    <Panel
      icon={Sparkles}
      title={t('workboard.detail.last_run')}
      aside={
        ticket.last_run_at &&
        new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(
          new Date(ticket.last_run_at)
        )
      }
    >
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        <Badge variant={OUTCOME_TONE[outcome]}>{t(`workboard.detail.outcome_${outcome}`)}</Badge>
      </div>
      {user?.tokens_display_enabled && runCost !== null && (
        // Six decimals, as a message's own line shows its cost.
        <UsageLine
          figures={[
            ['🟠', 'IN', ticket.last_run_tokens_in ?? 0],
            ['🟢', 'OUT', ticket.last_run_tokens_out ?? 0],
          ]}
          cost={runCost}
          decimals={6}
        />
      )}
      {failure && (
        // The sentence, then the evidence under it — smaller and muted, so a
        // stack-trace fragment never reads as the panel's own words.
        <div className="mt-2 space-y-0.5">
          <p className="text-xs text-destructive">{failure.label}</p>
          {failure.detail && (
            <p className="break-words font-mono text-[11px] text-muted-foreground">
              {failure.detail}
            </p>
          )}
        </div>
      )}
    </Panel>
  );
}

/**
 * What the ticket has cost since it was created — ONE line.
 *
 * The question a person actually asks about a ticket run up to ten times —
 * « what did this cost me » — answered in the SAME vocabulary the chat's
 * meter uses (🟠 IN · 🟢 OUT · 🔵 CACHE · 🟣 GOOGLE, then the euros), from the
 * totals the settle accumulates on the row rather than from a join on a
 * register that outlives the account. The run count sits beside the title.
 *
 * Shown only when the person asked to see figures at all (the header's own
 * switch, `tokens_display_enabled`) and only once something has been spent.
 */
export function TicketUsageBlock({ ticket }: { ticket: TicketRow }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  if (!user?.tokens_display_enabled || !hasUsage(ticket)) return null;

  const figures: readonly Figure[] = meterFigures({
    tokens_in: ticket.total_tokens_in,
    tokens_out: ticket.total_tokens_out,
    tokens_cache: ticket.total_tokens_cache,
    google_requests: ticket.total_google_requests,
  });

  return (
    <Panel
      icon={Coins}
      title={t('workboard.detail.usage')}
      aside={t('workboard.detail.usage_runs', { count: ticket.run_count })}
    >
      {/* Two decimals, as the conversation pill shows its total. */}
      <UsageLine figures={figures} cost={ticket.total_cost_eur} decimals={2} />
    </Panel>
  );
}

/** The ticket's steps — child tickets, one level (D9). */
export function StepsBlock({ steps }: { steps: readonly TicketRow[] }) {
  const { t } = useTranslation();
  return (
    <Panel icon={ListTree} title={t('workboard.detail.steps')}>
      {steps.length === 0 ? (
        <p className="mt-1 text-xs text-muted-foreground">{t('workboard.detail.no_step')}</p>
      ) : (
        <ul className="mt-2 space-y-1">
          {steps.map(child => (
            <li key={child.id} className="flex items-center gap-2 text-sm">
              <Badge variant={lifecycleTone(child.status)}>
                {t(`workboard.columns.${child.status}`)}
              </Badge>
              <span className="min-w-0 truncate">{child.title}</span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

/** The thread both sides read, LIA's run answers included. */
export function CommentsBlock({
  comments,
  locale,
  children,
}: {
  comments: readonly CommentRow[];
  /** The reader's locale: a thread without instants cannot be read in order. */
  locale: string;
  /** The composer, owned by the panel because it writes. */
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <Panel icon={MessageSquare} title={t('workboard.detail.comments')}>
      {comments.length === 0 ? (
        <p className="mt-1 text-xs text-muted-foreground">{t('workboard.detail.no_comment')}</p>
      ) : (
        // No rule between two turns: the dated HEAD of each one, on a pastel
        // band of the theme colour, is what separates them (owner, 2026-09-10)
        // — a thread is read as a sequence, and the band is the boundary.
        <ul className="mt-2 space-y-3">
          {comments.map(row => (
            <li key={row.id} className="text-sm">
              {/* Who said it AND when, both in weight: a run's answer and the
                  reply it drew read as one conversation only if the thread is
                  dated, and only if each turn's head is findable at a glance. */}
              <div className="flex flex-wrap items-baseline gap-x-2 rounded-md bg-primary/10 px-2 py-1 text-xs font-semibold text-foreground">
                <span>{t(`workboard.detail.author_${row.author_kind}`)}</span>
                <time dateTime={row.created_at}>
                  {new Intl.DateTimeFormat(locale, {
                    dateStyle: 'short',
                    timeStyle: 'short',
                  }).format(new Date(row.created_at))}
                </time>
              </div>
              <p className="mt-1.5 whitespace-pre-line px-2">{row.body}</p>
            </li>
          ))}
        </ul>
      )}
      {children}
    </Panel>
  );
}

/** One change, in the reader's words, their locale and their timezone. */
function Change({ change, locale }: { change: EventChange; locale: string }) {
  const { t } = useTranslation();
  const stamp = (value: string | null) =>
    value
      ? new Intl.DateTimeFormat(locale, { dateStyle: 'short' }).format(new Date(value))
      : t('workboard.history.none');

  // The punctuation between a label and its value travels with the LABELS
  // (an unbreakable space before a French colon, a full-width colon in
  // Chinese): a literal « : » here published French punctuation in six
  // languages — the trap lot 13 closed on the backend's preview labels.
  const sep = t('workboard.history.separator');
  if (change.field === 'created_in') {
    return (
      <span>
        {t('workboard.history.status')}
        {sep}
        {change.to ? t(`workboard.columns.${change.to}`) : t('workboard.history.none')}
      </span>
    );
  }
  if (change.field === 'follow') {
    return (
      <span>
        {t('workboard.history.follow')}
        {sep}
        {t(`workboard.history.${change.on ? 'on' : 'off'}`)}
      </span>
    );
  }
  const named = (value: string | null) => {
    if (!value) return t('workboard.history.none');
    if (change.field === 'status') return t(`workboard.columns.${value}`);
    if (change.field === 'priority') return t(`workboard.priority.${value}`);
    return stamp(value);
  };
  return (
    <span>
      {t(`workboard.history.${change.field}`)}
      {sep}
      {named(change.from)}
      {' → '}
      {named(change.to)}
    </span>
  );
}

/**
 * What happened, and who did it.
 *
 * The event log holds what PEOPLE did; what LIA did is also in the ADR-263
 * registers. The two never add up and are never joined — this block shows the
 * ticket's own log and nothing else.
 */
export function HistoryBlock({ events, locale }: { events: readonly EventRow[]; locale: string }) {
  const { t } = useTranslation();
  return (
    <Panel icon={History} title={t('workboard.detail.history')}>
      {events.length === 0 ? (
        <p className="mt-1 text-xs text-muted-foreground">{t('workboard.detail.no_history')}</p>
      ) : (
        <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
          {events.map(event => {
            const changes = eventChanges(event);
            return (
              <li key={event.id} className="flex flex-wrap items-baseline gap-x-1.5">
                <span className="font-medium text-foreground">{t(eventLabelKey(event))}</span>
                {changes.map((change, index) => (
                  <Change key={`${event.id}-${index}`} change={change} locale={locale} />
                ))}
                <time dateTime={event.created_at} className="ms-auto">
                  {new Intl.DateTimeFormat(locale, {
                    dateStyle: 'short',
                    timeStyle: 'short',
                  }).format(new Date(event.created_at))}
                </time>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
