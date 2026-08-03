'use client';

import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useAuth';
import { FeatureErrorBoundary } from '@/components/errors';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { TodayBriefing } from '@/components/dashboard/TodayBriefing';
import { ResultsSummary } from '@/components/dashboard/ResultsSummary';
import { UsageStatistics } from '@/components/dashboard/UsageStatistics';
import { usePersonalResults } from '@/hooks/usePersonalResults';

/**
 * Today dashboard — the daily ritual home page.
 *
 * Layout (top → bottom):
 *   1. <TodayBriefing> — greeting + synthesis + hero LIA + quick access + 9-card grid
 *   2. <ResultsSummary> — what the assistant ACHIEVED this cycle
 *   3. <UsageStatistics> — the volumes, folded behind a "Consumption" disclosure
 *
 * Results lead and consumption follows: messages, tokens, Google requests and
 * cost are what an administrator needs, not what a reader can act on.
 */
export default function DashboardPage() {
  const { user, isLoading } = useAuth();
  const { t, i18n } = useTranslation();
  const { results, firstLoad, error: resultsError } = usePersonalResults();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60dvh]">
        <div className="flex flex-col items-center gap-3">
          <LoadingSpinner size="xl" />
          <p className="text-sm text-muted-foreground">{t('dashboard.loading')}</p>
        </div>
      </div>
    );
  }

  if (!user?.is_active) return null;

  return (
    <FeatureErrorBoundary feature="dashboard">
      <div className="space-y-10 sm:space-y-12">
        <TodayBriefing />
        <ResultsSummary
          results={results}
          firstLoad={firstLoad}
          error={resultsError}
          locale={i18n.language || 'fr'}
        />
        <UsageStatistics />
      </div>
    </FeatureErrorBoundary>
  );
}
