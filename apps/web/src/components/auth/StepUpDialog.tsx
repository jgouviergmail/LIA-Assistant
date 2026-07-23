'use client';

import { useCallback, useEffect, useState } from 'react';
import { KeyRound, ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import apiClient from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/hooks/useAuth';
import {
  isWebAuthnSupported,
  parseRequestOptions,
  serializeAuthenticationCredential,
} from '@/lib/webauthn';
import { logger } from '@/lib/logger';

interface StepUpStatus {
  methods: string[];
  password_set: boolean;
  step_up_valid_until: string | null;
}

interface StepUpDialogProps {
  open: boolean;
  onVerified: () => void;
  onCancel: () => void;
}

/**
 * Re-authentication dialog for sensitive actions (security program D1).
 *
 * Offers whichever methods the account supports — passkey (one tap),
 * password, TOTP/backup code, or a fresh sign-in with the account's
 * identity provider (the only method an OAuth-only account has before it
 * enrolls a first factor) — and reports success to the guard, which
 * replays the parked action.
 */
export function StepUpDialog({ open, onVerified, onCancel }: StepUpDialogProps) {
  const { t } = useTranslation();
  const { initiateGoogleOAuth } = useAuth();
  const [methods, setMethods] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!open) {
      setPassword('');
      setCode('');
      setError(false);
      setLoaded(false);
      return;
    }
    (async () => {
      try {
        const status = await apiClient.get<StepUpStatus>('/auth/step-up/status');
        setMethods(status.methods);
      } catch (err) {
        logger.error('Step-up status fetch failed', err as Error, {
          component: 'StepUpDialog',
        });
        setMethods(['password']);
      } finally {
        setLoaded(true);
      }
    })();
  }, [open]);

  const succeed = useCallback(() => {
    setError(false);
    onVerified();
  }, [onVerified]);

  const verifyPassword = async () => {
    setBusy(true);
    setError(false);
    try {
      await apiClient.post('/auth/step-up/password', { password });
      succeed();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };

  const verifyTotp = async () => {
    setBusy(true);
    setError(false);
    try {
      await apiClient.post('/auth/step-up/totp', { code: code.trim() });
      succeed();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };

  const verifyPasskey = async () => {
    setBusy(true);
    setError(false);
    try {
      const { options } = await apiClient.post<{ options: string }>(
        '/auth/step-up/webauthn/options'
      );
      const credential = (await navigator.credentials.get(
        parseRequestOptions(options)
      )) as PublicKeyCredential | null;
      if (!credential) throw new Error('cancelled');
      await apiClient.post('/auth/step-up/webauthn/verify', {
        credential: serializeAuthenticationCredential(credential),
      });
      succeed();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };

  // Signing in again with the identity provider IS the step-up for an
  // OAuth account: the fresh session opens the sudo window server-side.
  // Full-page redirect — the parked action is lost, the hint says to retry.
  const verifyWithGoogle = async () => {
    setBusy(true);
    setError(false);
    try {
      await initiateGoogleOAuth();
    } catch {
      setError(true);
      setBusy(false);
    }
  };

  const showPasskey = methods.includes('passkey') && isWebAuthnSupported();
  const showPassword = methods.includes('password');
  const showTotp = methods.includes('totp');
  const showGoogle = methods.includes('oauth_google');
  const nothingAvailable = loaded && !showPasskey && !showPassword && !showTotp && !showGoogle;

  return (
    <Dialog open={open} onOpenChange={isOpen => !busy && !isOpen && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-primary" aria-hidden="true" />
            {t('auth.stepUp.title')}
          </DialogTitle>
          <DialogDescription>{t('auth.stepUp.description')}</DialogDescription>
        </DialogHeader>

        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {t('auth.stepUp.error')}
          </p>
        )}

        <div className="space-y-4">
          {showPasskey && (
            <Button
              type="button"
              variant="outline"
              className="w-full gap-2"
              onClick={verifyPasskey}
              disabled={busy}
            >
              <KeyRound className="h-4 w-4" aria-hidden="true" />
              {t('auth.stepUp.passkey_button')}
            </Button>
          )}

          {showPassword && (
            <div className="space-y-2">
              <Input
                label={t('auth.stepUp.password_label')}
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
                disabled={busy}
              />
              <Button
                type="button"
                className="w-full"
                onClick={verifyPassword}
                disabled={busy || password.length === 0}
              >
                {t('auth.stepUp.password_submit')}
              </Button>
            </div>
          )}

          {showTotp && (
            <div className="space-y-2">
              <Input
                label={t('auth.stepUp.totp_label')}
                type="text"
                inputMode="numeric"
                value={code}
                onChange={e => setCode(e.target.value)}
                autoComplete="one-time-code"
                disabled={busy}
              />
              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={verifyTotp}
                disabled={busy || code.trim().length < 6}
              >
                {t('auth.stepUp.totp_submit')}
              </Button>
            </div>
          )}

          {showGoogle && (
            <div className="space-y-2">
              <Button
                type="button"
                variant="outline"
                className="w-full gap-2"
                onClick={verifyWithGoogle}
                disabled={busy}
              >
                <svg
                  className="h-4 w-4"
                  viewBox="0 0 24 24"
                  xmlns="http://www.w3.org/2000/svg"
                  aria-hidden="true"
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
                {t('auth.stepUp.oauth_google_button')}
              </Button>
              <p className="text-xs text-muted-foreground">{t('auth.stepUp.oauth_hint')}</p>
            </div>
          )}

          {nothingAvailable && (
            <p className="text-sm text-muted-foreground rounded-lg border border-dashed border-border px-4 py-4 text-center">
              {t('auth.stepUp.no_methods')}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
            {t('common.cancel')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
