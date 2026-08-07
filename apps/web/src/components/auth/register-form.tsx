'use client';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { getLanguageFromPath, buildLocalizedPath } from '@/utils/i18n-path-utils';
import { useAuth } from '@/hooks/useAuth';
import { useAuthFeatures } from '@/hooks/useWebAuthn';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { logger } from '@/lib/logger';
import { useTranslation } from 'react-i18next';
import { getBrowserTimezone, formatTimezoneDisplay } from '@/utils/timezone';
import { getBrowserLanguageForBackend } from '@/utils/locale-mapping';
import { validatePassword, getPasswordRequirementChecks } from '@/lib/password-validation';
import { Check, X } from 'lucide-react';

/**
 * i18n key for a failed registration.
 *
 * The backend answers a structured `detail.error` rather than a sentence, so
 * an explicable refusal stays explicable in six languages. Anything else — a
 * network drop, a duplicate address, a 500 — keeps the generic message: a
 * visitor cannot act on those, and inventing a specific cause would be worse
 * than saying nothing precise.
 */
export function registrationErrorKey(error: unknown): string {
  const detail = (error as { data?: { detail?: { error?: unknown } } })?.data?.detail;
  const code = typeof detail?.error === 'string' ? detail.error : undefined;

  return code === 'demo_signup_limit_reached'
    ? 'auth.errors.demo_signup_limit_reached'
    : 'auth.errors.registration_failed';
}

export function RegisterForm() {
  const router = useLocalizedRouter();
  const pathname = usePathname();
  const currentLang = getLanguageFromPath(pathname);
  const { register } = useAuth();
  // A public demonstrator enforces the terms server-side; without this the
  // form cannot even ask, and every registration fails on `terms_accepted`.
  const { features } = useAuthFeatures();
  const termsRequired = features?.terms_required ?? false;
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [timezone, setTimezone] = useState<string | null>(null);
  const [language, setLanguage] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // Detect timezone and language on mount
  useEffect(() => {
    const detectedTimezone = getBrowserTimezone();
    if (detectedTimezone) {
      setTimezone(detectedTimezone);
      logger.info('Timezone detected', { timezone: detectedTimezone, component: 'RegisterForm' });
    }

    const detectedLanguage = getBrowserLanguageForBackend();
    if (detectedLanguage) {
      setLanguage(detectedLanguage);
      logger.info('Language detected', { language: detectedLanguage, component: 'RegisterForm' });
    }
  }, []);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError(t('auth.errors.passwords_mismatch'));
      return;
    }

    if (termsRequired && !termsAccepted) {
      setError(t('auth.errors.terms_not_accepted'));
      return;
    }

    const validationResult = validatePassword(password, t);
    if (!validationResult.isValid) {
      setError(validationResult.errors[0]);
      return;
    }

    setIsLoading(true);

    try {
      await register(
        email,
        password,
        name,
        rememberMe,
        timezone || undefined,
        language || undefined,
        termsRequired ? termsAccepted : undefined
      );
      router.push('/registration-success');
    } catch (err) {
      logger.error('Register error', err as Error, {
        component: 'RegisterForm',
        email,
        timezone,
        language,
      });
      // A refusal the visitor can act on must say so. Collapsing every failure
      // into "registration failed" told someone who hit the demonstrator's
      // daily ceiling nothing at all — not that it is full, not that it
      // reopens, not when. The backend ships a CODE; the sentence is resolved
      // here, in the visitor's language.
      setError(t(registrationErrorKey(err)));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card>
      <form onSubmit={handleSubmit} className="p-6 space-y-4">
        {error && (
          <div className="p-3 rounded-md bg-red-50 border border-red-200">
            <p className="text-sm text-red-800">{error}</p>
          </div>
        )}

        <Input
          label={t('auth.full_name_label')}
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder={t('auth.full_name_placeholder')}
          autoComplete="name"
          disabled={isLoading}
        />

        <Input
          label={t('auth.email_label')}
          type="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          placeholder={t('auth.email_placeholder')}
          required
          autoComplete="email"
          disabled={isLoading}
        />

        <Input
          label={t('auth.password_label')}
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          placeholder={t('auth.password_placeholder')}
          required
          autoComplete="new-password"
          disabled={isLoading}
        />

        {/* Password requirements checklist */}
        {password.length > 0 && (
          <div className="space-y-1 text-xs">
            {getPasswordRequirementChecks(password, t).map((req, idx) => (
              <div
                key={idx}
                className={`flex items-center gap-1.5 ${
                  req.met ? 'text-success' : 'text-muted-foreground'
                }`}
              >
                {req.met ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
                <span>{req.label}</span>
              </div>
            ))}
          </div>
        )}

        <Input
          label={t('auth.confirm_password_label')}
          type="password"
          value={confirmPassword}
          onChange={e => setConfirmPassword(e.target.value)}
          placeholder={t('auth.password_placeholder')}
          required
          autoComplete="new-password"
          disabled={isLoading}
        />

        {/* Timezone detection info */}
        {timezone && (
          <div className="p-2 text-xs text-gray-600 bg-gray-50 rounded">
            💡 {t('auth.timezone_detected')}: {formatTimezoneDisplay(timezone)}
          </div>
        )}

        {/* Remember Me checkbox */}
        <div className="flex items-center">
          <input
            id="remember-me-register"
            name="remember-me"
            type="checkbox"
            // aria-labelledby: same rationale as the login form (F012) — the
            // htmlFor/id association is real but invisible to static analysis.
            aria-labelledby="remember-me-register-label"
            checked={rememberMe}
            onChange={e => setRememberMe(e.target.checked)}
            disabled={isLoading}
            className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
          />
          <label
            id="remember-me-register-label"
            htmlFor="remember-me-register"
            className="ml-2 block text-sm text-gray-700"
          >
            {t('auth.remember_me')}
          </label>
        </div>

        {termsRequired && (
          <div className="flex items-start">
            <input
              id="terms-accepted-register"
              type="checkbox"
              // aria-labelledby: same rationale as the fields above (F012) —
              // the htmlFor/id association is real but invisible to static
              // analysis.
              aria-labelledby="terms-accepted-register-label"
              checked={termsAccepted}
              onChange={e => setTermsAccepted(e.target.checked)}
              disabled={isLoading}
              aria-required="true"
              className="mt-1 h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
            />
            <label
              id="terms-accepted-register-label"
              htmlFor="terms-accepted-register"
              className="ml-2 block text-sm text-gray-700"
            >
              {t('auth.terms.accept_prefix')}{' '}
              <Link
                href={buildLocalizedPath('/terms', currentLang)}
                target="_blank"
                rel="noopener noreferrer"
                className="underline underline-offset-4 hover:text-foreground"
              >
                {t('auth.terms.link_label')}
              </Link>
            </label>
          </div>
        )}

        <Button type="submit" className="w-full" isLoading={isLoading}>
          {t('auth.register_button')}
        </Button>

        <p className="text-xs text-center text-muted-foreground mt-3">
          {t('auth.register.terms_prefix')}{' '}
          <Link
            href={buildLocalizedPath('/terms', currentLang)}
            className="underline hover:text-foreground"
          >
            {t('auth.register.terms_link')}
          </Link>{' '}
          {t('auth.register.terms_and')}{' '}
          <Link
            href={buildLocalizedPath('/privacy', currentLang)}
            className="underline hover:text-foreground"
          >
            {t('auth.register.privacy_link')}
          </Link>
        </p>
      </form>
    </Card>
  );
}
