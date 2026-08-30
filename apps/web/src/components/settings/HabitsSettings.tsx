'use client';

/**
 * HabitsSettings — the learned-habits control surface (ADR-214).
 *
 * The control ships BEFORE any proactive consumption: everything the
 * detectors learned is visible here (rhythm profile per day class + discrete
 * habit rows), honest about its state (learning / sparse / diffuse / none —
 * never an invented habit), and reversible end to end (pause, block =
 * never-relearn tombstone, delete one, forget everything, master toggle).
 *
 * Row actions follow ADR-208 (`RowActions`), statuses take their tone from
 * `lib/status-tone.ts` (paused/blocked are INACTIVE → grey, told apart by
 * label), bulk destruction is solid red behind an explicit confirm
 * (ADR-207). Renders nothing when the instance flag is off.
 */

import {
  CircleSlash,
  Flame,
  Pause,
  Play,
  RefreshCw,
  Repeat,
  Trash2,
} from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { HabitExplanation } from '@/components/settings/HabitExplanation';
import { Label } from '@/components/ui/label';
import { RowActions } from '@/components/ui/row-actions';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { Switch } from '@/components/ui/switch';
import { lifecycleTone } from '@/lib/status-tone';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useConfirm } from '@/components/ui/use-confirm';
import {
  formatWindow,
  useHabits,
  type Habit,
  type HabitCandidate,
  type HabitsOverview,
  type HabitsProfileClass,
  type HabitStatus,
} from '@/hooks/useHabits';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { BaseSettingsProps } from '@/types/settings';

/** Localized weekday name from a 0=Monday..6=Sunday index. */
function weekdayName(locale: string, dow: number): string {
  // 2026-08-03 is a Monday; offsetting from it yields any weekday safely.
  const reference = new Date(Date.UTC(2026, 7, 3 + dow));
  return new Intl.DateTimeFormat(locale, { weekday: 'long', timeZone: 'UTC' }).format(reference);
}

/** "07:30"-style label from a fractional hour. */
function formatHour(hour: number): string {
  const totalMinutes = (Math.round((hour * 60) / 30) * 30) % (24 * 60);
  const h = String(Math.floor(totalMinutes / 60)).padStart(2, '0');
  const m = String(totalMinutes % 60).padStart(2, '0');
  return `${h}:${m}`;
}

export function HabitsSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { config } = useAppConfig();
  const flagOn = !!config?.features?.habits_enabled;
  const {
    overview,
    unavailable,
    loadError,
    refetch,
    setStatus,
    remove,
    removeAll,
    setEnabled,
    recompute,
  } = useHabits(flagOn);
  const { confirm, confirmDialog } = useConfirm();
  // Pending state of the bulk destruction: `<Button isLoading>` is the
  // design-system contract for an in-flight action (never a removed one).
  const [forgetting, setForgetting] = useState(false);
  const [recomputing, setRecomputing] = useState(false);

  if (!flagOn || unavailable) return null;

  const enabled = overview?.habits_enabled ?? true;

  const handleToggle = async (value: boolean) => {
    const ok = await setEnabled(value);
    if (!ok) toast.error(t('common.error'));
  };

  const handleStatus = async (habit: Habit, status: HabitStatus) => {
    const ok = await setStatus(habit.id, status);
    if (!ok) toast.error(t('common.error'));
  };

  const handleDelete = async (habit: Habit) => {
    const ok = await remove(habit.id);
    if (!ok) toast.error(t('common.error'));
  };

  const handleRecompute = async () => {
    setRecomputing(true);
    const ok = await recompute();
    setRecomputing(false);
    if (ok) toast.success(t('settings.habits.recompute_done'));
    else toast.error(t('common.error'));
  };

  const handleForgetAll = async () => {
    const confirmed = await confirm({
      title: t('settings.habits.forget_all_title'),
      description: t('settings.habits.forget_all_description'),
      confirmLabel: t('settings.habits.forget_all_confirm'),
    });
    if (!confirmed) return;
    setForgetting(true);
    const ok = await removeAll();
    setForgetting(false);
    if (ok) toast.success(t('settings.habits.forget_all_done'));
    else toast.error(t('common.error'));
  };

  const content = (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">{t('settings.habits.description')}</p>

      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <Label htmlFor="habits-enabled" className="text-sm font-medium">
            {t('settings.habits.enabled_label')}
          </Label>
          <p className="text-xs leading-relaxed text-muted-foreground">
            {t('settings.habits.enabled_hint')}
          </p>
        </div>
        <Switch id="habits-enabled" checked={enabled} onCheckedChange={v => void handleToggle(v)} />
      </div>

      {loadError ? (
        <div className="flex items-center gap-3">
          <p className="text-sm text-muted-foreground">{t('common.error')}</p>
          <button
            type="button"
            onClick={() => refetch()}
            className="text-sm text-primary hover:underline"
          >
            {t('common.retry')}
          </button>
        </div>
      ) : (
        enabled &&
        overview && (
          <HabitsOverviewBody
            lng={lng}
            overview={overview}
            onStatus={(habit, status) => void handleStatus(habit, status)}
            onDelete={habit => void handleDelete(habit)}
            forgetting={forgetting}
            recomputing={recomputing}
            onRecompute={() => void handleRecompute()}
            onForgetAll={() => void handleForgetAll()}
          />
        )
      )}
      {confirmDialog}
    </div>
  );

  return (
    <SettingsSection
      value="habits"
      title={t('settings.habits.title')}
      description={t('settings.habits.description')}
      icon={Repeat}
    >
      {content}
    </SettingsSection>
  );
}

