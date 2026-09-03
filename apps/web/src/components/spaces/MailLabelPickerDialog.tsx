/**
 * Pick the Gmail label whose threads a space will index (ADR-262).
 *
 * A radio group, not a list of buttons: the choice is single and the keyboard
 * must move through it with the arrows, as a native group does. The privacy
 * sentence is part of the dialog, not a tooltip — linking a label copies
 * personal mail into a space.
 */

'use client';

import { useCallback, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Tag } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useGmailLabels } from '@/hooks/useMailSources';

interface MailLabelPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  spaceId: string;
  /** Labels already linked — offered, but not twice. */
  linkedLabelIds: string[];
  onSelect: (labelId: string, labelName: string) => void;
}

export function MailLabelPickerDialog({
  open,
  onOpenChange,
  spaceId,
  linkedLabelIds,
  onSelect,
}: MailLabelPickerDialogProps) {
  const { t } = useTranslation();
  const { labels, loading, error, refetch } = useGmailLabels(spaceId, open);
  const [selected, setSelected] = useState<string | null>(null);
  const groupId = useId();

  const available = labels.filter(label => !linkedLabelIds.includes(label.id));
  const chosen = available.find(label => label.id === selected) ?? null;

  const handleClose = useCallback(
    (isOpen: boolean) => {
      if (!isOpen) setSelected(null);
      onOpenChange(isOpen);
    },
    [onOpenChange]
  );

  // Not memoized on purpose: `chosen` is derived from the fetched list, and a
  // useCallback over it is exactly the shape the React compiler refuses to
  // preserve — for a handler that costs nothing to recreate.
  const handleConfirm = () => {
    if (!chosen) return;
    onSelect(chosen.id, chosen.name);
    setSelected(null);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('spaces.mail.picker_title')}</DialogTitle>
          <DialogDescription>{t('spaces.mail.picker_description')}</DialogDescription>
        </DialogHeader>

        <p className="rounded-md bg-muted/60 p-3 text-xs text-muted-foreground">
          {t('spaces.mail.privacy_note')}
        </p>

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('spaces.mail.picker_loading')}
          </div>
        ) : error ? (
          <div className="py-6 text-center">
            <p className="text-sm text-destructive">{t('spaces.mail.picker_error')}</p>
            <Button variant="outline" size="sm" className="mt-3" onClick={refetch}>
              {t('errors.try_again')}
            </Button>
          </div>
        ) : available.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {t('spaces.mail.picker_empty')}
          </p>
        ) : (
          <div
            role="radiogroup"
            aria-label={t('spaces.mail.picker_title')}
            className="max-h-72 space-y-1 overflow-y-auto pr-1"
          >
            {available.map(label => (
              <label
                key={label.id}
                className="flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-muted/60"
              >
                <input
                  type="radio"
                  name="gmail-label"
                  value={label.id}
                  checked={selected === label.id}
                  onChange={() => setSelected(label.id)}
                  // The wrapping <label> already names this control implicitly
                  // (valid per WCAG); the explicit reference makes the name
                  // visible to static analysis too (F012).
                  aria-labelledby={`${groupId}-${label.id}`}
                  className="h-4 w-4 accent-primary"
                />
                <Tag className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                <span id={`${groupId}-${label.id}`} className="truncate">
                  {label.name}
                </span>
              </label>
            ))}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => handleClose(false)}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleConfirm} disabled={!chosen}>
            {t('spaces.mail.picker_select')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
