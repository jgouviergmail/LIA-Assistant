'use client';
import type { RefObject } from 'react';
import dynamic from 'next/dynamic';
import { LayoutDashboard } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import { FeatureErrorBoundary } from '@/components/errors';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { DashboardNavigate } from '@/components/dashboard/DashboardNavigation';
import { WorldActivityPanel } from './WorldActivityPanel';
import { useBriefing } from '@/hooks/useBriefing';

const Dashboard = dynamic(
  () =>
    import('@/components/dashboard/DashboardWorkspace').then(module => module.DashboardWorkspace),
  {
    ssr: false,
    loading: () => <Skeleton className="h-64 w-full" />,
  }
);
/** A stable modal host prevents chat's non-modal mode from remounting paid state. */
export function WorldDashboardPanel({
  lng,
  ownerId,
  active,
  suspended = false,
  opener,
  onClose,
  onBack,
  onNavigate,
}: {
  lng: Language;
  ownerId: string;
  active: boolean;
  suspended?: boolean;
  opener: RefObject<HTMLElement | null>;
  onClose(): void;
  onBack?: () => void;
  onNavigate: DashboardNavigate;
}) {
  const { t } = useTranslation(lng);
  // The visual tree suspends effects. Keep private invalidation listeners alive
  // here while its explicit enabled gate cancels all hidden transports.
  const briefing = useBriefing(active);
  return (
    <WorldActivityPanel
      lng={lng}
      ownerId={ownerId}
      open
      visible={active}
      suspended={suspended}
      title={t('world.dashboard.title')}
      icon={LayoutDashboard}
      opener={opener}
      onClose={onClose}
      onBack={onBack}
      fallbackToScene
    >
      <div className="h-full overflow-y-auto p-1">
        <FeatureErrorBoundary feature="world-dashboard">
          <Dashboard
            lng={lng}
            ownerId={ownerId}
            active={active}
            onNavigate={onNavigate}
            briefing={briefing}
          />
        </FeatureErrorBoundary>
      </div>
    </WorldActivityPanel>
  );
}