function HabitsOverviewBody({
  lng,
  overview,
  forgetting,
  recomputing,
  onStatus,
  onDelete,
  onRecompute,
  onForgetAll,
}: {
  lng: Language;
  overview: HabitsOverview;
  forgetting: boolean;
  recomputing: boolean;
  onStatus: (habit: Habit, status: HabitStatus) => void;
  onDelete: (habit: Habit) => void;
  onRecompute: () => void;
  onForgetAll: () => void;
}) {
  const { t, i18n } = useTranslation(lng);
  return (
    <>
      {/* Streak block (Lot 1-A4): rendered only when a run is CURRENT —
          a broken streak is not a fact worth a permanent banner. */}
      {overview.streak.current > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-card px-4 py-3">
          <Flame className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
          <span className="text-sm font-semibold text-foreground">
            {t('settings.habits.streak_current', { count: overview.streak.current })}
          </span>
          {overview.streak.milestone_reached !== null && (
            <Badge variant="default">
              {t('settings.habits.streak_badge', { days: overview.streak.milestone_reached })}
            </Badge>
          )}
          <span className="text-xs text-muted-foreground">
            {overview.streak.next_milestone !== null
              ? t('settings.habits.streak_meta', {
                  longest: overview.streak.longest,
                  next: overview.streak.next_milestone,
                })
              : t('settings.habits.streak_meta_final', { longest: overview.streak.longest })}
          </span>
        </div>
      )}
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {t('settings.habits.rhythm_title')}
        </p>
        {overview.profile.computed_at ? (
          <p className="text-[11px] text-muted-foreground">
            {t('settings.habits.computed_at', {
              date: new Intl.DateTimeFormat(i18n.language, {
                day: '2-digit',
                month: 'short',
                hour: '2-digit',
                minute: '2-digit',
              }).format(new Date(overview.profile.computed_at)),
            })}
            {overview.profile.active_days_fraction > 0 && (
              <>
                {' · '}
                {t('settings.habits.active_days_caption', {
                  percent: Math.round(overview.profile.active_days_fraction * 100),
                })}
              </>
            )}
          </p>
        ) : (
          <p className="text-sm italic text-muted-foreground">
            {t('settings.habits.verdict.insufficient')}
          </p>
        )}
        <ClassRhythmLine
          lng={lng}
          labelKey="settings.habits.weekday_label"
          rhythm={overview.profile.weekday}
        />
        <ClassRhythmLine
          lng={lng}
          labelKey="settings.habits.weekend_label"
          rhythm={overview.profile.weekend}
        />
      </div>

      {overview.habits.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t('settings.habits.rows_title')}
          </p>
          <ul className="space-y-1" role="list">
            {overview.habits.map(habit => (
              <HabitRow
                key={habit.id}
                lng={lng}
                habit={habit}
                onStatus={status => onStatus(habit, status)}
                onDelete={() => onDelete(habit)}
              />
            ))}
          </ul>
        </div>
      )}

      {(overview.candidates.length > 0 || overview.candidates_more > 0) && (
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t('settings.habits.observing_title')}
          </p>
          <ul className="space-y-1" role="list">
            {overview.candidates.map(candidate => (
              <CandidateRow key={candidate.key} lng={lng} candidate={candidate} />
            ))}
          </ul>
          {overview.candidates_more > 0 && (
            <p className="text-[11px] text-muted-foreground">
              {t('settings.habits.candidates_more', { count: overview.candidates_more })}
            </p>
          )}
        </div>
      )}

      {/* Section actions on one row, same geometry (ADR-207): the themed CTA
          left of the solid-red bulk destruction — owner arbitration 2026-08-05.
          The extra top padding separates actions from data (owner screenshot
          feedback: the row sat too close to the last heatmap). */}
      <div className="flex flex-wrap items-center gap-2 pt-2">
        <Button
          type="button"
          variant="default"
          size="sm"
          isLoading={recomputing}
          onClick={onRecompute}
        >
          <RefreshCw className="mr-1.5 h-4 w-4" aria-hidden="true" />
          {t('settings.habits.recompute_label')}
        </Button>
        {(overview.habits.length > 0 || overview.profile.computed_at) && (
          <Button
            type="button"
            variant="destructive"
            size="sm"
            isLoading={forgetting}
            onClick={onForgetAll}
          >
            <Trash2 className="mr-1.5 h-4 w-4" aria-hidden="true" />
            {t('settings.habits.forget_all_label')}
          </Button>
        )}
      </div>
    </>
  );
}

