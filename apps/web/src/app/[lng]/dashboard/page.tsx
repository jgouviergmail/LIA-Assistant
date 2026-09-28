'use client';

import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useAuth';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useLanguageParam } from '@/hooks/useLanguageParam';
import { FeatureErrorBoundary } from '@/components/errors';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { TodayBriefing } from '@/components/dashboard/TodayBriefing';
import { ResultsSummary } from '@/components/dashboard/ResultsSummary';
import { UsageStatistics } from '@/components/dashboard/UsageStatistics';
import { RadioDashboardCard } from '@/components/radio/RadioDashboardCard';
import { usePersonalResults } from '@/hooks/usePersonalResults';
import { radioAvailable } from '@/lib/radio/availability';

/**
 * Today dashboard — the daily ritual home page.
 *
 * Layout (top → bottom):
 *   1. <TodayBriefing> — hero LIA + quick access + the page's lead-in + synthesis + 9-card
 *      grid; the lead-in is <RadioDashboardCard>, the personal radio where the instance
 *      offers it (ADR-324): under the quick-access bar, right above « My dashboard » —
 *      the one surface started every day (owner request)
 *   2. <ResultsSummary> — what the assistant ACHIEVED this cycle
 *   3. <UsageStatistics> — the volumes, folded behind a "Consumption" disclosure
 *
 * Results lead and consumption follows: messages, tokens, Google requests and
 * cost are what an administrator needs, not what a reader can act on.
 *
 * The configuration is read from the first render, without waiting for the
 * session: `/config` is public, and read after the session the radio's card
 * appeared one round trip after the dashboard and pushed « My dashboard » down.
 */
interface DashboardPageProps {
  params: Promise<{ lng: string }>;
}

export default function DashboardPage({ params }: DashboardPageProps) {
  const lng = useLanguageParam(params);
  const { user, isLoading } = useAuth();
  const { t, i18n } = useTranslation();
  const { results, firstLoad, error: resultsError } = usePersonalResults();
  const { config } = useAppConfig();

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
        <TodayBriefing
          aboveBriefing={<RadioDashboardCard lng={lng} enabled={radioAvailable(config)} />}
        />
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
