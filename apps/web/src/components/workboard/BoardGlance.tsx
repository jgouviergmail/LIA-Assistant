'use client';
/**
 * The board at a glance, above its own filters (ADR-276, amendment 2026-11-11).
 *
 * These figures were a settings section — the board's only door besides a
 * notification (D16). The owner gave the board a header destination and moved
 * them here. Every figure is still an aggregate over the WHOLE board
 * (ADR-185), whatever the filters under it say, and pressing one narrows the
 * board to it, in place.
 *
 * On the settings page a figure was a link into the board. Here it is a
 * BUTTON: this page's filters start from the URL and lead it from then on, so
 * a link to the page it is already on would be undone by the page's own state.
 *
 * The block folds (`Disclosure`), and folds SHUT on arrival where the screen
 * is small — below `lg` the board already shows one column at a time. Shut, it
 * reads nothing: the figures are children of the fold, and a closed fold has
 * none. What the person chose is the device's (`workboardLanesStore`).
 */
import { AlertTriangle, BarChart3, Coins, SquareKanban, Sparkles, UserCheck } from '@/lib/icons';
import type { LucideIcon } from '@/lib/icons';

import { Disclosure } from '@/components/ui/disclosure';
import { Skeleton } from '@/components/ui/skeleton';
import { UsageLine, meterFigures } from '@/components/ui/usage-line';
import { useAuth } from '@/hooks/useAuth';
import { useWorkboardSummary } from '@/hooks/useWorkboardSummary';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatNumber } from '@/lib/format';
import { cn } from '@/lib/utils';
import { columnIcon, laneIcon } from '@/lib/workboard/icons';
import { useWorkboardLanesStore } from '@/stores/workboardLanesStore';
import {
  CONDITIONAL_STATUSES,
  TICKET_STATUSES,
  type BoardFilters,
  type LaneRow,
} from '@/types/workboard';

const FOCUS = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';
const PILL =
  'inline-flex max-w-full items-center gap-1.5 rounded-full border border-border bg-background px-2.5 py-1 text-xs transition-colors hover:bg-accent/40';

export interface BoardGlanceProps {
  lng: Language;
  /** Open on arrival: where the screen has room, never inside another interface. */
  defaultOpen: boolean;
  /**
   * Whether the board under it has been read. Before that the figures wait:
   * the stamp they are read under is not the board's yet, and a read taken on
   * it would be taken again a moment later.
   */
  ready: boolean;
  /** Changes whenever the figures may have moved; the block then re-reads them. */
  stamp: string;
  /** Narrow the board to one figure. An empty narrowing clears every filter. */
  onNarrow: (narrowing: BoardFilters) => void;
}

/** One figure of the board, and the narrowed board it opens. */
function FigureTile({
  icon: Icon,
  label,
  value,
  alarming = false,
  onPress,
}: {
  icon: LucideIcon;
  label: string;
  value: number;
  /** Lateness wears red once there is some — the number says it too. */
  alarming?: boolean;
  onPress: () => void;
}) {
  const alarm = alarming && value > 0;
  return (
    <button
      type="button"
      onClick={onPress}
      className={cn(
        'flex w-full items-center gap-3 rounded-xl border border-border bg-background p-3 text-left transition-colors hover:bg-accent/40',
        FOCUS
      )}
    >
      <span
        className={cn(
          'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
          alarm ? 'bg-destructive/10' : 'bg-primary/10'
        )}
      >
        <Icon
          className={cn('h-4 w-4', alarm ? 'text-destructive' : 'text-primary')}
          aria-hidden="true"
        />
      </span>
      <span className="min-w-0">
        <span className="block text-2xl font-semibold leading-none tabular-nums">
          {formatNumber(value)}
        </span>
        <span className="mt-1 block truncate text-xs text-muted-foreground">{label}</span>
      </span>
    </button>
  );
}

