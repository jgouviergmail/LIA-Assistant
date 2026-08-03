'use client';

import { useState, useMemo, useCallback, useRef } from 'react';
import { CalendarClock, Copy, Plus, Trash2, Pencil, Play, Clock, MoreVertical } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useTranslation } from '@/i18n/client';
import { type Language, getIntlLocale } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import {
  useScheduledActions,
  type ConditionConfig,
  type ConditionType,
  type ScheduledAction,
  type ScheduledActionCreate,
  type ScheduledActionUpdate,
  type TriggerKind,
} from '@/hooks/useScheduledActions';
import { renderOccurrences } from '@/lib/occurrences';
import { duplicateTitle } from '@/lib/scheduled-actions';
import { toast } from 'sonner';

interface ScheduledActionsSettingsProps {
  lng: Language;
}

/** ISO weekday numbers 1=Mon..7=Sun */
const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7] as const;

/** Minute options (every 5 minutes) */
const MINUTE_OPTIONS = Array.from({ length: 12 }, (_, i) => i * 5);

/** Hour options (0-23) */
const HOUR_OPTIONS = Array.from({ length: 24 }, (_, i) => i);

interface FormState {
  title: string;
  action_prompt: string;
  days_of_week: number[];
  trigger_hour: number;
  trigger_minute: number;
  // N-07 (flattened for the form; assembled into ConditionConfig on save).
  trigger_kind: TriggerKind;
  condition_type: ConditionType;
  condition_query: string;
  requires_approval: boolean;
}

const EMPTY_FORM: FormState = {
  title: '',
  action_prompt: '',
  days_of_week: [],
  trigger_hour: 8,
  trigger_minute: 0,
  trigger_kind: 'time',
  condition_type: 'task_overdue',
  condition_query: '',
  requires_approval: false,
};

/** N-07 condition types offered by the studio (mirror of the backend). */
const CONDITION_TYPES: readonly ConditionType[] = [
  'task_overdue',
  'weather_change',
  'mail_match',
  'document_added',
  'calendar_event',
];

/** Condition types whose studio form shows the text-filter field. */
const QUERY_CONDITION_TYPES: readonly ConditionType[] = ['mail_match', 'calendar_event'];

/** Assemble the API ConditionConfig from the flattened form (null for time). */
function buildConditionConfig(form: FormState): ConditionConfig | null {
  if (form.trigger_kind !== 'condition') return null;
  const config: ConditionConfig = { type: form.condition_type };
  const query = form.condition_query.trim();
  if (query && QUERY_CONDITION_TYPES.includes(form.condition_type)) {
    config.query = query;
  }
  return config;
}

/**
 * Read an action into the flattened form state (pure).
 *
 * Shared by "edit" and "duplicate" so the two can never drift: a field added
 * to the form has one place to be copied, and a duplicate that silently
 * dropped the condition would produce a routine the backend refuses.
 */
function formStateFromAction(action: ScheduledAction): FormState {
  return {
    title: action.title,
    action_prompt: action.action_prompt,
    days_of_week: [...action.days_of_week],
    trigger_hour: action.trigger_hour,
    trigger_minute: action.trigger_minute,
    trigger_kind: action.trigger_kind ?? 'time',
    condition_type: action.condition_config?.type ?? 'task_overdue',
    condition_query: action.condition_config?.query ?? '',
    requires_approval: action.requires_approval ?? false,
  };
}

/**
 * Diff the form against the edited action into a minimal update payload
 * (pure — keeps handleSave under the CC cap). Kind + condition travel
 * together (the backend enforces coherence); a changed condition alone also
 * ships.
 */
function buildUpdatePayload(
  form: FormState,
  editing: ScheduledAction,
  conditionConfig: ConditionConfig | null
): ScheduledActionUpdate {
  const update: ScheduledActionUpdate = {};
  if (form.title !== editing.title) update.title = form.title;
  if (form.action_prompt !== editing.action_prompt) update.action_prompt = form.action_prompt;
  if (JSON.stringify(form.days_of_week) !== JSON.stringify(editing.days_of_week))
    update.days_of_week = form.days_of_week;
  if (form.trigger_hour !== editing.trigger_hour) update.trigger_hour = form.trigger_hour;
  if (form.trigger_minute !== editing.trigger_minute) update.trigger_minute = form.trigger_minute;
  if (form.trigger_kind !== (editing.trigger_kind ?? 'time')) {
    update.trigger_kind = form.trigger_kind;
    update.condition_config = conditionConfig;
  } else if (JSON.stringify(conditionConfig) !== JSON.stringify(editing.condition_config ?? null)) {
    update.condition_config = conditionConfig;
  }
  if (form.requires_approval !== (editing.requires_approval ?? false))
    update.requires_approval = form.requires_approval;
  return update;
}

