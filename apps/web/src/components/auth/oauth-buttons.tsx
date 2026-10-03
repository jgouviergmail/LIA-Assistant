'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/button';
import { GoogleMark } from '@/components/icons/BrandMarks';
import { logger } from '@/lib/logger';
import { useLoggingContext } from '@/lib/logging-context';
import { useTranslation } from 'react-i18next';
import { useAuthFeatures } from '@/hooks/useWebAuthn';
import { beginNativeSignIn, isNativeShell } from '@/lib/native/shell';

interface OAuthButtonsProps {
  mode?: 'login' | 'register';
}

/**
 * Sign in with an identity provider — when the instance offers it.
 *
 * A public demonstrator closes that route: accounts are created with an email
 * address and an explicit acceptance of the terms, which are what tell a
 * visitor everything is wiped nightly. Drawing a button that answers 404
 * would be worse than drawing none, so the component reads the instance's
 * published capabilities and renders nothing when the answer is no — or not
 * yet known, since a button appearing a beat later moves the form under the
 * reader's cursor.
 */
export function OAuthButtons({ mode = 'login' }: OAuthButtonsProps) {
  const { initiateGoogleOAuth } = useAuth();
  const { features } = useAuthFeatures();
  const { withContext } = useLoggingContext();
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false);

  const handleGoogleOAuth = async () => {
    try {
      setIsLoading(true);

      if (isNativeShell()) {
        /*
         * A WebView cannot host this: both engines are refused with
         * `disallowed_useragent`. The flow goes to the system browser and comes
         * back through a deep link carrying a code — bound to a verifier this
         * page keeps, because any application can claim that scheme.
         */
        const challenge = await beginNativeSignIn();
        await initiateGoogleOAuth(challenge);
        return;
      }

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

  if (!features?.federated_signin_enabled) return null;

  return (
    <div className="space-y-3">
      <Button
        type="button"
        variant="outline"
        className="w-full h-12 text-base"
        onClick={handleGoogleOAuth}
        disabled={isLoading}
      >
        <GoogleMark className="w-6 h-6 mr-3" />
        {mode === 'login'
          ? t('auth.oauth.continue_with_google')
          : t('auth.oauth.signup_with_google')}
      </Button>
    </div>
  );
}
