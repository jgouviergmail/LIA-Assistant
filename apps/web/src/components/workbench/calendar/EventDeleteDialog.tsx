'use client';

/**
 * EventDeleteDialog — deleting one event, or its whole series (ADR-369).
 *
 * An occurrence of a series asks which: this one, by default, or the whole series. A calendar
 * that cannot change one occurrence alone only offers the whole series, and says so.
 * Where the provider lets the page choose, « tell the guests » is offered and
 * checked by default (spec §14); elsewhere nothing is offered — the provider
 * tells them its own way. The act runs once per opening.
 */
import { useId, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { CalendarEventDetail } from '@/lib/workbench/types';
import { CancelButton, ToolActions, ToolDialogHeader } from '../ToolForm';

export interface EventDeleteDialogProps {
  lng: Language;
  event: CalendarEventDetail;
  notifyOffered: boolean;
  /** One occurrence can go alone. */
  occurrenceEdit: boolean;
  onDelete: (notify: boolean | undefined, series: boolean) => Promise<void>;
  onClose: () => void;
}

function deleteSentence(event: CalendarEventDetail, series: boolean): string {
  if (series) return 'workbench.calendar.delete_series';
  return event.recurring
    ? 'workbench.calendar.delete_occurrence'
    : 'workbench.calendar.delete_description';
}

export function EventDeleteDialog({
  lng,
  event,
  notifyOffered,
  occurrenceEdit,
  onDelete,
  onClose,
}: EventDeleteDialogProps) {
  const { t } = useTranslation(lng);
  const [notify, setNotify] = useState(true);
  const [series, setSeries] = useState(event.recurring && !occurrenceEdit);
  const [deleting, setDeleting] = useState(false);
  const busy = useRef(false);
  const notifyId = useId();
  const scopeName = useId();
  const remove = async () => {
    if (busy.current) return;
    busy.current = true;
    setDeleting(true);
    try {
      await onDelete(notifyOffered ? notify : undefined, series);
    } finally {
      busy.current = false;
      setDeleting(false);
    }
  };
  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent>
        <ToolDialogHeader>
          <DialogTitle>
            {t('workbench.calendar.delete_title', {
              name: event.summary || t('workbench.calendar.no_title'),
            })}
          </DialogTitle>
          <DialogDescription>{t(deleteSentence(event, series))}</DialogDescription>
        </ToolDialogHeader>
        {event.recurring && occurrenceEdit && (
          <fieldset className="space-y-2">
            <legend className="sr-only">{t('workbench.calendar.delete_scope')}</legend>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name={scopeName}
                aria-label={t('workbench.calendar.delete_this')}
                checked={!series}
                onChange={() => setSeries(false)}
              />
              {t('workbench.calendar.delete_this')}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name={scopeName}
                aria-label={t('workbench.calendar.delete_whole')}
                checked={series}
                onChange={() => setSeries(true)}
              />
              {t('workbench.calendar.delete_whole')}
            </label>
          </fieldset>
        )}
        {notifyOffered && event.attendees.length > 0 && (
          <div className="flex items-center gap-2">
            <Checkbox
              id={notifyId}
              checked={notify}
              onChange={change => setNotify(change.target.checked)}
            />
            <Label htmlFor={notifyId}>{t('workbench.calendar.editor.notify')}</Label>
          </div>
        )}
        <ToolActions>
          <CancelButton lng={lng} onClick={onClose} />
          <Button variant="destructive" isLoading={deleting} onClick={() => void remove()}>
            {t('workbench.calendar.delete')}
          </Button>
        </ToolActions>
      </DialogContent>
    </Dialog>
  );
}
