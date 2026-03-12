'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useAuth } from '@/hooks/useAuth';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { logger } from '@/lib/logger';
import { useTranslation } from 'react-i18next';
import { getBrowserTimezone, formatTimezoneDisplay } from '@/utils/timezone';
import { getBrowserLanguageForBackend } from '@/utils/locale-mapping';
import {
  validatePassword,
  getPasswordRequirementChecks,
} from '@/lib/password-validation';
import { Check, X } from 'lucide-react';

export function RegisterForm() {
  const router = useLocalizedRouter();
  const { register } = useAuth();
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
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
        language || undefined
      );
      router.push('/dashboard');
    } catch (err) {
      logger.error('Register error', err as Error, {
        component: 'RegisterForm',
        email,
        timezone,
        language,
      });
      setError(t('auth.errors.registration_failed'));
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
                  req.met ? 'text-green-600' : 'text-gray-500'
                }`}
              >
                {req.met ? (
                  <Check className="h-3 w-3" />
                ) : (
                  <X className="h-3 w-3" />
                )}
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
            checked={rememberMe}
            onChange={e => setRememberMe(e.target.checked)}
            disabled={isLoading}
            className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
          />
          <label htmlFor="remember-me-register" className="ml-2 block text-sm text-gray-700">
            {t('auth.remember_me')}
          </label>
        </div>

        <Button type="submit" className="w-full" isLoading={isLoading}>
          {t('auth.register_button')}
        </Button>
      </form>
    </Card>
  );
}
