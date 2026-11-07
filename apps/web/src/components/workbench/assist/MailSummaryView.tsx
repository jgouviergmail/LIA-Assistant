'use client';

/**
 * MailSummaryView — what a message says and asks, as the panel draws it (ADR-372).
 *
 * Plain text: what a model read in a stranger's message never becomes a link or markup here. An
 * action it found is one press from a task, which opens filled in its tool and saves nothing.
 */
import { ListPlus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { MailSummaryAnswer } from '@/lib/workbench/assist';

export interface MailSummaryViewProps {
  lng: Language;
  answer: MailSummaryAnswer;
  /** Makes a task of an action; left out without a tasks tool. */
  onTask?: (title: string) => void;
}

export function MailSummaryView({ lng, answer, onTask }: MailSummaryViewProps) {
  const { t } = useTranslation(lng);
  return (
    <div className="space-y-2">
      <p className="whitespace-pre-wrap break-words">{answer.gist}</p>
      {answer.key_points.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-4">
          {answer.key_points.map((point, index) => (
            <li key={index} className="break-words">
              {point}
            </li>
          ))}
        </ul>
      )}
      {answer.actions.length > 0 && (
        <section aria-label={t('workbench.assist.mail.to_do')} className="space-y-1">
          <p className="text-xs font-semibold text-muted-foreground">
            {t('workbench.assist.mail.to_do')}
          </p>
          <ul className="space-y-1">
            {answer.actions.map((action, index) => (
              <li key={index} className="flex items-start gap-1">
                <span className="min-w-0 flex-1 break-words">{action}</span>
                {onTask && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="-my-1 h-8 w-8 shrink-0"
                    aria-label={t('workbench.assist.mail.to_task', { action })}
                    title={t('workbench.assist.mail.to_task', { action })}
                    onClick={() => onTask(action)}
                  >
                    <ListPlus className="h-4 w-4" aria-hidden="true" />
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
