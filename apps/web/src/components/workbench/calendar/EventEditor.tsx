'use client';

/**
 * EventEditor — a new event, or a change to one (ADR-369, spec §14).
 *
 * Native day and time fields; what leaves is the wall time and the account's
 * zone (`lib/workbench/calendar/editor`). A new event carries ONE key for the
 * life of this form — the provider's own idempotency: a second press creates
 * nothing. An outcome nobody knows keeps what was written and says to look in
 * the calendar. A video call and « tell the guests » are offered only where the
 * provider has them (the descriptor). Each opening mounts a new editor.
 */
import { useId, useRef, useState, type FormEvent } from 'react';

import { RecipientCombobox } from '@/components/email-share/RecipientCombobox';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import {
  changeBody,
  endsAfterStart,
  fieldsOf,
  newEventBody,
  type EventChangeBody,
  type EventFields,
  type NewEventBody,
} from '@/lib/workbench/calendar/editor';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { WORKBENCH_RECIPIENTS_PATH } from '@/lib/workbench/recipients';
import type { CalendarEventDetail, WorkbenchCalendar } from '@/lib/workbench/types';

/** What the editor was opened on. */
export type EditorTarget =
  | { kind: 'new'; fields: EventFields }
  | { kind: 'edit'; event: CalendarEventDetail };

export interface EventEditorProps {
  lng: Language;
  target: EditorTarget;
  zone: string;
  calendars: readonly WorkbenchCalendar[];
  conferenceOffered: boolean;
  notifyOffered: boolean;
  bounds: Readonly<Record<string, number>>;
  onCreate: (body: NewEventBody) => Promise<unknown>;
  onUpdate: (body: EventChangeBody) => Promise<unknown>;
  onClose: () => void;
}

const UNKNOWN = 'workbench.errors.outcome_unknown';

