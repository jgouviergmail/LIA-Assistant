'use client';

import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useAuth';
import { FeatureErrorBoundary } from '@/components/errors';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { TodayBriefing } from '@/components/dashboard/TodayBriefing';
import { UsageStatistics } from '@/components/dashboard/UsageStatistics';

/**
 * Today dashboard — the daily ritual home page.
 *
 * Layout (top → bottom):
 *   1. <TodayBriefing> — greeting + synthesis + hero LIA + quick access + 6-card grid
 *   2. <UsageStatistics> — billing cycle counters (preserved as-is)
 */
export default function DashboardPage() {
  const { user, isLoading } = useAuth();
  const { t } = useTranslation();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
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
        <UsageStatistics />
      </div>
    </FeatureErrorBoundary>
  );
}
