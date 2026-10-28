'use client';

import { Activity } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useAuth';
import { useAppConfig } from '@/hooks/useAppConfig';
import { usePersonalResults } from '@/hooks/usePersonalResults';
import { useBriefing, type UseBriefingResult } from '@/hooks/useBriefing';
import { FeatureErrorBoundary } from '@/components/errors';
import { RadioDashboardCard } from '@/components/radio/RadioDashboardCard';
import { radioAvailable } from '@/lib/radio/availability';
import type { Language } from '@/i18n/settings';
import { TodayBriefing } from './TodayBriefing';
import { ResultsSummary } from './ResultsSummary';
import { UsageStatistics } from './UsageStatistics';
import { DashboardNavigationProvider, type DashboardNavigate } from './DashboardNavigation';
import { MeetingNavigationProvider } from '@/components/meetings/MeetingNavigation';

/** One full native dashboard; Activity preserves edits while disconnecting hidden effects. */
interface DashboardWorkspaceProps {
  lng: Language;
  ownerId: string;
  active?: boolean;
  onNavigate?: DashboardNavigate;
  /** A retained host owns this controller outside its suspended presentation. */
  briefing?: UseBriefingResult;
}
export function DashboardWorkspace(props: DashboardWorkspaceProps) {
  const { user } = useAuth();
  if (user?.id !== props.ownerId || !user.is_active) return null;
  return props.briefing ? (
    <DashboardView {...props} briefing={props.briefing} />
  ) : (
    <DashboardWithBriefing {...props} />
  );
}
function DashboardWithBriefing(props: DashboardWorkspaceProps) {
  const briefing = useBriefing(props.active ?? true);
  return <DashboardView {...props} briefing={briefing} />;
}
function DashboardView({
  lng,
  ownerId,
  active = true,
  onNavigate,
  briefing,
}: DashboardWorkspaceProps & { briefing: UseBriefingResult }) {
  return (
    <Activity mode={active ? 'visible' : 'hidden'}>
      <DashboardNavigationProvider onNavigate={onNavigate}>
        <MeetingNavigationProvider
          onOpen={
            onNavigate
              ? id => {
                  onNavigate({ kind: 'meeting', id });
                }
              : undefined
          }
        >
          <DashboardBody key={ownerId} lng={lng} briefing={briefing} />
        </MeetingNavigationProvider>
      </DashboardNavigationProvider>
    </Activity>
  );
}

function DashboardBody({ lng, briefing }: { lng: Language; briefing: UseBriefingResult }) {
  const { i18n } = useTranslation();
  const { results, firstLoad, error } = usePersonalResults();
  const { config } = useAppConfig();
  return (
    <FeatureErrorBoundary feature="dashboard">
      <div className="dashboard-home space-y-10 sm:space-y-12">
        <TodayBriefing
          briefing={briefing}
          aboveBriefing={<RadioDashboardCard lng={lng} enabled={radioAvailable(config)} />}
        />
        <ResultsSummary
          results={results}
          firstLoad={firstLoad}
          error={error}
          locale={i18n.language || lng}
        />
        <UsageStatistics />
      </div>
    </FeatureErrorBoundary>
  );
}
