'use client';

/**
 * What a call to LIA tells beside its answer, where no panel holds it: what it cost, and why it
 * failed. A toast takes no room on a screen with little of it.
 */
import { useEffect } from 'react';
import { toast } from 'sonner';

import { LLMUsageBadge } from '@/components/ui/llm-usage-badge';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { LLMUsage } from '@/types/llm-usage';

import type { AssistState } from './useAssistCall';

/** What an answer that leaves its place cost: the page goes, the figure stays said. */
export function tellCost(usage: LLMUsage | null): void {
  if (usage) toast(<LLMUsageBadge usage={usage} />);
}

/**
 * @param lng - The reader's language.
 * @param state - The call that has no panel of its own to say it failed.
 */
export function useToldFailure<T>(lng: Language, state: AssistState<T>): void {
  const { t } = useTranslation(lng);
  useEffect(() => {
    if (state.status !== 'failed') return;
    toast.error(
      state.refusal ? t(state.refusal.key, state.refusal.values) : t('workbench.assist.failed')
    );
  }, [state, t]);
}
