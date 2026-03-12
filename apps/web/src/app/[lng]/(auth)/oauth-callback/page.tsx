'use client';

import { useEffect, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useTranslation } from 'react-i18next';

/**
 * OAuth Callback Page (BFF Pattern)
 *
 * With BFF Pattern, this page is primarily for error handling:
 * - Success case: Backend redirects directly to /dashboard with session cookie
 * - Error case: Google redirects here with error parameter
 *
 * This page should rarely be reached in the success flow.
 */
function OAuthCallbackContent() {
  const router = useLocalizedRouter();
  const searchParams = useSearchParams();
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const errorParam = searchParams.get('error');
    const errorDescription = searchParams.get('error_description');

    if (errorParam) {
      // OAuth error from provider
      setError(errorDescription || t('auth.oauth_callback.error'));
      setTimeout(() => router.push('/login'), 3000);
      return;
    }

    // If we reach here with no error, user was likely redirected by backend
    // Backend should have already set the session cookie and redirected to /dashboard
    // If user ended up here, redirect them to dashboard
    router.push('/dashboard');
  }, [searchParams, router, t]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center">
        {error ? (
          <div>
            <div className="text-red-600 text-lg mb-4">{error}</div>
            <div className="text-sm text-gray-600">{t('auth.oauth_callback.redirecting')}</div>
          </div>
        ) : (
          <div>
            <div className="animate-pulse text-lg text-gray-600 mb-4">
              {t('auth.oauth_callback.authenticating')}
            </div>
            <div className="text-sm text-gray-500">{t('auth.oauth_callback.please_wait')}</div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function OAuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-gray-50">
          <div className="animate-pulse text-lg text-gray-600">Loading...</div>
        </div>
      }
    >
      <OAuthCallbackContent />
    </Suspense>
  );
}
