'use client';

import { ErrorPage } from '@/components/errors';

/** Error boundary of the meetings pages (Next.js App Router `error.tsx`). */
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
      titleKey="errors.meetings.title"
      messageKey="errors.meetings.message"
      componentName="MeetingsErrorBoundary"
      showRefresh={false}
      secondaryActionKey="common.back_to_dashboard"
      secondaryActionHref="/dashboard"
    />
  );
}
