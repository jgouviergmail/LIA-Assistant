'use client';

/**
 * ConfideDialog — handing a thing to LIA as a ticket (ADR-372, ADR-276).
 *
 * The person's own act, a ticket like any other: the words arrive filled and stay theirs to change.
 * What LIA does with it runs on the board, under its rules; nothing here calls a model.
 */
import { useRef, useState, type FormEvent } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { workboardErrorCode } from '@/hooks/useWorkboard';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { workboardApi } from '@/lib/workboard/api';
import { workboardErrorKey } from '@/lib/workboard/errors';
import { CancelButton, ToolActions, ToolDialogHeader } from '../ToolForm';

export interface Confiding {
  title: string;
  brief: string;
}

export interface ConfideDialogProps extends Confiding {
  lng: Language;
  onClose: () => void;
}

export function ConfideDialog({ lng, title, brief, onClose }: ConfideDialogProps) {
  const { t } = useTranslation(lng);
  const [name, setName] = useState(title);
  const [words, setWords] = useState(brief);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submitButton = useRef<HTMLButtonElement>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || !name.trim()) return;
    setBusy(true);
    setRefusal(null);
    try {
      await workboardApi.create({
        title: name.trim(),
        description: words.trim() || null,
        assignee: 'lia',
      });
      toast.success(t('workbench.assist.confide.done'));
      onClose();
    } catch (refused: unknown) {
      setRefusal(workboardErrorKey(workboardErrorCode(refused)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent
        aria-describedby={undefined}
        className="sm:max-w-md"
        onOpenAutoFocus={event => {
          // The words are ready: a field in focus would open a phone's keyboard over them.
          event.preventDefault();
          submitButton.current?.focus();
        }}
      >
        <ToolDialogHeader>
          <DialogTitle>{t('workbench.assist.confide.title')}</DialogTitle>
        </ToolDialogHeader>
        <form className="space-y-3" onSubmit={event => void submit(event)}>
          <Input
            label={t('workbench.assist.confide.name')}
            value={name}
            onChange={event => setName(event.target.value)}
          />
          <Textarea
            label={t('workbench.assist.confide.brief')}
            rows={3}
            value={words}
            onChange={event => setWords(event.target.value)}
          />
          {refusal && (
            <p role="alert" className="text-sm text-destructive">
              {t(refusal)}
            </p>
          )}
          <ToolActions>
            <CancelButton lng={lng} onClick={onClose} />
            <Button ref={submitButton} type="submit" isLoading={busy}>
              {t('workbench.assist.confide.submit')}
            </Button>
          </ToolActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}
