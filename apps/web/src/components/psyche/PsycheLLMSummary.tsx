'use client';

import { Sparkles } from 'lucide-react';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useAuth } from '@/hooks/useAuth';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { Skeleton } from '@/components/ui/skeleton';

interface PsycheLLMSummaryProps {
  lng: Language;
  isOpen?: boolean;
  hideHeading?: boolean;
  refreshKey?: number;
  onGenerated?: () => void;
}

/** The visible point generates once per opening; ordinary rerenders never call the model. */
export function PsycheLLMSummary({
  lng,
  isOpen = true,
  hideHeading = false,
  refreshKey = 0,
  onGenerated,
}: PsycheLLMSummaryProps) {
  const { user } = useAuth();
  return (
    <OwnedSummary
      key={user?.id ?? 'anonymous'}
      lng={lng}
      isOpen={isOpen}
      hideHeading={hideHeading}
      refreshKey={refreshKey}
      onGenerated={onGenerated}
    />
  );
}
function OwnedSummary({
  lng,
  isOpen,
  hideHeading,
  refreshKey,
  onGenerated,
}: PsycheLLMSummaryProps & { isOpen: boolean; refreshKey: number }) {
  const { t } = useTranslation(lng);
  const { data, loading, error } = useApplicationAccountQuery<{ summary: string }>(
    '/psyche/summary',
    'PsycheLLMSummary',
    isOpen,
    onGenerated,
    { deps: [refreshKey] }
  );
  const text = data?.summary?.trim();
  const failed = !!error || (data !== undefined && !text);
  if (!isOpen) return null;
  return (
    <section
      aria-label={t('psyche.presentation.point')}
      aria-busy={loading}
      className="min-w-0 space-y-3"
    >
      {!hideHeading && (
        <h4 className="flex items-center gap-2 text-base font-semibold">
          <Sparkles className="size-5 shrink-0 text-primary" aria-hidden="true" />
          {t('psyche.presentation.point')}
        </h4>
      )}
      <div aria-live="polite" className="min-w-0 space-y-3">
        {text && (
          <p className="whitespace-pre-wrap text-sm leading-relaxed [overflow-wrap:anywhere]">
            {text}
          </p>
        )}
        {!data && !failed && (
          <Skeleton label={t('common.loading')} className="h-16 w-full rounded-lg" />
        )}
        {failed && (
          <p role="alert" className="text-sm leading-relaxed text-destructive">
            {t('psyche.summary.error')}
          </p>
        )}
      </div>
    </section>
  );
}
