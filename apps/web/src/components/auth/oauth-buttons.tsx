'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/button';
import { logger } from '@/lib/logger';
import { useLoggingContext } from '@/lib/logging-context';
import { useTranslation } from 'react-i18next';

interface OAuthButtonsProps {
  mode?: 'login' | 'register';
}

export function OAuthButtons({ mode = 'login' }: OAuthButtonsProps) {
  const { initiateGoogleOAuth } = useAuth();
  const { withContext } = useLoggingContext();
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false);

  const handleGoogleOAuth = async () => {
    try {
      setIsLoading(true);
      await initiateGoogleOAuth();
      // User will be redirected to Google, no need to handle response here
    } catch (error) {
      logger.error(
        'oauth_initiation_failed',
        error as Error,
        withContext({
          component: 'OAuthButtons',
          provider: 'google',
          mode,
        })
      );
      setIsLoading(false);
      toast.error(t('auth.oauth.error_title'), {
        description: t('auth.oauth.error_message'),
      });
    }
  };

  return (
    <div className="space-y-3">
      <Button
        type="button"
        variant="outline"
        className="w-full h-12 text-base"
        onClick={handleGoogleOAuth}
        disabled={isLoading}
      >
        <svg
          className="w-6 h-6 mr-3"
          viewBox="0 0 24 24"
          xmlns="http://www.w3.org/2000/svg"
          suppressHydrationWarning
        >
          <path
            d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
            fill="#4285F4"
          />
          <path
            d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            fill="#34A853"
          />
          <path
            d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
            fill="#FBBC05"
          />
          <path
            d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
            fill="#EA4335"
          />
        </svg>
        {mode === 'login'
          ? t('auth.oauth.continue_with_google')
          : t('auth.oauth.signup_with_google')}
      </Button>
    </div>
  );
}
