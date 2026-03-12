'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { AlertTriangle } from 'lucide-react';
import { logger } from '@/lib/logger';
import { getLanguageFromPath, buildLocalizedPath } from '@/utils/i18n-path-utils';

interface ErrorPageProps {
  /** The error object from Next.js error boundary */
  error: Error & { digest?: string };
  /** Reset function to retry rendering */
  reset: () => void;
  /** i18n key for the error title */
  titleKey: string;
  /** i18n key for the error message */
  messageKey: string;
  /** Component name for logging */
  componentName: string;
  /** Show refresh page button (default: true) */
  showRefresh?: boolean;
  /** i18n key for secondary action button */
  secondaryActionKey?: string;
  /** URL for secondary action button */
  secondaryActionHref?: string;
}

/**
 * Reusable error page component for Next.js App Router error boundaries.
 *
 * Provides consistent error UI with i18n support and optional actions.
 *
 * @example
 * ```tsx
 * // In error.tsx
 * export default function Error({ error, reset }) {
 *   return (
 *     <ErrorPage
 *       error={error}
 *       reset={reset}
 *       titleKey="errors.dashboard.title"
 *       messageKey="errors.dashboard.message"
 *       componentName="DashboardErrorBoundary"
 *     />
 *   );
 * }
 * ```
 */
export function ErrorPage({
  error,
  reset,
  titleKey,
  messageKey,
  componentName,
  showRefresh = true,
  secondaryActionKey,
  secondaryActionHref,
}: ErrorPageProps) {
  const { t } = useTranslation();
  const pathname = usePathname();
  const currentLang = getLanguageFromPath(pathname);

  useEffect(() => {
    logger.error(`${componentName} error`, error, {
      component: componentName,
      digest: error.digest,
    });
  }, [error, componentName]);

  // Build localized URL for secondary action
  const localizedSecondaryHref = secondaryActionHref
    ? buildLocalizedPath(secondaryActionHref, currentLang)
    : undefined;

  return (
    <div className="container mx-auto py-8 px-4">
      <Card className="p-8 max-w-2xl mx-auto">
        <div className="text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/20 mb-4">
            <AlertTriangle className="h-8 w-8 text-red-600 dark:text-red-400" />
          </div>

          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">
            {t(titleKey)}
          </h2>

          <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">{t(messageKey)}</p>

          {process.env.NODE_ENV === 'development' && (
            <div className="mb-6 rounded-lg bg-gray-100 dark:bg-gray-800 p-4 text-left">
              <p className="text-xs font-mono text-gray-800 dark:text-gray-200 break-all">
                {error.message}
              </p>
              {error.digest && (
                <p className="mt-2 text-xs text-gray-600 dark:text-gray-400">
                  Error ID: {error.digest}
                </p>
              )}
            </div>
          )}

          <div className="flex justify-center gap-4">
            <Button onClick={reset} variant="default">
              {t('common.retry')}
            </Button>
            {showRefresh && (
              <Button onClick={() => window.location.reload()} variant="outline">
                {t('common.refresh_page')}
              </Button>
            )}
            {localizedSecondaryHref && secondaryActionKey && (
              <Button variant="outline" asChild>
                <Link href={localizedSecondaryHref}>{t(secondaryActionKey)}</Link>
              </Button>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
