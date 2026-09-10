'use client';
/**
 * The workboard's settings section — the board at a glance, and its door (ADR-276).
 *
 * D15: the board has NO header destination (the header is at its measured
 * maximum of seven), so it is reached from here and from every ticket
 * notification. That makes this section load-bearing — and a sentence with a
 * button under it was not carrying the load (owner, 2026-09-10: « une page vide
 * avec un bouton »). It now reads `GET /workboard/summary` — every figure an
 * aggregate over the WHOLE board (ADR-185), every figure a link into the board
 * narrowed to it — shows what the account owns against the cap the instance
 * enforces (ADR-184: an enforced bound is a published one), and what its
 * tickets have cost in the chat meter's vocabulary, under the header's own
 * « show figures » switch.
 *
 * Self-gated on the instance flag `features.workboard_enabled` (the
 * `MeetingsSettings` precedent): off, it renders nothing and the settings shell
 * says the section is absent.
 */
import Link from 'next/link';
import {
  AlertTriangle,
  Coins,
  ExternalLink,
  LayoutGrid,
  Sparkles,
  UserCheck,
  type LucideIcon,
} from 'lucide-react';

import { SettingsSection } from '@/components/settings/SettingsSection';
import { Button } from '@/components/ui/button';
import { UsageLine, meterFigures } from '@/components/workboard/UsageLine';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useAuth } from '@/hooks/useAuth';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useWorkboardSummary } from '@/hooks/useWorkboardSummary';
import { useTranslation } from '@/i18n/client';
import { formatNumber } from '@/lib/format';
import { cn } from '@/lib/utils';
import { boardHref } from '@/lib/workboard/filters-url';
import { columnIcon } from '@/lib/workboard/icons';
import type { BaseSettingsProps } from '@/types/settings';
import { CONDITIONAL_STATUSES, TICKET_STATUSES, type BoardSummary } from '@/types/workboard';

const FOCUS = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

/** One figure of the board, and the narrowed board it opens. */
function FigureTile({
  href,
  icon: Icon,
  label,
  value,
  alarming = false,
}: {
  href: string;
  icon: LucideIcon;
  label: string;
  value: number;
  /** Lateness wears red once there is some — the number says it too. */
  alarming?: boolean;
}) {
  const alarm = alarming && value > 0;
  return (
    <Link
      href={href}
      className={cn(
        'flex items-center gap-3 rounded-xl border border-border/60 bg-muted/20 p-3 transition-colors hover:bg-accent/40',
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
    </Link>
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

/** The figures, once the summary is known. */
function Glance({ lng, summary }: { lng: BaseSettingsProps['lng']; summary: BoardSummary }) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  // A conditional column is drawn only while it holds a ticket, as on the board.
  const columns = TICKET_STATUSES.filter(
    status => !CONDITIONAL_STATUSES.has(status) || (summary.counts_by_status[status] ?? 0) > 0
  );
  const showCost = Boolean(user?.tokens_display_enabled) && summary.runs_total > 0;

  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-xs font-bold uppercase tracking-wider text-primary">
          {t('settings.workboard.glance')}
        </h4>
        <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <FigureTile
            href={boardHref(lng)}
            icon={LayoutGrid}
            label={t('settings.workboard.tile_total')}
            value={summary.total}
          />
          <FigureTile
            href={boardHref(lng, { overdue: true })}
            icon={AlertTriangle}
            label={t('settings.workboard.tile_overdue')}
            value={summary.overdue}
            alarming
          />
          <FigureTile
            href={boardHref(lng, { assignee: 'lia' })}
            icon={Sparkles}
            label={t('settings.workboard.tile_lia')}
            value={summary.held_by_lia}
          />
          <FigureTile
            href={boardHref(lng)}
            icon={UserCheck}
            label={t('settings.workboard.tile_needs_me')}
            value={summary.needs_me}
          />
        </div>
      </div>

      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('settings.workboard.by_column')}
        </p>
        <ul className="mt-1.5 flex flex-wrap gap-2" aria-label={t('settings.workboard.by_column')}>
          {columns.map(status => (
            <li key={status}>
              <Link
                href={boardHref(lng, { status: [status] })}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-full border border-border/60 bg-background px-2.5 py-1 text-xs transition-colors hover:bg-accent/40',
                  FOCUS
                )}
              >
                {columnIcon(status, 'h-3.5 w-3.5 shrink-0 text-primary')}
                <span>{t(`workboard.columns.${status}`)}</span>
                <span className="font-semibold tabular-nums">
                  {formatNumber(summary.counts_by_status[status] ?? 0)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>

      <Capacity
        owned={summary.owned}
        max={summary.max_tickets}
        label={t('settings.workboard.capacity_label')}
        text={t('settings.workboard.capacity', { owned: summary.owned, max: summary.max_tickets })}
      />

      {showCost && (
        <div className="rounded-xl border border-border/60 bg-muted/20 p-3">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h4 className="flex items-center gap-2 text-sm font-semibold">
              <Coins className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
              {t('settings.workboard.cost')}
            </h4>
            <span className="text-xs text-muted-foreground">
              {t('settings.workboard.runs', { count: summary.runs_total })}
            </span>
          </div>
          {/* Two decimals, as the conversation pill shows its total. */}
          <UsageLine figures={meterFigures(summary)} cost={summary.cost_eur} decimals={2} />
        </div>
      )}
    </div>
  );
}

export function WorkboardSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { config } = useAppConfig();
  const router = useLocalizedRouter();
  const enabled = Boolean(config?.features?.workboard_enabled);
  const { summary } = useWorkboardSummary(enabled);

  if (!enabled) return null;

  const needsMe = summary?.needs_me;

  return (
    <SettingsSection
      value="workboard"
      icon={LayoutGrid}
      title={t('settings.workboard.title')}
      description={t('settings.workboard.description')}
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            {/* « unknown » and a real 0 are told apart by the ABSENCE of the
                payload, exactly as the hub does. */}
            {needsMe === undefined
              ? t('settings.workboard.description')
              : needsMe === 0
                ? t('settings.workboard.nothing_waiting')
                : t('settings.workboard.needs_you', { count: needsMe })}
          </p>
          <Button variant="default" onClick={() => router.push('/dashboard/workboard')}>
            <ExternalLink className="mr-2 h-4 w-4" aria-hidden="true" />
            {t('settings.workboard.open_board')}
          </Button>
        </div>
        {summary && <Glance lng={lng} summary={summary} />}
      </div>
    </SettingsSection>
  );
}