/** One recurrence signature under observation: the domains, then either the
 * quantified progress toward the ENFORCED existence gate (published by the
 * backend — ADR-184) or, once volume is there, the consistency-forming state
 * (a lock is not a linear progress — pretending otherwise would be a lie). */
function CandidateRow({ lng, candidate }: { lng: Language; candidate: HabitCandidate }) {
  const { t } = useTranslation(lng);
  const volumeReached = candidate.observed_days >= candidate.required_days;
  return (
    <li className="flex flex-wrap items-center gap-2 rounded-lg border border-border/40 bg-card/60 px-3 py-2">
      <span className="min-w-0 flex-1 truncate text-sm font-medium">
        {candidate.key.split('+').join(' + ')}
      </span>
      {volumeReached ? (
        <span className="text-xs text-muted-foreground">
          {t('settings.habits.candidate_forming')}
        </span>
      ) : (
        <ObservationProgress
          observed={candidate.observed_days}
          required={candidate.required_days}
          caption={t('settings.habits.candidate_caption', {
            observed: candidate.observed_days,
            required: candidate.required_days,
          })}
          ariaLabel={t('settings.habits.candidate_aria')}
        />
      )}
    </li>
  );
}

function ClassRhythmLine({
  lng,
  labelKey,
  rhythm,
}: {
  lng: Language;
  labelKey: string;
  rhythm: HabitsProfileClass;
}) {
  const { t } = useTranslation(lng);
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{t(labelKey)}</span>
        {rhythm.verdict === 'windows' ? (
          rhythm.windows.map(window => (
            <Badge key={`${window.start_hour}-${window.end_hour}`} variant="default">
              {formatWindow(window)}
            </Badge>
          ))
        ) : rhythm.verdict === 'insufficient' ? (
          <UnlockProgress lng={lng} rhythm={rhythm} />
        ) : (
          <span className="text-sm text-muted-foreground">
            {t(`settings.habits.verdict.${rhythm.verdict}`)}
          </span>
        )}
      </div>
      {/* C-02 (ADR-184): the enforced bar is published, not just applied —
          shown on the `none` verdict, where it answers "why nothing?". The
          Wilson floor makes it class-dependent (weekends need more). */}
      {rhythm.verdict === 'none' && rhythm.effective_presence_min < 1 && (
        <p className="text-xs text-muted-foreground tabular-nums">
          {t('settings.habits.effective_bar', {
            pct: Math.round(rhythm.effective_presence_min * 100),
          })}
        </p>
      )}
      <RhythmHeatmap lng={lng} bins={rhythm.bin_presence} />
    </div>
  );
}

/** 24-slot activity heatmap — the distribution-level truth that stays
 * visible even when no window is claimable (a `none` verdict says "no fixed
 * hours", the heatmap shows WHERE presence spreads anyway). Intensity is
 * normalized to the strongest slot: a description, never a threshold claim.
 * The hour axis below is exact by construction: five equidistant labels over
 * 24 slots land on 0/6/12/18/24. Renders nothing when there is no presence. */
function RhythmHeatmap({ lng, bins }: { lng: Language; bins: number[] }) {
  const { t } = useTranslation(lng);
  const max = Math.max(0, ...bins);
  if (max <= 0) return null;
  return (
    <div className="max-w-xs space-y-0.5">
      <div
        role="img"
        aria-label={t('settings.habits.heatmap_aria')}
        className="flex h-2 items-stretch gap-px"
      >
        {bins.slice(0, 24).map((value, hour) => (
          <span
            key={hour}
            title={`${String(hour).padStart(2, '0')}:00`}
            className="min-w-0 flex-1 rounded-[1px] bg-primary"
            style={{ opacity: value > 0 ? 0.15 + 0.85 * (value / max) : 0.04 }}
          />
        ))}
      </div>
      <div
        aria-hidden="true"
        className="flex justify-between text-[9px] leading-none tracking-tight text-muted-foreground tabular-nums"
      >
        <span>00</span>
        <span>06</span>
        <span>12</span>
        <span>18</span>
        <span>24</span>
      </div>
    </div>
  );
}

/** Counter + thin bar for a published observation threshold (StarterChecklist
 * progressbar pattern) — the required value always comes from the backend
 * (ADR-184), never re-declared here. Shared by the rhythm unlock and the
 * recurrence candidates. */
