'use client';

import { useState, useMemo, useCallback } from 'react';
import {
  CalendarClock,
  Plus,
  Trash2,
  Pencil,
  Play,
  Clock,
} from 'lucide-react';
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
  type ScheduledAction,
  type ScheduledActionCreate,
  type ScheduledActionUpdate,
} from '@/hooks/useScheduledActions';
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
}

const EMPTY_FORM: FormState = {
  title: '',
  action_prompt: '',
  days_of_week: [],
  trigger_hour: 8,
  trigger_minute: 0,
};

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
  const formatSchedule = useCallback((action: ScheduledAction) => {
    const sorted = [...action.days_of_week].sort((a, b) => a - b);
    const daysStr = sorted.map((d) => dayLabels[d] ?? `${d}`).join(', ');
    const time = `${String(action.trigger_hour).padStart(2, '0')}:${String(action.trigger_minute).padStart(2, '0')}`;
    return `${daysStr} - ${time}`;
  }, [dayLabels]);

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
    setForm((prev) => ({
      ...prev,
      days_of_week: prev.days_of_week.includes(day)
        ? prev.days_of_week.filter((d) => d !== day)
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
    setForm({
      title: action.title,
      action_prompt: action.action_prompt,
      days_of_week: [...action.days_of_week],
      trigger_hour: action.trigger_hour,
      trigger_minute: action.trigger_minute,
    });
    setEditingAction(action);
  };

  // Save (create or update)
  const handleSave = async () => {
    if (!form.title.trim() || !form.action_prompt.trim() || form.days_of_week.length === 0) {
      return;
    }

    try {
      if (editingAction) {
        // Build update payload (only changed fields)
        const update: ScheduledActionUpdate = {};
        if (form.title !== editingAction.title) update.title = form.title;
        if (form.action_prompt !== editingAction.action_prompt)
          update.action_prompt = form.action_prompt;
        if (JSON.stringify(form.days_of_week) !== JSON.stringify(editingAction.days_of_week))
          update.days_of_week = form.days_of_week;
        if (form.trigger_hour !== editingAction.trigger_hour)
          update.trigger_hour = form.trigger_hour;
        if (form.trigger_minute !== editingAction.trigger_minute)
          update.trigger_minute = form.trigger_minute;

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
        };
        await createAction(data);
        toast.success(t('scheduled_actions.create_success'));
        setShowCreateDialog(false);
      }
    } catch {
      toast.error(
        editingAction
          ? t('scheduled_actions.error_update')
          : t('scheduled_actions.error_create')
      );
    }
  };

  // Delete
  const handleDelete = async () => {
    if (!deletingActionId) return;
    try {
      await deleteAction(deletingActionId);
      toast.success(t('scheduled_actions.delete_success'));
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
  const formDialog = (
    isOpen: boolean,
    onClose: () => void,
    titleKey: string,
  ) => (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
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
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
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
              onChange={(e) => setForm((f) => ({ ...f, action_prompt: e.target.value }))}
              maxLength={2000}
              rows={3}
              placeholder={t('scheduled_actions.prompt_placeholder')}
            />
          </div>

          {/* Days of week */}
          <div className="space-y-2">
            <Label>{t('scheduled_actions.field_days')}</Label>
            <div className="flex flex-wrap gap-2">
              {WEEKDAYS.map((day) => (
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
                onValueChange={(v) => setForm((f) => ({ ...f, trigger_hour: parseInt(v) }))}
              >
                <SelectTrigger className="w-20">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {HOUR_OPTIONS.map((h) => (
                    <SelectItem key={h} value={String(h)}>
                      {String(h).padStart(2, '0')}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-lg font-bold">:</span>
              <Select
                value={String(form.trigger_minute)}
                onValueChange={(v) => setForm((f) => ({ ...f, trigger_minute: parseInt(v) }))}
              >
                <SelectTrigger className="w-20">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MINUTE_OPTIONS.map((m) => (
                    <SelectItem key={m} value={String(m)}>
                      {String(m).padStart(2, '0')}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
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
      {/* Header with count and add button */}
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-muted-foreground">
          {total > 0
            ? `${total} ${t('scheduled_actions.settings.count', { count: total })}`
            : ''}
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
          {actions.map((action) => (
            <div
              key={action.id}
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
                    onClick={(e) => { e.stopPropagation(); handleExecute(action); }}
                    disabled={executing}
                    title={t('scheduled_actions.test_now')}
                  >
                    <Play className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={(e) => { e.stopPropagation(); handleOpenEdit(action); }}
                    title={t('common.edit')}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={(e) => { e.stopPropagation(); setDeletingActionId(action.id); }}
                    title={t('common.delete')}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
                <Switch
                  checked={action.is_enabled}
                  onCheckedChange={() => handleToggle(action)}
                  onClick={(e) => e.stopPropagation()}
                />
              </div>

              {/* Prompt (truncated) */}
              <p className="text-sm text-muted-foreground line-clamp-1">
                {action.action_prompt}
              </p>

              {/* Schedule */}
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {formatSchedule(action)}
              </p>

              {/* Next execution */}
              <p className="text-xs text-muted-foreground">
                {t('scheduled_actions.next_execution')}: {formatDateTime(action.next_trigger_at)}
              </p>

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

      {/* Create dialog */}
      {formDialog(
        showCreateDialog,
        () => setShowCreateDialog(false),
        'scheduled_actions.create',
      )}

      {/* Edit dialog */}
      {formDialog(
        editingAction !== null,
        () => setEditingAction(null),
        'scheduled_actions.edit_title',
      )}

      {/* Delete confirmation */}
      <AlertDialog
        open={deletingActionId !== null}
        onOpenChange={(open) => !open && setDeletingActionId(null)}
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
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {/* Mobile actions dialog */}
      <Dialog
        open={mobileActionItem !== null}
        onOpenChange={(open) => !open && setMobileActionItem(null)}
      >
        <DialogContent className="lg:hidden max-w-[90vw] rounded-lg">
          <DialogHeader>
            <DialogTitle className="text-base">
              {mobileActionItem?.title}
            </DialogTitle>
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
