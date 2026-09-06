'use client';

/**
 * The reminders a reader owns: what is coming, and their hand on it.
 *
 * This screen is the genericity test of the recurrence work. It mounts
 * `RecurrenceEditor` with `REMINDER_LIMITS` and nothing else — no prop added,
 * no branch inside the editor, no copy of a field. If it had needed one, the
 * editor would have been the routines' editor wearing a different name.
 *
 * Three rules it obeys, each paid for elsewhere in this codebase:
 *
 * - **A refresh is not a first load.** `initialLoading` is monotone, so a poll
 *   never swaps the populated list for a spinner and destroys the reader's
 *   place in it (`PeerConnectionsSettings`, 2026-07-31).
 * - **Row actions go through `RowActions`** — visible ghost icons from `sm`
 *   up, a named menu below, delete red at rest. Never `opacity-0 group-hover`.
 * - **The dialog constrains its height in `dvh` and scrolls inside.** The
 *   recurrence editor is tall; without it the save button is unreachable on a
 *   phone (found on the routines' dialog, 2026-09-06).
 *
 * **The list is never a history.** A reminder is deleted the moment it has no
 * future left, so an empty list means "nothing is coming", never "nothing was
 * ever sent" — the empty state says exactly that.
 */

import { useCallback, useMemo, useState } from 'react';
import { Bell, BellPlus, Pencil, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { RecurrenceEditor, type RecurrenceLimits } from '@/components/recurrence/RecurrenceEditor';
import { FormSection } from '@/components/ui/form-section';
import { SettingsSection } from '@/components/settings/SettingsSection';
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
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { RowActions } from '@/components/ui/row-actions';
import { useReminders, type Reminder, type ReminderCreate } from '@/hooks/useReminders';
import { emptyRecurrence, recurrenceIsComplete } from '@/lib/recurrence';
import { type Language } from '@/i18n/settings';
import type { RecurrenceSpec } from '@/types/recurrence';

interface RemindersSettingsProps {
  lng: Language;
}

/**
 * What a REMINDER may ask of the recurrence engine.
 *
 * Injected, never owned by the editor: a routine runs an agent pipeline and is
 * capped at 12 firings a day, a reminder sends a notification and is capped at
 * 48. Mirrors `RECURRENCE_REMINDER_LIMITS` in `src/core/constants.py`, which
 * is what the API actually enforces.
 */
const REMINDER_LIMITS: RecurrenceLimits = {
  maxTimesPerDay: 48,
  minStepMinutes: 5,
  maxSeriesCount: 1000,
};

/** The browser's own zone, shown while a new reminder is being described. */
function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

/** Today, `YYYY-MM-DD`, as the anchor a new recurrence starts from. */
function todayLocal(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

interface DraftState {
  content: string;
  recurrence: RecurrenceSpec;
}

export function RemindersSettings({ lng }: RemindersSettingsProps) {
  const { t } = useTranslation(lng);
  const {
    reminders,
    total,
    loading,
    initialLoading,
    createReminder,
    updateReminder,
    deleteReminder,
    creating,
    updating,
  } = useReminders();

  const [editing, setEditing] = useState<Reminder | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftState>({
    content: '',
    recurrence: emptyRecurrence(todayLocal()),
  });

  const timezone = editing?.user_timezone ?? browserTimezone();
  const busy = creating || updating;

  const openCreate = useCallback(() => {
    setEditing(null);
    setDraft({ content: '', recurrence: emptyRecurrence(todayLocal()) });
    setDialogOpen(true);
  }, []);

  const openEdit = useCallback((reminder: Reminder) => {
    setEditing(reminder);
    setDraft({ content: reminder.content, recurrence: reminder.recurrence });
    setDialogOpen(true);
  }, []);

  const canSave = useMemo(
    () => draft.content.trim().length > 0 && recurrenceIsComplete(draft.recurrence),
    [draft]
  );

  const handleSave = useCallback(async () => {
    // The guard, not a `disabled` attribute: disabling a focused control blurs
    // it and drops it from the tab order (`apps/web/CLAUDE.md`).
    if (!canSave || busy) return;
    try {
      if (editing) {
        await updateReminder(editing.id, {
          content: draft.content.trim(),
          recurrence: draft.recurrence,
        });
        toast.success(t('reminders.updated'));
      } else {
        const payload: ReminderCreate = {
          content: draft.content.trim(),
          // No conversation behind a reminder created here, so the "original
          // message" IS what the reader typed. The column is NOT NULL and the
          // notification prompt reads it.
          original_message: draft.content.trim(),
          // No `trigger_at`: the API derives the armed instant from the
          // recurrence. Sending both is refused — one authority for when a
          // reminder fires, never two.
          recurrence: draft.recurrence,
        };
        await createReminder(payload);
        toast.success(t('reminders.created'));
      }
      setDialogOpen(false);
    } catch {
      toast.error(t('reminders.save_failed'));
    }
  }, [canSave, busy, editing, draft, updateReminder, createReminder, t]);

  const handleDelete = useCallback(async () => {
    if (!deletingId) return;
    try {
      await deleteReminder(deletingId);
      toast.success(t('reminders.deleted'));
    } catch {
      toast.error(t('reminders.delete_failed'));
    } finally {
      setDeletingId(null);
    }
  }, [deletingId, deleteReminder, t]);

  const pendingDeletion = reminders.find(r => r.id === deletingId) ?? null;

  return (
    <SettingsSection
      value="reminders"
      title={t('reminders.settings.title')}
      description={t('reminders.settings.description')}
      icon={Bell}
    >
      <ReminderList
        reminders={reminders}
        total={total}
        loading={loading}
        initialLoading={initialLoading}
        onCreate={openCreate}
        onEdit={openEdit}
        onDelete={setDeletingId}
      />

      <ReminderFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editing={editing}
        draft={draft}
        onDraftChange={setDraft}
        timezone={timezone}
        busy={busy}
        canSave={canSave}
        onSave={() => void handleSave()}
      />

      <ReminderDeleteDialog
        reminder={pendingDeletion}
        onCancel={() => setDeletingId(null)}
        onConfirm={() => void handleDelete()}
      />
    </SettingsSection>
  );
}

/**
 * The three states of the list: loading, empty, populated.
 *
 * Its own component so the screen above stays a description of WHAT happens
 * rather than a description of what is drawn — and so neither function carries
 * every branch of both (the complexity ratchet is per function, and it is
 * right to be).
 */
function ReminderList({
  reminders,
  total,
  loading,
  initialLoading,
  onCreate,
  onEdit,
  onDelete,
}: {
  reminders: Reminder[];
  total: number;
  loading: boolean;
  initialLoading: boolean;
  onCreate: () => void;
  onEdit: (reminder: Reminder) => void;
  onDelete: (id: string) => void;
}) {
  const { t } = useTranslation();

  return (
    <div aria-busy={loading}>
      <div className="flex items-center justify-between gap-2 mb-4">
        <p className="text-sm text-muted-foreground">
          {/* The EXACT total, and — when the page could not hold it — a line
              saying so. A cap is stated, never applied in silence (ADR-185). */}
          {total > 0 ? t('reminders.settings.count', { count: total }) : ''}
          {reminders.length < total && (
            <span className="ml-1">
              {t('reminders.settings.capped', { shown: reminders.length })}
            </span>
          )}
        </p>
        <Button size="sm" onClick={onCreate}>
          <BellPlus className="h-4 w-4 mr-1" />
          {t('reminders.create')}
        </Button>
      </div>

      {initialLoading && (
        <div className="flex justify-center py-8">
          <LoadingSpinner className="h-6 w-6" />
        </div>
      )}

      {!initialLoading && reminders.length === 0 && (
        <EmptyState
          icon={Bell}
          title={t('reminders.empty')}
          description={t('reminders.empty_hint')}
        />
      )}

      {!initialLoading && reminders.length > 0 && (
        <ul className="space-y-2">
          {reminders.map(reminder => (
            <ReminderRow
              key={reminder.id}
              reminder={reminder}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

/** One reminder: what it says, when it repeats, and the two things to do. */
function ReminderRow({
  reminder,
  onEdit,
  onDelete,
}: {
  reminder: Reminder;
  onEdit: (reminder: Reminder) => void;
  onDelete: (id: string) => void;
}) {
  const { t } = useTranslation();

  return (
    <li className="rounded-lg border bg-card p-4 flex items-start justify-between gap-2">
      <div className="min-w-0 flex-1 space-y-1">
        <p className="font-medium break-words">{reminder.content}</p>
        {/* The sentence the SERVER composed: the browser never re-reads a
            schedule, or the two would disagree at a clock change. */}
        <p className="text-sm text-muted-foreground">{reminder.schedule_display}</p>
        {reminder.runs_per_day > 1 && (
          <p className="text-xs text-muted-foreground">
            {t('recurrence.summary_per_day', { count: reminder.runs_per_day })}
          </p>
        )}
      </div>
      <RowActions
        menuLabel={t('common.actions_for', { name: reminder.content })}
        actions={[
          {
            key: 'edit',
            label: t('common.edit'),
            icon: Pencil,
            onSelect: () => onEdit(reminder),
          },
          {
            key: 'delete',
            label: t('common.delete'),
            icon: Trash2,
            tone: 'destructive',
            onSelect: () => onDelete(reminder.id),
          },
        ]}
      />
    </li>
  );
}

/** The form: what to remind, and the generic recurrence editor. */
function ReminderFormDialog({
  open,
  onOpenChange,
  editing,
  draft,
  onDraftChange,
  timezone,
  busy,
  canSave,
  onSave,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: Reminder | null;
  draft: DraftState;
  onDraftChange: (updater: (previous: DraftState) => DraftState) => void;
  timezone: string;
  busy: boolean;
  canSave: boolean;
  onSave: () => void;
}) {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* The recurrence editor makes this form tall: two questions, a weekday
          row, an end rule and a summary. `DialogContent` does not scroll on
          its own, and `dvh` accounts for the mobile browser bars that move. */}
      <DialogContent className="sm:max-w-[480px] max-h-[85dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {editing ? t('reminders.edit_title') : t('reminders.create_title')}
          </DialogTitle>
        </DialogHeader>

        {/* Two named groups rather than one column of inputs: the form asks
            two different questions, and `space-y-6` gives the boundary between
            them more air than the gap inside each. */}
        <div className="space-y-6 py-2">
          <FormSection icon={Bell} title={t('reminders.section_what')}>
            <div className="space-y-3">
              <Label htmlFor="reminder-content">{t('reminders.field_content')}</Label>
              <Input
                id="reminder-content"
                value={draft.content}
                onChange={e => onDraftChange(d => ({ ...d, content: e.target.value }))}
                placeholder={t('reminders.field_content_placeholder')}
                maxLength={2000}
              />
            </div>
          </FormSection>

          {/* Mounted UNCHANGED — the whole point of the generic editor. */}
          <RecurrenceEditor
            value={draft.recurrence}
            onChange={recurrence => onDraftChange(d => ({ ...d, recurrence }))}
            limits={REMINDER_LIMITS}
            timezone={timezone}
            idPrefix="rem"
            sentence={editing?.schedule_display}
            occurrences={editing?.next_occurrences}
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          {/* `aria-disabled`, never `disabled`: the latter blurs a focused
              control and drops it from the tab order. The guard in `onSave`
              is what actually prevents the save. */}
          <Button onClick={onSave} isLoading={busy} aria-disabled={!canSave || busy}>
            {t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** The confirmation, which must say whether a SERIES is about to go. */
function ReminderDeleteDialog({
  reminder,
  onCancel,
  onConfirm,
}: {
  reminder: Reminder | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { t } = useTranslation();
  const repeats = reminder !== null && reminder.recurrence.freq !== 'once';

  return (
    <AlertDialog open={reminder !== null} onOpenChange={open => !open && onCancel()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('reminders.delete_title')}</AlertDialogTitle>
          {/* A reminder that repeats is a SERIES: deleting it removes every
              future occurrence, not just the next one. */}
          <AlertDialogDescription>
            {repeats
              ? t('reminders.delete_series_confirm', {
                  content: reminder.content,
                  schedule: reminder.schedule_display,
                })
              : t('reminders.delete_confirm', { content: reminder?.content ?? '' })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>{t('common.delete')}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export default RemindersSettings;
