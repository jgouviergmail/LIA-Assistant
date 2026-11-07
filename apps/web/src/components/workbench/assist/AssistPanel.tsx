'use client';

/**
 * AssistPanel — what LIA answered, in the detail it was asked from (ADR-372).
 *
 * It takes no room until it is asked for, and stands in the flow of the detail, so a phone keeps
 * the thing itself one scroll away. Whatever its state it can be closed, which stops what is on
 * its way. What it cost stands beside the words; what was already held says so and shows no figure.
 * The focus stays where the person left it: the answer is announced, never imposed. Closing it
 * gives the focus back to the icon it was asked from: its button leaves with it.
 */
import { X } from 'lucide-react';
import { useEffect, useRef, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import { LLMUsageBadge } from '@/components/ui/llm-usage-badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatEuro } from '@/lib/format';
import type { ReadAloudAnswer } from '@/lib/workbench/assist';
import type { LLMUsage } from '@/types/llm-usage';

import { AssistStars } from './AssistStars';
import type { AssistCall } from './useAssistCall';

export interface AssistPanelProps<T extends { usage: LLMUsage | null }> {
  lng: Language;
  title: string;
  call: AssistCall<T>;
  /** The answer, drawn. */
  children: (answer: T) => ReactNode;
  /** What it cost, where that is no count of tokens. */
  spent?: (answer: T) => ReactNode;
}

/** @returns The icon this panel was asked from, in the nearest bar around it. */
function askedFrom(panel: HTMLElement | null): HTMLElement | null {
  for (let around = panel?.parentElement ?? null; around; around = around.parentElement) {
    const icon = around.querySelector<HTMLElement>('[data-assist-trigger]');
    if (icon) return icon;
  }
  return null;
}

/** Words heard: a player the person holds, which a phone may ask them to start themselves. */
export function HeardWords({
  lng,
  label,
  answer,
}: {
  lng: Language;
  label: string;
  answer: ReadAloudAnswer;
}) {
  const { t } = useTranslation(lng);
  return (
    <>
      {/* A data: URL — the page's own bytes, no object URL to revoke (CSP media-src data:). */}
      <audio
        controls
        autoPlay
        aria-label={label}
        className="w-full"
        src={`data:audio/mpeg;base64,${answer.audio}`}
      />
      {answer.cut && (
        <p className="text-xs text-muted-foreground">{t('workbench.assist.voice.read_cut')}</p>
      )}
    </>
  );
}

/** What a voice cost; a free engine has nothing to say. */
export function VoiceCost({ lng, cost }: { lng: Language; cost: number }) {
  const { t } = useTranslation(lng);
  if (cost <= 0) return null;
  return (
    <p className="text-px-10 tabular-nums text-muted-foreground">
      {t('workbench.assist.voice.spent', { cost: formatEuro(cost, 6, lng) })}
    </p>
  );
}

/** Words LIA read out, and the sentence saying they stop short when they do. */
export function ReadWords({ text, cutNote }: { text: string; cutNote?: string | null }) {
  return (
    <>
      <p className="whitespace-pre-wrap break-words">{text}</p>
      {cutNote && <p className="text-xs text-muted-foreground">{cutNote}</p>}
    </>
  );
}

export function AssistPanel<T extends { usage: LLMUsage | null }>({
  lng,
  title,
  call,
  children,
  spent,
}: AssistPanelProps<T>) {
  const { t } = useTranslation(lng);
  const panel = useRef<HTMLElement>(null);
  const { state } = call;
  const shown = state.status !== 'idle';

  useEffect(() => {
    if (shown) panel.current?.scrollIntoView({ block: 'nearest' });
  }, [shown]);

  if (state.status === 'idle') return null;
  return (
    <section
      ref={panel}
      aria-label={title}
      className="space-y-2 rounded-md border bg-muted/30 p-3 text-sm"
    >
      <div className="flex items-center gap-2">
        <AssistStars className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        {/* No heading: it stands above the thing's own title, and the section is named already. */}
        <p className="min-w-0 flex-1 truncate text-xs font-semibold text-muted-foreground">
          {title}
        </p>
        <Button
          variant="ghost"
          size="icon"
          className="-my-1.5 -mr-1.5 h-8 w-8 shrink-0"
          aria-label={t('workbench.assist.close')}
          onClick={() => {
            const icon = askedFrom(panel.current);
            call.stop();
            icon?.focus();
          }}
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </Button>
      </div>
      {/* One live region for its whole life: what replaces the wait is read out too. */}
      <div role="status" className="space-y-2" aria-busy={state.status === 'running'}>
        {state.status === 'running' && (
          <>
            <span className="sr-only">{t('workbench.assist.reading')}</span>
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </>
        )}
        {state.status === 'failed' && (
          <>
            <p role="alert" className="text-destructive">
              {state.refusal
                ? t(state.refusal.key, state.refusal.values)
                : t('workbench.assist.failed')}
            </p>
            <Button variant="outline" size="sm" onClick={() => void call.retry()}>
              {t('workbench.states.retry')}
            </Button>
          </>
        )}
        {state.status === 'done' && (
          <>
            {children(state.value)}
            {spent && spent(state.value)}
            {!spent && state.value.usage && <LLMUsageBadge usage={state.value.usage} />}
            {!spent && !state.value.usage && (
              <p className="text-px-10 text-muted-foreground">{t('workbench.assist.held')}</p>
            )}
          </>
        )}
      </div>
    </section>
  );
}
