'use client';

import { useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { CheckCircle2, XCircle, KeyRound, Eye, EyeOff, Check, X } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { apiClient } from '@/lib/api-client';
import { useTranslation } from 'react-i18next';
import { validatePassword, getPasswordRequirementChecks } from '@/lib/password-validation';

type ResetStatus = 'form' | 'loading' | 'success' | 'error';

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const { t } = useTranslation();
  const [status, setStatus] = useState<ResetStatus>('form');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const token = searchParams.get('token');

  // Check if token is missing
  if (!token && status === 'form') {
    return (
      <div className="text-center space-y-6">
        <div className="flex justify-center">
          <XCircle className="h-16 w-16 text-destructive" />
        </div>
        <h1 className="text-2xl font-bold text-destructive">
          {t('auth.reset_password.invalid_link_title')}
        </h1>
        <p className="text-muted-foreground">{t('auth.reset_password.invalid_link_message')}</p>
        <Button asChild>
          <Link href="/login">{t('auth.reset_password.back_to_login')}</Link>
        </Button>
      </div>
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    // Validate passwords match
    if (password !== confirmPassword) {
      setErrorMessage(t('auth.reset_password.error_mismatch'));
      setStatus('error');
      return;
    }

    // Validate password requirements
    const validationResult = validatePassword(password, t);
    if (!validationResult.isValid) {
      setErrorMessage(validationResult.errors[0]);
      setStatus('error');
      return;
    }

    setStatus('loading');

    try {
      await apiClient.post('/auth/reset-password', {
        token,
        new_password: password,
      });
      setStatus('success');
    } catch (error: unknown) {
      setStatus('error');
      if (error instanceof Error) {
        const apiError = error as { message?: string };
        setErrorMessage(apiError.message || t('auth.reset_password.error_invalid_token'));
      } else {
        setErrorMessage(t('auth.reset_password.error_invalid_token'));
      }
    }
  }

  if (status === 'success') {
    return (
      <div className="text-center space-y-6">
        <div className="flex justify-center">
          <CheckCircle2 className="h-16 w-16 text-green-500" />
        </div>
        <h1 className="text-2xl font-bold text-green-600">
          {t('auth.reset_password.success_title')}
        </h1>
        <p className="text-muted-foreground">{t('auth.reset_password.success_message')}</p>
        <Button asChild className="mt-4">
          <Link href="/login">{t('auth.reset_password.login_button')}</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="text-center space-y-3">
        <div className="flex justify-center">
          <KeyRound className="h-12 w-12 text-primary" />
        </div>
        <h1 className="text-2xl font-bold">{t('auth.reset_password.title')}</h1>
        <p className="text-muted-foreground">{t('auth.reset_password.subtitle')}</p>
      </div>

      {status === 'error' && (
        <div className="bg-destructive/10 text-destructive px-4 py-3 rounded-lg text-sm">
          {errorMessage}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="password">{t('auth.reset_password.new_password_label')}</Label>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder={t('auth.reset_password.new_password_placeholder')}
              required
              minLength={10}
              className="pr-10"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          {/* Password requirements checklist */}
          {password.length > 0 && (
            <div className="space-y-1 text-xs mt-2">
              {getPasswordRequirementChecks(password, t).map((req, idx) => (
                <div
                  key={idx}
                  className={`flex items-center gap-1.5 ${
                    req.met ? 'text-green-600' : 'text-muted-foreground'
                  }`}
                >
                  {req.met ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
                  <span>{req.label}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-2">
          <Label htmlFor="confirmPassword">{t('auth.reset_password.confirm_password_label')}</Label>
          <div className="relative">
            <Input
              id="confirmPassword"
              type={showConfirmPassword ? 'text' : 'password'}
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              placeholder={t('auth.reset_password.confirm_password_placeholder')}
              required
              minLength={10}
              className="pr-10"
            />
            <button
              type="button"
              onClick={() => setShowConfirmPassword(!showConfirmPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <Button type="submit" className="w-full" disabled={status === 'loading'}>
          {status === 'loading'
            ? t('auth.reset_password.submitting')
            : t('auth.reset_password.submit')}
        </Button>
      </form>

      <div className="text-center">
        <Link
          href="/login"
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          {t('auth.reset_password.back_to_login')}
        </Link>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col items-center justify-center space-y-4 py-8">
          <LoadingSpinner size="xl" />
          <p className="text-muted-foreground">Loading...</p>
        </div>
      }
    >
      <ResetPasswordForm />
    </Suspense>
  );
}
