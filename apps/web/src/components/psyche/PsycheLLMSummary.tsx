/**
 * PsycheLLMSummary — LLM-generated natural language summary of psyche state.
 *
 * Fetches a 2-3 sentence summary from GET /psyche/summary when the section
 * is opened. Shows a loading skeleton during generation (~1-2s).
 *
 * Phase: evolution — Psyche Engine (Iteration 2)
 * Created: 2026-04-01
 */

'use client';

import { Sparkles } from 'lucide-react';

import { useApiQuery } from '@/hooks/useApiQuery';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

interface PsycheSummaryData {
  summary: string;
}

interface PsycheLLMSummaryProps {
  lng: Language;
  /** Whether the parent section is open (triggers fetch). */
  isOpen: boolean;
  /** External refresh trigger — increment to re-fetch. */
  refreshKey?: number;
}

export function PsycheLLMSummary({ lng, isOpen, refreshKey = 0 }: PsycheLLMSummaryProps) {
  const { t } = useTranslation(lng, 'translation');

  const { data, loading, error } = useApiQuery<PsycheSummaryData>('/psyche/summary', {
    componentName: 'PsycheLLMSummary',
    enabled: isOpen,
    deps: [refreshKey],
  });

  return (
    <div className="rounded-lg border bg-gradient-to-br from-primary/5 to-primary/10 p-4">
      <div className="flex items-center gap-2 mb-2">
        <Sparkles className="h-4 w-4 text-primary" />
        <span className="text-sm font-semibold">{t('psyche.summary.title', 'Psyche State')}</span>
      </div>

      {loading && (
        <div className="space-y-2 animate-pulse">
          <div className="h-3 bg-muted rounded w-full" />
          <div className="h-3 bg-muted rounded w-5/6" />
          <div className="h-3 bg-muted rounded w-4/6" />
        </div>
      )}

      {!loading && error && (
        <p className="text-xs text-muted-foreground italic">
          {t('psyche.summary.error', 'Could not generate summary')}
        </p>
      )}

      {!loading && data?.summary && (
        <p className="text-sm text-foreground/90 leading-relaxed">{data.summary}</p>
      )}
    </div>
  );
}
