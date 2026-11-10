'use client';
import { useState, type ReactNode } from 'react';
import { useTranslation } from '@/i18n/client';
import type { AssistState } from '@/hooks/useAssistCall';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { X } from '@/lib/icons';
import type { Language } from '@/i18n/settings';
import { isDestination, type SelectionAction } from '@/lib/selection-assist/contracts';
import { AssistStars } from './AssistStars';

export function SelectionBubble({
  lng,
  action,
  onClose,
  children,
}: {
  lng: Language;
  action: SelectionAction;
  onClose: () => void;
  children: ReactNode;
}) {
  const { t } = useTranslation(lng);
  return (
    <>
      <div className="mb-3 flex items-center gap-2">
        <AssistStars className="h-4 w-4 shrink-0" aria-hidden="true" />
        <h2 className="flex-1 text-sm font-semibold">{t(`selectionAssist.actions.${action}`)}</h2>
        <Button
          data-selection-close=""
          type="button"
          variant="ghost"
          size="icon"
          aria-label={t('common.close')}
          onClick={onClose}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      {children}
    </>
  );
}

export function SelectionQuestion({
  lng,
  limit,
  onAsk,
}: {
  lng: Language;
  limit: number;
  onAsk: (question: string) => void;
}) {
  const { t } = useTranslation(lng);
  const [question, setQuestion] = useState('');
  return (
    <form
      className="space-y-3"
      onSubmit={event => {
        event.preventDefault();
        event.stopPropagation();
        if (question.trim()) onAsk(question);
      }}
    >
      <Textarea
        label={t('selectionAssist.question')}
        value={question}
        maxLength={limit}
        onChange={event => setQuestion(event.target.value)}
      />
      <Button type="submit" aria-disabled={!question.trim()}>
        {t('selectionAssist.send')}
      </Button>
    </form>
  );
}

/** A failed call stays a refusal; another paid attempt requires a new click. */
export function SelectionProgress<T>({
  lng,
  action,
  state,
  onRetry,
}: {
  lng: Language;
  action: SelectionAction;
  state: AssistState<T>;
  onRetry: () => void;
}) {
  const { t } = useTranslation(lng);
  if (state.status === 'running')
    return (
      <div
        role="status"
        aria-busy="true"
        className="flex min-h-12 items-center gap-2.5 rounded-lg bg-muted/50 px-3 py-2.5 text-xs leading-relaxed text-muted-foreground"
      >
        <LoadingSpinner
          size="default"
          role="presentation"
          aria-hidden="true"
          className="shrink-0 motion-reduce:animate-none"
        />
        <span>
          {t(
            action === 'read'
              ? 'selectionAssist.waiting_read'
              : isDestination(action)
                ? 'selectionAssist.waiting'
                : 'selectionAssist.waiting_answer'
          )}
        </span>
      </div>
    );
  if (state.status !== 'failed') return null;
  return (
    <div className="space-y-2">
      <p role="alert">
        {state.refusal ? t(state.refusal.key, state.refusal.values) : t('selectionAssist.failed')}
      </p>
      <Button type="button" variant="outline" onClick={onRetry}>
        {t('common.retry')}
      </Button>
    </div>
  );
}