/** What the account owns against the cap the instance enforces. */
function Capacity({
  owned,
  max,
  label,
  text,
}: {
  owned: number;
  max: number;
  label: string;
  text: string;
}) {
  const pct = max > 0 ? Math.min(100, Math.round((owned / max) * 100)) : 0;
  return (
    <div>
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">{text}</span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuenow={owned}
        aria-valuemin={0}
        aria-valuemax={max}
        className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted"
      >
        <div
          className={cn('h-full rounded-full', pct >= 90 ? 'bg-destructive' : 'bg-primary')}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/** A labelled row of pills, each one a narrowing of the board. */
function PillList({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-px-11 font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <ul className="mt-1.5 flex flex-wrap gap-2" aria-label={label}>
        {children}
      </ul>
    </div>
  );
}

/** Every column of a lane: an aggregate over the whole board, never a page. */
function laneTotal(lane: LaneRow): number {
  return Object.values(lane.counts_by_status).reduce((sum, count) => sum + count, 0);
}

/** The figures themselves. Mounted only while the block is open. */
function Figures({ lng, ready, stamp, onNarrow }: Omit<BoardGlanceProps, 'defaultOpen'>) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const { summary, error } = useWorkboardSummary(ready, stamp);

  if (!summary) {
    // Unknown and refused are two answers; neither shows a figure nobody read.
    return error ? (
      <p role="alert" className="text-sm text-destructive">
        {t('workboard.summary.unavailable')}
      </p>
    ) : (
      <Skeleton className="h-24 w-full" />
    );
  }

  // A conditional column is drawn only while it holds a ticket, as on the board.
  const columns = TICKET_STATUSES.filter(
    status => !CONDITIONAL_STATUSES.has(status) || (summary.counts_by_status[status] ?? 0) > 0
  );
  const showCost = Boolean(user?.tokens_display_enabled) && summary.runs_total > 0;
  // Absent from an API that predates categories: that reads as « none ».
  const lanes = summary.lanes ?? [];

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {summary.needs_me === 0
          ? t('workboard.summary.nothing_waiting')
          : t('workboard.summary.needs_you', { count: summary.needs_me })}
      </p>

      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <FigureTile
          icon={SquareKanban}
          label={t('workboard.summary.tile_total')}
          value={summary.total}
          onPress={() => onNarrow({})}
        />
        <FigureTile
          icon={AlertTriangle}
          label={t('workboard.summary.tile_overdue')}
          value={summary.overdue}
          alarming
          onPress={() => onNarrow({ overdue: true })}
        />
        <FigureTile
          icon={Sparkles}
          label={t('workboard.summary.tile_lia')}
          value={summary.held_by_lia}
          onPress={() => onNarrow({ assignee: 'lia' })}
        />
        <FigureTile
          icon={UserCheck}
          label={t('workboard.summary.tile_mine')}
          value={summary.held_by_me}
          onPress={() => onNarrow({ assignee: 'me' })}
        />
      </div>

      <PillList label={t('workboard.summary.by_column')}>
        {columns.map(status => (
          <li key={status}>
            <button
              type="button"
              onClick={() => onNarrow({ status: [status] })}
              className={cn(PILL, FOCUS)}
            >
              {columnIcon(status, 'h-3.5 w-3.5 shrink-0 text-primary')}
              <span>{t(`workboard.columns.${status}`)}</span>
              <span className="font-semibold tabular-nums">
                {formatNumber(summary.counts_by_status[status] ?? 0)}
              </span>
            </button>
          </li>
        ))}
      </PillList>

      {lanes.length > 0 && (
        <PillList label={t('workboard.summary.by_category')}>
          {lanes.map(lane => (
            <li key={lane.category_id ?? 'unfiled'}>
              <button
                type="button"
                onClick={() =>
                  onNarrow(
                    lane.category_id === null
                      ? { uncategorized: true }
                      : { category: [lane.category_id] }
                  )
                }
                className={cn(PILL, FOCUS)}
              >
                {laneIcon(lane.category_id !== null, 'h-3.5 w-3.5 shrink-0 text-primary')}
                <span className="min-w-0 break-words text-left">
                  {lane.name ?? t('workboard.lanes.unfiled')}
                </span>
                <span className="font-semibold tabular-nums">{formatNumber(laneTotal(lane))}</span>
              </button>
            </li>
          ))}
        </PillList>
      )}

      <Capacity
        owned={summary.owned}
        max={summary.max_tickets}
        label={t('workboard.summary.capacity_label')}
        text={t('workboard.summary.capacity', { owned: summary.owned, max: summary.max_tickets })}
      />

      {showCost && (
        <div className="rounded-xl border border-border bg-background [--lia-field-background:var(--color-card)] p-3">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            {/* A label, not a heading: the page's outline stops at the lanes. */}
            <p className="flex items-center gap-2 text-sm font-semibold">
              <Coins className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
              {t('workboard.summary.cost')}
            </p>
            <span className="text-xs text-muted-foreground">
              {t('workboard.summary.runs', { count: summary.runs_total })}
            </span>
          </div>
          {/* Six decimals, as a ticket's own cost: a board of tickets costs
              cents, and two decimals turned a real spend into 0,00 €. */}
          <UsageLine figures={meterFigures(summary)} cost={summary.cost_eur} decimals={6} />
        </div>
      )}
    </div>
  );
}

export function BoardGlance({ lng, defaultOpen, ready, stamp, onNarrow }: BoardGlanceProps) {
  const { t } = useTranslation(lng);
  const chosen = useWorkboardLanesStore(state => state.summaryOpen);
  const choose = useWorkboardLanesStore(state => state.setSummaryOpen);
  const open = chosen ?? defaultOpen;

  return (
    <Disclosure
      icon={BarChart3}
      title={t('workboard.summary.title')}
      // Said while it is shut: these are the WHOLE board's figures, not the
      // filtered board's under it.
      description={t('workboard.summary.hint')}
      open={open}
      // A CHOICE is a change. A browser also fires `toggle` on a block merely
      // created open, and when the screen's size opens it: recording that
      // would pin on this device a state nobody chose.
      onOpenChange={next => {
        if (next !== open) choose(next);
      }}
    >
      <Figures lng={lng} ready={ready} stamp={stamp} onNarrow={onNarrow} />
    </Disclosure>
  );
}
