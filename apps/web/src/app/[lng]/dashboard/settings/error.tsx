'use client';

import { ErrorPage } from '@/components/errors';

/**
 * Error boundary for dashboard settings page
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
      titleKey="errors.settings.title"
      messageKey="errors.settings.message"
      componentName="SettingsErrorBoundary"
      showRefresh={false}
      secondaryActionKey="common.back_to_dashboard"
      secondaryActionHref="/dashboard"
    />
  );
}
