'use client';

import { useHydrated } from '@/hooks/useHydrated';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useAuth } from '@/hooks/useAuth';
import { useTurnstileDoor } from '@/hooks/useTurnstileDoor';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { logger } from '@/lib/logger';
import { turnstileErrorKey } from '@/lib/turnstile';
import { useTranslation } from 'react-i18next';
import { TurnstileWidget } from './TurnstileWidget';

export function LoginForm() {
  const router = useLocalizedRouter();
  const { login, verifyMfa } = useAuth();
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  /*
   * Two-step login. The step is due whenever this is non-null; the token
   * inside it may legitimately be absent.
   *
   * A password login receives the pending token in the JSON answer and holds
   * it here. A PROVIDER sign-in cannot: its callback is a redirect, so the
   * token travels in an httpOnly cookie and the browser simply lands on
   * `?mfa=1`. Modelling "the step is due" and "we hold a token" as one nullable
   * token would have made the second case unrepresentable.
   */
  const [mfaStep, setMfaStep] = useState<{ token: string | null } | null>(null);
  const [mfaCode, setMfaCode] = useState('');
  const botCheck = useTurnstileDoor('login');

  /*
   * Read once, from `window.location` rather than `useSearchParams`: the hook
   * requires a <Suspense> boundary, and at prerender time the FALLBACK is what
   * ships in the static HTML — the sign-in form would be missing from the page
   * every visitor lands on. A single boolean read at mount costs nothing and
   * keeps the form in the document.
   */
  const hydrated = useHydrated();
  const [initialQueryRead, setInitialQueryRead] = useState(false);
  if (hydrated && !initialQueryRead) {
    setInitialQueryRead(true);
    if (new URLSearchParams(window.location.search).get('mfa') === '1') setMfaStep({ token: null });
  }
  useEffect(() => {
    if (hydrated && new URLSearchParams(window.location.search).get('mfa') === '1')
      window.history.replaceState(null, '', window.location.pathname);
  }, [hydrated]);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError('');
    if (!botCheck.ready) {
      setError(t('auth.turnstile.required'));
      return;
    }
    setIsLoading(true);

    try {
      const result = await login(email, password, rememberMe, botCheck.token);
      if (result.mfaRequired) {
        setMfaStep({ token: result.mfaToken ?? null });
        return;
      }
      router.push('/dashboard');
    } catch (err) {
      logger.error('Login error', err as Error, {
        component: 'LoginForm',
        email,
      });
      setError(t(turnstileErrorKey(err, botCheck.failed) ?? 'auth.errors.invalid_credentials'));
    } finally {
      setIsLoading(false);
      // The API spent the token, whatever it answered (ADR-364).
      botCheck.spent();
    }
  };

  const handleMfaSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!mfaStep) return;
    setError('');
    setIsLoading(true);

    try {
      await verifyMfa(mfaStep.token, mfaCode);
      router.push('/dashboard');
    } catch (err) {
      logger.error('MFA verification error', err as Error, {
        component: 'LoginForm',
      });
      // The pending token is single-use: a failed attempt requires a fresh
      // first step, so send the user back with a clear message.
      setMfaStep(null);
      setMfaCode('');
      setError(t('auth.mfa.invalid_code'));
    } finally {
      setIsLoading(false);
    }
  };

  if (mfaStep) {
    return (
      <Card>
        <form onSubmit={handleMfaSubmit} className="p-6 space-y-4">
          {error && (
            <div className="p-3 rounded-md bg-red-50 border border-red-200">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          <p className="text-sm text-muted-foreground">{t('auth.mfa.prompt')}</p>

          <Input
            label={t('auth.mfa.code_label')}
            type="text"
            inputMode="numeric"
            value={mfaCode}
            onChange={e => setMfaCode(e.target.value)}
            placeholder={t('auth.mfa.code_placeholder')}
            required
            autoComplete="one-time-code"
            autoFocus
            disabled={isLoading}
          />

          <Button type="submit" className="w-full" isLoading={isLoading}>
            {t('auth.mfa.verify_button')}
          </Button>

          <Button
            type="button"
            variant="ghost"
            className="w-full"
            onClick={() => {
              setMfaStep(null);
              setMfaCode('');
              setError('');
            }}
            disabled={isLoading}
          >
            {t('auth.mfa.back_to_login')}
          </Button>
        </form>
      </Card>
    );
  }

  return (
    <Card>
      <form onSubmit={handleSubmit} className="p-6 space-y-4">
        {error && (
          <div className="p-3 rounded-md bg-red-50 border border-red-200">
            <p className="text-sm text-red-800">{error}</p>
          </div>
        )}

        <Input
          label={t('auth.email_label')}
          type="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          placeholder={t('auth.email_placeholder')}
          required
          // "webauthn" arms the passkey conditional UI (autofill) on this
          // field when the browser supports it (security program D1, A1).
          autoComplete="username webauthn"
          disabled={isLoading}
        />

        <Input
          label={t('auth.password_label')}
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          placeholder={t('auth.password_placeholder')}
          required
          autoComplete="current-password"
          disabled={isLoading}
        />

        {/* Remember Me checkbox and Forgot Password */}
        <div className="space-y-2">
          <div className="flex items-center">
            <Checkbox
              id="remember-me"
              name="remember-me"
              // aria-labelledby: the htmlFor/id association below is real, but
              // static analysis cannot resolve it across elements (F012) — the
              // explicit reference makes the accessible name verifiable.
              aria-labelledby="remember-me-label"
              checked={rememberMe}
              onChange={e => setRememberMe(e.target.checked)}
              disabled={isLoading}
            />
            <label
              id="remember-me-label"
              htmlFor="remember-me"
              className="ml-2 block text-sm text-foreground"
            >
              {t('auth.remember_me')}
            </label>
          </div>
          <Link
            href="/forgot-password"
            className="block text-sm text-primary hover:text-primary/90 transition-colors"
          >
            {t('auth.forgot_password_link')}
          </Link>
        </div>

        {botCheck.siteKey && (
          <TurnstileWidget
            siteKey={botCheck.siteKey}
            action="login"
            onToken={botCheck.onToken}
            onFailure={botCheck.onFailure}
            resetSignal={botCheck.resetSignal}
          />
        )}

        <Button type="submit" className="w-full" isLoading={isLoading}>
          {t('auth.login_button')}
        </Button>
      </form>
    </Card>
  );
}
