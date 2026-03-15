'use client';

import { ErrorPage } from '@/components/errors';

/**
 * Error boundary for RAG Spaces page.
 * Follows Next.js App Router error handling pattern.
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
      titleKey="errors.spaces.title"
      messageKey="errors.spaces.message"
      componentName="SpacesErrorBoundary"
      showRefresh={false}
      secondaryActionKey="common.back_to_dashboard"
      secondaryActionHref="/dashboard"
    />
  );
}
