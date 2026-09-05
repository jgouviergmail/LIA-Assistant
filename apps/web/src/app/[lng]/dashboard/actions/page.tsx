'use client';

/**
 * `/dashboard/actions` — the two transparency registers (ADR-263).
 *
 * A thin route shell, like the activity and notifications pages: the body
 * lives in `RegistersPage` so the page stays the routing concern and the
 * components stay testable without a router.
 *
 * The route keeps its name: it was already linked from the dashboard, and a
 * URL a user may have bookmarked is not renamed to match an internal split.
 */

import { RegistersPage } from '@/components/effects/RegistersPage';
import { FeatureErrorBoundary } from '@/components/errors';
import { useLanguageParam } from '@/hooks/useLanguageParam';

export default function ActionsPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);

  return (
    <FeatureErrorBoundary feature="effects-journal">
      <RegistersPage lng={lng} />
    </FeatureErrorBoundary>
  );
}
