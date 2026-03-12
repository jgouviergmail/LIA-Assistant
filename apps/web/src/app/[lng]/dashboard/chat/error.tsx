'use client';

import { ErrorPage } from '@/components/errors';

/**
 * Error boundary for chat page
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
      titleKey="errors.chat.title"
      messageKey="errors.chat.message"
      componentName="ChatErrorBoundary"
      showRefresh={false}
      secondaryActionKey="common.back_to_dashboard"
      secondaryActionHref="/dashboard"
    />
  );
}
