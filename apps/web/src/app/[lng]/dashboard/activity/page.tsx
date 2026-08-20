'use client';

/**
 * `/dashboard/activity` — the proactive activity timeline.
 *
 * A thin route shell, exactly like the notifications page: the body lives
 * in `ActivityTimeline` so the page stays the routing concern and the
 * component stays testable without a router.
 */

import { ActivityTimeline } from '@/components/activity/ActivityTimeline';
import { FeatureErrorBoundary } from '@/components/errors';
import { useLanguageParam } from '@/hooks/useLanguageParam';

export default function ActivityPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);

  return (
    <FeatureErrorBoundary feature="activity">
      <ActivityTimeline lng={lng} />
    </FeatureErrorBoundary>
  );
}
