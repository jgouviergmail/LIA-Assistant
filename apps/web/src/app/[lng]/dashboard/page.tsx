'use client';

import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useAuth';
import { useLanguageParam } from '@/hooks/useLanguageParam';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { DashboardWorkspace } from '@/components/dashboard/DashboardWorkspace';

/**
 * Today dashboard — the daily ritual home page.
 *
 * Layout (top → bottom):
 *   1. <TodayBriefing> — date, welcome, personal radio, quick access, synthesis
 *      and the card grid; <RadioDashboardCard> appears where the instance offers
 *      it (ADR-324), immediately below the welcome.
 *   2. <ResultsSummary> — what the assistant ACHIEVED this cycle
 *   3. <UsageStatistics> — the volumes, folded behind a "Consumption" disclosure
 *
 * Results lead and consumption follows: messages, tokens, Google requests and
 * cost are what an administrator needs, not what a reader can act on.
 *
 * The page starts no configuration read of its own. The dashboard layout reads
 * `/config` from its first render, without waiting for the session (the
 * endpoint is public), and seeds every page under it with that answer
 * (`AppConfigSeedContext`): read after the session, the radio's card appeared
 * one round trip after the dashboard and pushed « My dashboard » down. The
 * dashboard body then reads its own (`useAppConfig`), starting from the seed.
 */
interface DashboardPageProps {
  params: Promise<{ lng: string }>;
}

export default function DashboardPage({ params }: DashboardPageProps) {
  const lng = useLanguageParam(params);
  const { user, isLoading } = useAuth();
  const { t } = useTranslation();

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

  return <DashboardWorkspace lng={lng} ownerId={user.id} />;
}
