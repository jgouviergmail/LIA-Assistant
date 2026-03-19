'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useAuth } from '@/hooks/useAuth';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { logger } from '@/lib/logger';
import { useTranslation } from 'react-i18next';

export function LoginForm() {
  const router = useLocalizedRouter();
  const { login } = useAuth();
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await login(email, password, rememberMe);
      router.push('/dashboard');
    } catch (err) {
      logger.error('Login error', err as Error, {
        component: 'LoginForm',
        email,
      });
      setError(t('auth.errors.invalid_credentials'));
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
          autoComplete="current-password"
          disabled={isLoading}
        />

        {/* Remember Me checkbox and Forgot Password */}
        <div className="space-y-2">
          <div className="flex items-center">
            <input
              id="remember-me"
              name="remember-me"
              type="checkbox"
              checked={rememberMe}
              onChange={e => setRememberMe(e.target.checked)}
              disabled={isLoading}
              className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
            />
            <label
              htmlFor="remember-me"
              className="ml-2 block text-sm text-gray-700 dark:text-gray-300"
            >
              {t('auth.remember_me')}
            </label>
          </div>
          <Link
            href="/forgot-password"
            className="block text-sm text-primary hover:text-primary/80 transition-colors"
          >
            {t('auth.forgot_password_link')}
          </Link>
        </div>

        <Button type="submit" className="w-full" isLoading={isLoading}>
          {t('auth.login_button')}
        </Button>
      </form>
    </Card>
  );
}