function getStatusBadgeVariant(
  action: ScheduledAction
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (!action.is_enabled) return 'secondary';
  if (action.status === 'error') return 'destructive';
  if (action.status === 'executing') return 'outline';
  return 'default';
}

export function ScheduledActionsSettings({ lng }: ScheduledActionsSettingsProps) {
  const { t } = useTranslation(lng);
  const intlLocale = getIntlLocale(lng);

  const {
    actions,
    total,
    loading,
    createAction,
    updateAction,
    deleteAction,
    toggleAction,
    executeAction,
    creating,
    updating,
    executing,
  } = useScheduledActions();

  // Dialog states
  const regionRef = useRef<HTMLDivElement>(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [editingAction, setEditingAction] = useState<ScheduledAction | null>(null);
  const [deletingActionId, setDeletingActionId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [mobileActionItem, setMobileActionItem] = useState<ScheduledAction | null>(null);

  // Day labels for the current language
  const dayLabels = useMemo(() => {
    const labels: Record<number, string> = {};
    for (const d of WEEKDAYS) {
      labels[d] = t(`scheduled_actions.days.d${d}`);
    }
    return labels;
  }, [t]);

  // Format schedule for display using i18n day labels (replaces backend schedule_display)
  const formatSchedule = useCallback(
    (action: ScheduledAction) => {
      const sorted = [...action.days_of_week].sort((a, b) => a - b);
      const daysStr = sorted.map(d => dayLabels[d] ?? `${d}`).join(', ');
      const time = `${String(action.trigger_hour).padStart(2, '0')}:${String(action.trigger_minute).padStart(2, '0')}`;
      return `${daysStr} - ${time}`;
    },
    [dayLabels]
  );

  // Format datetime for display
  const formatDateTime = (isoString: string | null) => {
    if (!isoString) return t('scheduled_actions.never_executed');
    try {
      return new Intl.DateTimeFormat(intlLocale, {
        dateStyle: 'short',
        timeStyle: 'short',
      }).format(new Date(isoString));
    } catch {
      return isoString;
    }
  };

  // Toggle day in form
  const toggleDay = (day: number) => {
    setForm(prev => ({
      ...prev,
      days_of_week: prev.days_of_week.includes(day)
        ? prev.days_of_week.filter(d => d !== day)
        : [...prev.days_of_week, day].sort(),
    }));
  };

  // Open create dialog
  const handleOpenCreate = () => {
    setForm(EMPTY_FORM);
    setShowCreateDialog(true);
  };

  // Open edit dialog
  const handleOpenEdit = (action: ScheduledAction) => {
    setForm(formStateFromAction(action));
    setEditingAction(action);
  };

  /**
   * Open the CREATION dialog prefilled from an existing routine.
   *
   * Nothing is written yet: the reader lands on a form they can adjust before
   * saving — the point being to decline a routine (week/weekend,
   * personal/professional), which almost always means changing a day or an
   * hour first. Execution state (counters, last error, status) is deliberately
   * not carried: the creation payload has no place for it, and a copy has run
   * zero times.
   */
  const handleOpenDuplicate = (action: ScheduledAction) => {
    const source = formStateFromAction(action);
    setForm({
      ...source,
      title: duplicateTitle(source.title, t('scheduled_actions.duplicate_suffix')),
    });
    setShowCreateDialog(true);
  };

  // N-07: a mail_match condition without its filter cannot be saved.
  const conditionInvalid =
    form.trigger_kind === 'condition' &&
    form.condition_type === 'mail_match' &&
    !form.condition_query.trim();

  // Save (create or update)
  const handleSave = async () => {
    if (
      !form.title.trim() ||
      !form.action_prompt.trim() ||
      form.days_of_week.length === 0 ||
      conditionInvalid
    ) {
      return;
    }
    const conditionConfig = buildConditionConfig(form);

    try {
      if (editingAction) {
        const update = buildUpdatePayload(form, editingAction, conditionConfig);
        if (Object.keys(update).length > 0) {
          await updateAction(editingAction.id, update);
          toast.success(t('scheduled_actions.edit_success'));
        }
        setEditingAction(null);
      } else {
        const data: ScheduledActionCreate = {
          title: form.title.trim(),
          action_prompt: form.action_prompt.trim(),
          days_of_week: form.days_of_week,
          trigger_hour: form.trigger_hour,
          trigger_minute: form.trigger_minute,
          trigger_kind: form.trigger_kind,
          condition_config: conditionConfig,
          requires_approval: form.requires_approval,
        };
        await createAction(data);
        toast.success(t('scheduled_actions.create_success'));
        setShowCreateDialog(false);
      }
    } catch {
      toast.error(
        editingAction ? t('scheduled_actions.error_update') : t('scheduled_actions.error_create')
      );
    }
  };

  // Delete
  const handleDelete = async () => {
    if (!deletingActionId) return;
    try {
      await deleteAction(deletingActionId);
      toast.success(t('scheduled_actions.delete_success'));
      // Take focus back into the panel: Radix restores it to the trigger the
      // dialog was opened from, and that trigger is inside the row this
      // deletion just removed — leaving the keyboard user on <body>.
      regionRef.current?.focus();
    } catch {
      toast.error(t('scheduled_actions.error_delete'));
    }
    setDeletingActionId(null);
  };

  // Toggle
  const handleToggle = async (action: ScheduledAction) => {
    try {
      const result = await toggleAction(action.id);
      if (result) {
        toast.success(
          result.is_enabled
            ? t('scheduled_actions.toggle_enabled')
            : t('scheduled_actions.toggle_disabled')
        );
      }
    } catch {
      toast.error(t('scheduled_actions.error_update'));
    }
  };

  // Execute now
  const handleExecute = async (action: ScheduledAction) => {
    try {
      await executeAction(action.id);
      toast.success(t('scheduled_actions.test_now_launched'));
    } catch {
      toast.error(t('scheduled_actions.error_execute'));
    }
  };

  // Status label
  const getStatusLabel = (action: ScheduledAction) => {
    if (!action.is_enabled) return t('scheduled_actions.status.paused');
    if (action.status === 'error') return t('scheduled_actions.status.error');
    if (action.status === 'executing') return t('scheduled_actions.status.executing');
    return t('scheduled_actions.status.active');
  };

  // Form dialog content (shared between create and edit)
  const formDialog = (isOpen: boolean, onClose: () => void, titleKey: string) => (
    <Dialog open={isOpen} onOpenChange={open => !open && onClose()}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t(titleKey)}</DialogTitle>
          <DialogDescription>{t('scheduled_actions.settings.description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Title */}
          <div className="space-y-2">
            <Label htmlFor="sa-title">{t('scheduled_actions.field_title')}</Label>
            <Input
              id="sa-title"
              value={form.title}
              onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              maxLength={200}
              placeholder={t('scheduled_actions.field_title_placeholder')}
            />
          </div>

          {/* Prompt */}
          <div className="space-y-2">
            <Label htmlFor="sa-prompt">{t('scheduled_actions.field_prompt')}</Label>
            <Textarea
              id="sa-prompt"
              value={form.action_prompt}
              onChange={e => setForm(f => ({ ...f, action_prompt: e.target.value }))}
              maxLength={2000}
              rows={3}
              placeholder={t('scheduled_actions.prompt_placeholder')}
            />
          </div>

          {/* Days of week */}
          <div className="space-y-2">
            <Label>{t('scheduled_actions.field_days')}</Label>
            <div className="flex flex-wrap gap-2">
              {WEEKDAYS.map(day => (
                <Button
                  key={day}
                  type="button"
                  size="sm"
                  variant={form.days_of_week.includes(day) ? 'default' : 'outline'}
                  onClick={() => toggleDay(day)}
                  className="min-w-[3rem]"
                >
                  {dayLabels[day]}
                </Button>
              ))}
            </div>
          </div>

          {/* Time */}
          <div className="space-y-2">
            <Label>{t('scheduled_actions.field_time')}</Label>
            <div className="flex items-center gap-2">
              <Select
                value={String(form.trigger_hour)}
                onValueChange={v => setForm(f => ({ ...f, trigger_hour: parseInt(v) }))}
              >
                <SelectTrigger className="w-20">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {HOUR_OPTIONS.map(h => (
                    <SelectItem key={h} value={String(h)}>
                      {String(h).padStart(2, '0')}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-lg font-bold">:</span>
              <Select
                value={String(form.trigger_minute)}
                onValueChange={v => setForm(f => ({ ...f, trigger_minute: parseInt(v) }))}
              >
                <SelectTrigger className="w-20">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MINUTE_OPTIONS.map(m => (
                    <SelectItem key={m} value={String(m)}>
                      {String(m).padStart(2, '0')}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <p className="text-xs text-muted-foreground">
              {form.trigger_kind === 'condition'
                ? t('scheduled_actions.studio.time_hint_condition')
                : t('scheduled_actions.studio.time_hint_time')}
            </p>
          </div>

          {/* N-07 studio: trigger kind */}
          <div className="space-y-2">
            <Label htmlFor="sa-trigger-kind">{t('scheduled_actions.studio.trigger_kind')}</Label>
            <Select
              value={form.trigger_kind}
              onValueChange={v => setForm(f => ({ ...f, trigger_kind: v as TriggerKind }))}
            >
              <SelectTrigger id="sa-trigger-kind">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="time">{t('scheduled_actions.studio.kind_time')}</SelectItem>
                <SelectItem value="condition">
                  {t('scheduled_actions.studio.kind_condition')}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* N-07 studio: condition config (condition kind only) */}
          {form.trigger_kind === 'condition' && (
            <div className="space-y-2 rounded-lg border border-border/40 p-3">
              <Label htmlFor="sa-condition-type">
                {t('scheduled_actions.studio.condition_type')}
              </Label>
              <Select
                value={form.condition_type}
                onValueChange={v => setForm(f => ({ ...f, condition_type: v as ConditionType }))}
              >
                <SelectTrigger id="sa-condition-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CONDITION_TYPES.map(type => (
                    <SelectItem key={type} value={type}>
                      {t(`scheduled_actions.studio.condition.${type}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {QUERY_CONDITION_TYPES.includes(form.condition_type) && (
                <div className="space-y-1.5">
                  <Label htmlFor="sa-condition-query">
                    {t(`scheduled_actions.studio.query_label.${form.condition_type}`)}
                  </Label>
                  <Input
                    id="sa-condition-query"
                    value={form.condition_query}
                    maxLength={120}
                    onChange={e => setForm(f => ({ ...f, condition_query: e.target.value }))}
                    placeholder={t(`scheduled_actions.studio.query_ph.${form.condition_type}`)}
                  />
                  {conditionInvalid && (
                    <p className="text-xs text-destructive" role="alert">
                      {t('scheduled_actions.studio.query_required')}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* N-07 studio: propose-first mode */}
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <Label htmlFor="sa-approval">{t('scheduled_actions.studio.requires_approval')}</Label>
              <p className="text-xs text-muted-foreground">
                {t('scheduled_actions.studio.requires_approval_hint')}
              </p>
            </div>
            <Switch
              id="sa-approval"
              checked={form.requires_approval}
              onCheckedChange={v => setForm(f => ({ ...f, requires_approval: v }))}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={handleSave}
            disabled={
              !form.title.trim() ||
              !form.action_prompt.trim() ||
              form.days_of_week.length === 0 ||
              conditionInvalid ||
              creating ||
              updating
            }
          >
            {(creating || updating) && <LoadingSpinner className="mr-2 h-4 w-4" />}
            {t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return (
    <SettingsSection
      value="scheduled-actions"
      title={t('scheduled_actions.settings.title')}
      description={t('scheduled_actions.settings.description')}
      icon={CalendarClock}
    >
      {/* A stable focus anchor for a panel whose rows DISAPPEAR under the
          reader. Radix returns focus to the trigger the delete dialog opened
          from; that trigger lived inside the removed row, so focus falls to
          <body> and the keyboard user restarts at the top of the settings
          page. `-1` adds no tab stop — it only makes this container a legal
          destination for a deliberate `.focus()`, and it outlives every row,
          the empty state included. */}
      <div ref={regionRef} tabIndex={-1} data-routines-region className="focus:outline-none">
      {/* Header with count and add button */}
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-muted-foreground">
          {total > 0 ? `${total} ${t('scheduled_actions.settings.count', { count: total })}` : ''}
        </p>
        <Button size="sm" onClick={handleOpenCreate}>
          <Plus className="h-4 w-4 mr-1" />
          {t('scheduled_actions.create')}
        </Button>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-8">
          <LoadingSpinner className="h-6 w-6" />
        </div>
      )}

      {/* Empty state */}
      {!loading && actions.length === 0 && (
        <div className="text-center py-8 text-muted-foreground">
          <CalendarClock className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <p className="text-sm font-medium">{t('scheduled_actions.empty')}</p>
          <p className="text-xs mt-1">{t('scheduled_actions.empty_hint')}</p>
        </div>
      )}

      {/* Action cards */}
      {!loading && actions.length > 0 && (
        <div className="space-y-3">
          {actions.map(action => (
            // role="presentation": the tap-anywhere onClick is a pointer-only
            // convenience duplicating the dedicated mobile actions button
            // (audit F012/F045); the card carries no semantics (it contains
            // interactive children).
            <div
              key={action.id}
              role="presentation"
              className="rounded-lg border bg-card p-4 space-y-1.5 group cursor-pointer lg:cursor-default"
              onClick={() => {
                if (window.innerWidth < 1024) setMobileActionItem(action);
              }}
            >
              {/* Row 1: Title + Status + Actions (hover) + Toggle */}
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <span className="font-medium truncate">{action.title}</span>
                  <Badge variant={getStatusBadgeVariant(action)} className="shrink-0">
                    {getStatusLabel(action)}
                  </Badge>
                </div>
                {/* Desktop action buttons — hover reveal */}
                <div className="hidden lg:flex gap-1 shrink-0 opacity-0 group-hover:opacity-100">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={e => {
                      e.stopPropagation();
                      handleExecute(action);
                    }}
                    disabled={executing}
                    title={t('scheduled_actions.test_now')}
                  >
                    <Play className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={e => {
                      e.stopPropagation();
                      handleOpenEdit(action);
                    }}
                    title={t('common.edit')}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={e => {
                      e.stopPropagation();
                      handleOpenDuplicate(action);
                    }}
                    aria-label={t('scheduled_actions.duplicate')}
                    title={t('scheduled_actions.duplicate')}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={e => {
                      e.stopPropagation();
                      setDeletingActionId(action.id);
                    }}
                    title={t('common.delete')}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
                {/* Mobile actions button (audit F012/F045): the desktop
                    buttons above are hidden below lg and the tap-anywhere card
                    click is pointer-only — this is the keyboard/AT path to the
                    actions popup. */}
                <Button
                  variant="ghost"
                  size="icon"
                  className="lg:hidden shrink-0"
                  aria-label={t('common.actions')}
                  onClick={e => {
                    e.stopPropagation();
                    setMobileActionItem(action);
                  }}
                >
                  <MoreVertical className="h-4 w-4 text-muted-foreground" />
                </Button>
                {/* Named, and named with the ROUTINE: a Radix `Switch` is a
                    `<button role="switch">`, which jsx-a11y cannot see is
                    anonymous — axe reported it `critical`. On a list of
                    several, "switch, on" says nothing about what is about to
                    be turned off. */}
                <Switch
                  checked={action.is_enabled}
                  onCheckedChange={() => handleToggle(action)}
                  onClick={e => e.stopPropagation()}
                  aria-label={t('scheduled_actions.toggle_aria', { title: action.title })}
                />
              </div>

              {/* Prompt (truncated) */}
              <p className="text-sm text-muted-foreground line-clamp-1">{action.action_prompt}</p>

              {/* Schedule */}
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {formatSchedule(action)}
              </p>

              {/* Upcoming runs. A CONDITION routine gets a different heading:
                  its cron says when the condition is EVALUATED, and claiming
                  to know when it will become true would be an invention. */}
              <div className="text-xs text-muted-foreground">
                <span>
                  {t(
                    (action.trigger_kind ?? 'time') === 'condition'
                      ? 'scheduled_actions.next_evaluations'
                      : 'scheduled_actions.next_executions'
                  )}
                </span>
                <ul className="mt-0.5 space-y-0.5" role="list">
                  {renderOccurrences(
                    action.next_occurrences ?? [action.next_trigger_at],
                    action.user_timezone,
                    intlLocale
                  ).map(run => (
                    <li key={run.iso} className="tabular-nums">
                      <time dateTime={run.iso}>{run.label}</time>
                      {/* No `opacity-70`: axe measured 2.9:1 against the card
                          (4.5 required). The zone name is the one thing on
                          this line that says WHICH clock the hour is read
                          against — dimming it below legibility defeats it. */}
                      {run.zone && <span className="ml-1">{run.zone}</span>}
                      {run.clockChange && (
                        <span className="ml-1 text-warning">
                          {t('scheduled_actions.clock_change')}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Last execution */}
              <p className="text-xs text-muted-foreground">
                {t('scheduled_actions.last_execution')}: {formatDateTime(action.last_executed_at)}
              </p>

              {/* Execution count */}
              {action.execution_count > 0 && (
                <p className="text-xs text-muted-foreground">
                  {t('scheduled_actions.execution_count')}: {action.execution_count}
                </p>
              )}

              {/* Error message */}
              {action.last_error && (
                <p className="text-xs text-destructive line-clamp-1">{action.last_error}</p>
              )}
            </div>
          ))}
        </div>
      )}

      </div>

      {/* Create dialog */}
      {formDialog(showCreateDialog, () => setShowCreateDialog(false), 'scheduled_actions.create')}

      {/* Edit dialog */}
      {formDialog(
        editingAction !== null,
        () => setEditingAction(null),
        'scheduled_actions.edit_title'
      )}

      {/* Delete confirmation */}
      <AlertDialog
        open={deletingActionId !== null}
        onOpenChange={open => !open && setDeletingActionId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('scheduled_actions.confirm_delete_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('scheduled_actions.confirm_delete_description')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {/* Mobile actions dialog */}
      <Dialog
        open={mobileActionItem !== null}
        onOpenChange={open => !open && setMobileActionItem(null)}
      >
        <DialogContent className="lg:hidden max-w-[90vw] rounded-lg">
          <DialogHeader>
            <DialogTitle className="text-base">{mobileActionItem?.title}</DialogTitle>
            <DialogDescription className="sr-only">
              {t('scheduled_actions.settings.description')}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2 py-2">
            <Button
              variant="outline"
              className="w-full justify-start gap-3"
              onClick={() => {
                if (mobileActionItem) {
                  handleExecute(mobileActionItem);
                  setMobileActionItem(null);
                }
              }}
              disabled={executing}
            >
              <Play className="h-4 w-4" />
              {t('scheduled_actions.test_now')}
            </Button>
            <Button
              variant="outline"
              className="w-full justify-start gap-3"
              onClick={() => {
                if (mobileActionItem) {
                  handleOpenEdit(mobileActionItem);
                  setMobileActionItem(null);
                }
              }}
            >
              <Pencil className="h-4 w-4" />
              {t('common.edit')}
            </Button>
            <Button
              variant="outline"
              className="w-full justify-start gap-3"
              onClick={() => {
                if (mobileActionItem) {
                  handleOpenDuplicate(mobileActionItem);
                  setMobileActionItem(null);
                }
              }}
            >
              <Copy className="h-4 w-4" />
              {t('scheduled_actions.duplicate')}
            </Button>
            <Button
              variant="outline"
              className="w-full justify-start gap-3 text-destructive hover:text-destructive"
              onClick={() => {
                if (mobileActionItem) {
                  setDeletingActionId(mobileActionItem.id);
                  setMobileActionItem(null);
                }
              }}
            >
              <Trash2 className="h-4 w-4" />
              {t('common.delete')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </SettingsSection>
  );
}
