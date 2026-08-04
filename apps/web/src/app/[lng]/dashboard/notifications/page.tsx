'use client';

/**
 * `/dashboard/notifications` — the hub.
 *
 * A thin route shell, exactly like the relations page: the body lives in
 * `NotificationsHub` so the page stays the routing concern and the component
 * stays testable without a router.
 */

import { FeatureErrorBoundary } from '@/components/errors';
import { NotificationsHub } from '@/components/notifications/NotificationsHub';
import { useLanguageParam } from '@/hooks/useLanguageParam';

export default function NotificationsPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);

  return (
    <FeatureErrorBoundary feature="notifications">
      <NotificationsHub lng={lng} />
    </FeatureErrorBoundary>
  );
}
