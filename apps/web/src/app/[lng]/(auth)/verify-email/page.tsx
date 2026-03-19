'use client';

import { useEffect, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { CheckCircle2, XCircle } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';
import { useTranslation } from 'react-i18next';

type VerificationStatus = 'loading' | 'success' | 'error';

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const { t } = useTranslation();
  const [status, setStatus] = useState<VerificationStatus>('loading');
  const [errorMessage, setErrorMessage] = useState<string>('');

  const token = searchParams.get('token');

  useEffect(() => {
    async function verifyEmail() {
      if (!token) {
        setStatus('error');
        setErrorMessage(t('auth.verify_email.error_missing_token'));
        return;
      }

      try {
        await apiClient.post(`/auth/verify-email?token=${encodeURIComponent(token)}`);
        setStatus('success');
      } catch (error: unknown) {
        setStatus('error');
        if (error instanceof Error) {
          // Try to extract message from API error
          const apiError = error as { message?: string };
          setErrorMessage(apiError.message || t('auth.verify_email.error_invalid_token'));
        } else {
          setErrorMessage(t('auth.verify_email.error_invalid_token'));
        }
      }
    }

    verifyEmail();
  }, [token, t]);

  if (status === 'loading') {
    return (
      <div className="text-center space-y-6">
        <div className="flex justify-center">
          <LoadingSpinner size="2xl" />
        </div>
        <h1 className="text-2xl font-bold">{t('auth.verify_email.loading_title')}</h1>
        <p className="text-muted-foreground">{t('auth.verify_email.loading_message')}</p>
      </div>
    );
  }

  if (status === 'success') {
    return (
      <div className="text-center space-y-6">
        <div className="flex justify-center">
          <CheckCircle2 className="h-16 w-16 text-green-500" />
        </div>
        <h1 className="text-2xl font-bold text-green-600">
          {t('auth.verify_email.success_title')}
        </h1>
        <p className="text-muted-foreground">{t('auth.verify_email.success_message')}</p>
        <p className="text-sm text-muted-foreground">{t('auth.verify_email.success_hint')}</p>
        <Button asChild className="mt-4">
          <Link href="/login">{t('auth.verify_email.back_to_login')}</Link>
        </Button>
      </div>
    );
  }

  // Error state
  return (
    <div className="text-center space-y-6">
      <div className="flex justify-center">
        <XCircle className="h-16 w-16 text-destructive" />
      </div>
      <h1 className="text-2xl font-bold text-destructive">{t('auth.verify_email.error_title')}</h1>
      <p className="text-muted-foreground">{errorMessage}</p>
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
        <Button variant="outline" asChild>
          <Link href="/login">{t('auth.verify_email.back_to_login')}</Link>
        </Button>
        <Button asChild>
          <Link href="/register">{t('auth.verify_email.create_account')}</Link>
        </Button>
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <div className="text-center space-y-6">
          <div className="flex justify-center">
            <LoadingSpinner size="2xl" />
          </div>
          <h1 className="text-2xl font-bold">Loading...</h1>
        </div>
      }
    >
      <VerifyEmailContent />
    </Suspense>
  );
}
