'use client';

import { useEffect, useRef, useState } from 'react';
import { KeyRound } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useAuth } from '@/hooks/useAuth';
import { useAuthFeatures, useWebAuthn } from '@/hooks/useWebAuthn';
import { isConditionalUIAvailable, isWebAuthnSupported } from '@/lib/webauthn';
import { logger } from '@/lib/logger';

/**
 * Passkey login entry point (security program D1, arbitration A1).
 *
 * Renders an explicit "Sign in with a passkey" button and, when the browser
 * supports conditional mediation, also arms the passkey autofill on the
 * login form's email field. Hidden entirely when the instance has MFA
 * disabled or the browser lacks WebAuthn.
 */
export function PasskeyLoginButton() {
  const { t } = useTranslation();
  const router = useLocalizedRouter();
  const { refreshUser } = useAuth();
  const { features } = useAuthFeatures();
  const { authenticateWithPasskey } = useWebAuthn();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const conditionalAbortRef = useRef<AbortController | null>(null);

  const available = Boolean(features?.mfa_enabled) && isWebAuthnSupported();

  const completeLogin = async () => {
    await refreshUser();
    router.push('/dashboard');
  };

  // Conditional UI: arm the passkey autofill once per mount. A cancelled or
  // unsupported conditional ceremony is silent — the explicit button remains.
  useEffect(() => {
    if (!available) return;
    let cancelled = false;
    const controller = new AbortController();
    conditionalAbortRef.current = controller;

    (async () => {
      if (!(await isConditionalUIAvailable()) || cancelled) return;
      try {
        await authenticateWithPasskey({ conditional: true, signal: controller.signal });
        if (!cancelled) await completeLogin();
      } catch {
        // Silent: abort on unmount, user dismissal, or timeout are all
        // normal outcomes for a conditional ceremony.
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
      conditionalAbortRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- arm once per availability change; ceremony helpers are stable
  }, [available]);

  if (!available) return null;

  const handleClick = async () => {
    setError('');
    setIsLoading(true);
    // The modal ceremony supersedes any armed conditional one.
    conditionalAbortRef.current?.abort();
    try {
      await authenticateWithPasskey();
      await completeLogin();
    } catch (err) {
      logger.error('Passkey login failed', err as Error, {
        component: 'PasskeyLoginButton',
      });
      setError(t('auth.passkey.login_error'));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-2">
      <Button
        type="button"
        variant="outline"
        className="w-full gap-2"
        onClick={handleClick}
        disabled={isLoading}
      >
        <KeyRound className="h-4 w-4" aria-hidden="true" />
        {isLoading ? t('auth.passkey.login_pending') : t('auth.passkey.login_button')}
      </Button>
      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400 text-center">
          {error}
        </p>
      )}
    </div>
  );
}