export function EventEditor(props: EventEditorProps) {
  const { lng, target, zone, onClose } = props;
  const { t } = useTranslation(lng);
  const [initial] = useState(() =>
    target.kind === 'new' ? target.fields : fieldsOf(target.event, zone)
  );
  const [fields, setFields] = useState(initial);
  const [conference, setConference] = useState(false);
  const [notify, setNotify] = useState(true);
  const [key] = useState(() => crypto.randomUUID());
  const [status, setStatus] = useState<'editing' | 'saving' | 'unknown'>('editing');
  const [problem, setProblem] = useState<string | null>(null);
  const busy = useRef(false);
  const reversed = !endsAfterStart(fields, zone);
  const set = (change: Partial<EventFields>) => setFields(current => ({ ...current, ...change }));

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (busy.current || reversed || !fields.summary.trim()) return;
    const run = submission(props, initial, fields, { conference, notify, key });
    if (run === null) {
      onClose();
      return;
    }
    busy.current = true;
    setStatus('saving');
    setProblem(null);
    try {
      await run();
      onClose();
    } catch (error: unknown) {
      const refusal = workbenchRefusal(error);
      setStatus(refusal?.key === UNKNOWN ? 'unknown' : 'editing');
      setProblem(refusal ? t(refusal.key, refusal.values) : t('workbench.calendar.failed'));
    } finally {
      busy.current = false;
    }
  };

  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent className="max-sm:inset-0 max-sm:left-0 max-sm:top-0 max-sm:h-dvh max-sm:max-h-none max-sm:w-screen max-sm:max-w-none max-sm:translate-x-0 max-sm:translate-y-0 max-sm:overflow-y-auto max-sm:rounded-none max-sm:border-0 sm:max-w-xl">
        <form onSubmit={save} className="space-y-4">
          <DialogHeader>
            <DialogTitle>
              {t(
                target.kind === 'new'
                  ? 'workbench.calendar.editor.title_new'
                  : 'workbench.calendar.editor.title_edit'
              )}
            </DialogTitle>
            <DialogDescription>{t('workbench.calendar.editor.zone', { zone })}</DialogDescription>
          </DialogHeader>
          <EditorFields {...props} fields={fields} set={set} reversed={reversed} />
          {props.conferenceOffered && target.kind === 'new' && (
            <CheckLine
              label={t('workbench.calendar.editor.conference')}
              checked={conference}
              onChange={setConference}
            />
          )}
          {props.notifyOffered && target.kind === 'edit' && (
            <CheckLine
              label={t('workbench.calendar.editor.notify')}
              checked={notify}
              onChange={setNotify}
            />
          )}
          {problem && (
            <p role="alert" className="text-sm text-destructive">
              {status === 'unknown' ? t('workbench.calendar.editor.unknown') : problem}
            </p>
          )}
          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              isLoading={status === 'saving'}
              aria-disabled={reversed || !fields.summary.trim() || undefined}
            >
              {t(
                target.kind === 'new'
                  ? 'workbench.calendar.editor.create'
                  : 'workbench.calendar.editor.save'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** The act the form submits; null when a change names nothing. */
function submission(
  props: EventEditorProps,
  initial: EventFields,
  fields: EventFields,
  choices: { conference: boolean; notify: boolean; key: string }
): (() => Promise<unknown>) | null {
  const { target, zone, conferenceOffered, notifyOffered } = props;
  if (target.kind === 'new') {
    const body = newEventBody(fields, zone, {
      conference: conferenceOffered && choices.conference,
      idempotencyKey: choices.key,
    });
    return () => props.onCreate(body);
  }
  const change = changeBody(
    target.event,
    initial,
    fields,
    zone,
    notifyOffered ? choices.notify : undefined
  );
  return change === null ? null : () => props.onUpdate(change);
}

interface EditorFieldsProps extends EventEditorProps {
  fields: EventFields;
  set: (change: Partial<EventFields>) => void;
  reversed: boolean;
}

function EditorFields({
  lng,
  target,
  calendars,
  bounds,
  fields,
  set,
  reversed,
}: EditorFieldsProps) {
  const { t } = useTranslation(lng);
  const allDayId = useId();
  const calendarId = useId();
  const writable = calendars.filter(calendar => calendar.writable);
  return (
    <div className="space-y-3">
      <Input
        label={t('workbench.calendar.editor.summary')}
        value={fields.summary}
        maxLength={bounds.summary_max_chars}
        required
        onChange={event => set({ summary: event.target.value })}
      />
      {/* The guests, right under the title (owner, 2026-10-31): a message's recipients'
          field — contacts suggested while a guest is typed, « Send by e-mail »'s matcher. */}
      <RecipientCombobox
        label={t('workbench.calendar.editor.attendees')}
        placeholder={t('workbench.calendar.editor.attendees_hint')}
        value={fields.attendees}
        onChange={attendees => set({ attendees })}
        minChars={bounds.recipient_query_min_chars ?? 2}
        suggestionsPath={WORKBENCH_RECIPIENTS_PATH}
      />
      {target.kind === 'new' && writable.length > 1 && (
        <div className="space-y-1.5">
          <Label htmlFor={calendarId}>{t('workbench.calendar.editor.calendar')}</Label>
          <select
            id={calendarId}
            value={fields.calendarId}
            onChange={event => set({ calendarId: event.target.value })}
            className="h-10 w-full rounded-md border bg-background px-3 text-sm"
          >
            {writable.map(calendar => (
              <option key={calendar.id} value={calendar.id}>
                {calendar.name}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="flex items-center gap-3">
        <Switch
          id={allDayId}
          aria-labelledby={`${allDayId}-label`}
          checked={fields.allDay}
          onCheckedChange={allDay => set({ allDay })}
        />
        <Label id={`${allDayId}-label`} htmlFor={allDayId}>
          {t('workbench.calendar.editor.all_day')}
        </Label>
      </div>
      <BoundFields lng={lng} fields={fields} set={set} reversed={reversed} />
      <Input
        label={t('workbench.calendar.editor.location')}
        value={fields.location}
        maxLength={bounds.location_max_chars}
        onChange={event => set({ location: event.target.value })}
      />
      <Textarea
        label={t('workbench.calendar.editor.description')}
        value={fields.description}
        rows={4}
        maxLength={bounds.description_max_chars}
        onChange={event => set({ description: event.target.value })}
      />
    </div>
  );
}

function BoundFields({
  lng,
  fields,
  set,
  reversed,
}: {
  lng: Language;
  fields: EventFields;
  set: (change: Partial<EventFields>) => void;
  reversed: boolean;
}) {
  const { t } = useTranslation(lng);
  const prefix = 'workbench.calendar.editor';
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Input
        type="date"
        label={t(fields.allDay ? `${prefix}.first_day` : `${prefix}.start`)}
        value={fields.startDate}
        required
        onChange={event => set({ startDate: event.target.value })}
      />
      {!fields.allDay && (
        <Input
          type="time"
          label={t(`${prefix}.start_time`)}
          value={fields.startTime}
          required
          onChange={event => set({ startTime: event.target.value })}
        />
      )}
      <Input
        type="date"
        label={t(fields.allDay ? `${prefix}.last_day` : `${prefix}.end`)}
        value={fields.endDate}
        min={fields.startDate}
        required
        onChange={event => set({ endDate: event.target.value })}
        error={reversed && fields.allDay ? t(`${prefix}.ends_before`) : undefined}
      />
      {!fields.allDay && (
        <Input
          type="time"
          label={t(`${prefix}.end_time`)}
          value={fields.endTime}
          required
          onChange={event => set({ endTime: event.target.value })}
          error={reversed ? t(`${prefix}.ends_before`) : undefined}
        />
      )}
    </div>
  );
}

function CheckLine({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  const id = useId();
  return (
    <div className="flex items-center gap-2">
      <Checkbox id={id} checked={checked} onChange={event => onChange(event.target.checked)} />
      <Label htmlFor={id}>{label}</Label>
    </div>
  );
}
