'use client';

import { ErrorPage } from '@/components/errors';

/** Error boundary of the « Tools » pages (Next.js App Router `error.tsx`). */
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
      titleKey="errors.workbench.title"
      messageKey="errors.workbench.message"
      componentName="WorkbenchErrorBoundary"
      showRefresh={false}
      secondaryActionKey="common.back_to_dashboard"
      secondaryActionHref="/dashboard"
    />
  );
}
