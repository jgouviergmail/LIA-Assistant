'use client';

/**
 * FileNameDialog — a name for a new folder or an item (ADR-369, lot 6).
 *
 * One name, never a path: what no drive takes is said here and sends nothing. A
 * name that did not change asks nothing. An act that did not go through leaves the
 * dialog open, the field keeping what was typed.
 */
import { useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { isOneName } from '@/lib/workbench/files';
import { CancelButton, ToolActions, ToolDialogHeader } from '../ToolForm';

export interface FileNameDialogProps {
  lng: Language;
  title: string;
  submitLabel: string;
  /** The name it starts from. */
  initial: string;
  /** The longest name the routes take. */
  maxLength: number | undefined;
  onClose: () => void;
  /** Whether the act went through: the dialog closes on it. */
  onSubmit: (name: string) => Promise<boolean>;
}

export function FileNameDialog({
  lng,
  title,
  submitLabel,
  initial,
  maxLength,
  onClose,
  onSubmit,
}: FileNameDialogProps) {
  const { t } = useTranslation(lng);
  const [name, setName] = useState(initial);
  const [busy, setBusy] = useState(false);
  const wanted = name.trim();
  const oneName = isOneName(wanted);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || !wanted || !oneName) return;
    if (wanted === initial) {
      onClose();
      return;
    }
    setBusy(true);
    if (await onSubmit(wanted)) onClose();
    else setBusy(false);
  };

  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent aria-describedby={undefined} className="sm:max-w-md">
        <ToolDialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </ToolDialogHeader>
        <form className="space-y-3" onSubmit={event => void submit(event)}>
          <Input
            aria-label={t('workbench.files.name_label')}
            aria-invalid={!oneName || undefined}
            value={name}
            maxLength={maxLength}
            onChange={event => setName(event.target.value)}
            autoFocus
          />
          {!oneName && (
            <p role="alert" className="text-sm text-destructive">
              {t('workbench.files.name_is_one')}
            </p>
          )}
          <ToolActions>
            <CancelButton lng={lng} onClick={onClose} />
            <Button type="submit" isLoading={busy}>
              {submitLabel}
            </Button>
          </ToolActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}
