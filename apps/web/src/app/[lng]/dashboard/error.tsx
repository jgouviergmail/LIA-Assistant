'use client';

import { ErrorPage } from '@/components/errors';

/**
 * Error boundary for dashboard page
 * Follows Next.js 15 App Router error handling patterns
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorPage
      error={error}
      reset={reset}
      titleKey="errors.dashboard.title"
      messageKey="errors.dashboard.message"
      componentName="DashboardErrorBoundary"
    />
  );
}