function ObservationProgress({
  observed,
  required,
  caption,
  ariaLabel,
}: {
  observed: number;
  required: number;
  caption: string;
  ariaLabel: string;
}) {
  const safeRequired = Math.max(1, Math.round(required));
  const safeObserved = Math.min(Math.round(observed), safeRequired);
  const pct = Math.min(100, Math.round((safeObserved / safeRequired) * 100));
  return (
    <span
      role="progressbar"
      aria-valuenow={safeObserved}
      aria-valuemin={0}
      aria-valuemax={safeRequired}
      aria-label={ariaLabel}
      className="inline-flex items-center gap-2"
    >
      <span className="h-1.5 w-24 overflow-hidden rounded-full bg-muted" aria-hidden="true">
        <span className="block h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </span>
      <span className="text-xs text-muted-foreground tabular-nums">{caption}</span>
    </span>
  );
}

/** Quantified unlock state for the rhythm's 'still learning' verdict. */
function UnlockProgress({ lng, rhythm }: { lng: Language; rhythm: HabitsProfileClass }) {
  const { t } = useTranslation(lng);
  const observed = Math.min(Math.round(rhythm.n_eff), Math.round(rhythm.required_n_eff));
  const required = Math.max(1, Math.round(rhythm.required_n_eff));
  return (
    <ObservationProgress
      observed={observed}
      required={required}
      caption={t('settings.habits.progress_caption', { observed, required })}
      ariaLabel={t('settings.habits.progress_aria')}
    />
  );
}

/** Human label of one habit row, from its kind + key + payload. */
function habitLabel(
  t: ReturnType<typeof useTranslation>['t'],
  locale: string,
  habit: Habit
): string {
  if (habit.kind === 'active_window') {
    const [dayClass, part] = habit.key.split(':');
    const windows = Array.isArray(habit.payload.windows)
      ? (habit.payload.windows as { start_hour: number; end_hour: number }[])
          .map(w => formatWindow({ ...w, presence: 0 }))
          .join(', ')
      : '';
    return t('settings.habits.row.active_window', {
      dayClass: t(`settings.habits.class.${dayClass ?? 'weekday'}`),
      part: t(`settings.habits.part.${part ?? 'morning'}`),
      windows,
    });
  }
  const shape = typeof habit.payload.shape === 'string' ? habit.payload.shape : 'daily';
  const hour = typeof habit.payload.trigger_hour === 'number' ? habit.payload.trigger_hour : null;
  const days = Array.isArray(habit.payload.days_of_week)
    ? (habit.payload.days_of_week as number[])
    : [];
  const schedule =
    shape === 'weekly' && days.length > 0
      ? t('settings.habits.shape.weekly', { day: weekdayName(locale, days[0]) })
      : t(`settings.habits.shape.${shape}`);
  return t('settings.habits.row.recurring_request', {
    domains: habit.key.split('+').join(' + '),
    schedule,
    time: hour !== null ? `~${formatHour(hour)}` : '',
  }).trim();
}

function HabitRow({
  lng,
  habit,
  onStatus,
  onDelete,
}: {
  lng: Language;
  habit: Habit;
  onStatus: (status: HabitStatus) => void;
  onDelete: () => void;
}) {
  const { t, i18n } = useTranslation(lng);
  const label = habitLabel(t, i18n.language, habit);
  return (
    <li className="rounded-lg border border-border/40 bg-card/60 px-3 py-2">
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium" title={label}>
            {label}
          </p>
          <p className="text-[11px] text-muted-foreground">
            {t('settings.habits.signals_caption', {
              positive: habit.positive_signals,
              negative: habit.negative_signals,
            })}
          </p>
        </div>
        <Badge variant={lifecycleTone(habit.status)}>
          {t(`settings.habits.status.${habit.status}`)}
        </Badge>
        <RowActions
          menuLabel={t('common.actions_for', { name: label })}
          actions={[
            habit.status === 'paused' || habit.status === 'blocked'
              ? {
                  key: 'resume',
                  label: t('settings.habits.resume_label'),
                  icon: Play,
                  onSelect: () => onStatus('active'),
                }
              : {
                  key: 'pause',
                  label: t('settings.habits.pause_label'),
                  icon: Pause,
                  onSelect: () => onStatus('paused'),
                },
            ...(habit.status !== 'blocked'
              ? [
                  {
                    key: 'block',
                    label: t('settings.habits.block_label'),
                    icon: CircleSlash,
                    onSelect: () => onStatus('blocked'),
                  },
                ]
              : []),
            {
              key: 'delete',
              label: t('settings.habits.delete_label'),
              icon: Trash2,
              tone: 'destructive',
              onSelect: onDelete,
            },
          ]}
        />
      </div>
      <HabitExplanation lng={lng} habitId={habit.id} />
    </li>
  );
}
