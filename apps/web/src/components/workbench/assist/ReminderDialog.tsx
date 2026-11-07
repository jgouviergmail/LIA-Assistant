'use client';

/**
 * ReminderDialog — « Remind me » from a tool (ADR-372, lot 1).
 *
 * The person keeps the words: they arrive filled and stay theirs to change. The moment is shown in
 * its field whichever way it was chosen, read on the account's wall as the route reads it, and one
 * press away for the common ones. A moment already gone is said here and sends nothing; a refusal
 * leaves everything as typed. It is the person's own act, a reminder like any other (ADR-268):
 * nothing here calls a model.
 */
import { useRef, useState, type FormEvent } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import apiClient from '@/lib/api-client';
import { isStillAhead, reminderInstant, remindChoices } from '@/lib/workbench/reminding';
import { CancelButton, ToolActions, ToolDialogHeader } from '../ToolForm';

export interface ReminderDialogProps {
  lng: Language;
  /** What the reminder will say. */
  words: string;
  /** The account's zone. */
  zone: string;
  onClose: () => void;
}

/** Tomorrow morning, the moment a thing left for later most often means. */
function firstChoice(zone: string): string {
  const choices = remindChoices(new Date(), zone);
  return choices.find(choice => choice.key === 'tomorrow')?.at ?? choices[0].at;
}

export function ReminderDialog({ lng, words, zone, onClose }: ReminderDialogProps) {
  const { t } = useTranslation(lng);
  const [content, setContent] = useState(words);
  const [moment, setMoment] = useState(() => firstChoice(zone));
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Set synchronously: a second press lands before the render that holds the button.
  const sending = useRef(false);
  const submitButton = useRef<HTMLButtonElement>(null);
  const said = content.trim();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (sending.current || !said) return;
    if (!isStillAhead(moment, new Date(), zone)) {
      setProblem('workbench.assist.remind.past');
      return;
    }
    sending.current = true;
    setBusy(true);
    setProblem(null);
    try {
      await apiClient.post('/reminders', {
        content: said,
        original_message: said,
        trigger_at: reminderInstant(moment),
      });
      toast.success(t('workbench.assist.remind.done'));
      onClose();
    } catch {
      setProblem('workbench.assist.remind.failed');
    } finally {
      sending.current = false;
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent
        aria-describedby={undefined}
        className="sm:max-w-md"
        onOpenAutoFocus={event => {
          // The words are ready: a field in focus would open a phone's keyboard over the moments.
          event.preventDefault();
          submitButton.current?.focus();
        }}
      >
        <ToolDialogHeader>
          <DialogTitle>{t('workbench.assist.remind.title')}</DialogTitle>
        </ToolDialogHeader>
        <form className="space-y-3" onSubmit={event => void submit(event)}>
          <Input
            label={t('workbench.assist.remind.what')}
            value={content}
            onChange={event => setContent(event.target.value)}
          />
          <div className="flex flex-wrap gap-1.5">
            {remindChoices(new Date(), zone).map(choice => (
              <Button
                key={choice.key}
                type="button"
                variant="outline"
                size="sm"
                className="h-8 px-2.5 text-xs"
                aria-pressed={moment === choice.at}
                onClick={() => setMoment(choice.at)}
              >
                {t(`workbench.assist.remind.choices.${choice.key}`)}
              </Button>
            ))}
          </div>
          <Input
            type="datetime-local"
            label={t('workbench.assist.remind.when')}
            value={moment}
            onChange={event => setMoment(event.target.value)}
          />
          {problem && (
            <p role="alert" className="text-sm text-destructive">
              {t(problem)}
            </p>
          )}
          <ToolActions>
            <CancelButton lng={lng} onClick={onClose} />
            <Button ref={submitButton} type="submit" isLoading={busy}>
              {t('workbench.assist.remind.submit')}
            </Button>
          </ToolActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}
