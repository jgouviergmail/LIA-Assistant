'use client';

/**
 * EventDeleteDialog — deleting one event, an occurrence alone (ADR-369).
 *
 * Where the provider lets the page choose, « tell the guests » is offered and
 * checked by default (spec §14); elsewhere nothing is offered — the provider
 * tells them its own way. The act runs once per opening.
 */
import { useId, useRef, useState } from 'react';

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
import { Label } from '@/components/ui/label';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { CalendarEventDetail } from '@/lib/workbench/types';

export interface EventDeleteDialogProps {
  lng: Language;
  event: CalendarEventDetail;
  notifyOffered: boolean;
  onDelete: (notify: boolean | undefined) => Promise<void>;
  onClose: () => void;
}

export function EventDeleteDialog({
  lng,
  event,
  notifyOffered,
  onDelete,
  onClose,
}: EventDeleteDialogProps) {
  const { t } = useTranslation(lng);
  const [notify, setNotify] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const busy = useRef(false);
  const notifyId = useId();
  const remove = async () => {
    if (busy.current) return;
    busy.current = true;
    setDeleting(true);
    try {
      await onDelete(notifyOffered ? notify : undefined);
    } finally {
      busy.current = false;
      setDeleting(false);
    }
  };
  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('workbench.calendar.delete_title', {
              name: event.summary || t('workbench.calendar.no_title'),
            })}
          </DialogTitle>
          <DialogDescription>
            {t(
              event.recurring
                ? 'workbench.calendar.delete_occurrence'
                : 'workbench.calendar.delete_description'
            )}
          </DialogDescription>
        </DialogHeader>
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
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button variant="destructive" isLoading={deleting} onClick={() => void remove()}>
            {t('workbench.calendar.delete')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
