'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Mail, CheckCircle2, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { apiClient } from '@/lib/api-client';
import { useTranslation, Trans } from 'react-i18next';

type Status = 'form' | 'loading' | 'success';

export default function ForgotPasswordPage() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<Status>('form');
  const [email, setEmail] = useState('');
  const [errorMessage, setErrorMessage] = useState<string>('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErrorMessage('');
    setStatus('loading');

    try {
      await apiClient.post('/auth/request-password-reset', { email });
      setStatus('success');
    } catch {
      // API always returns success to prevent email enumeration
      // but we still show success message
      setStatus('success');
    }
  }

  if (status === 'success') {
    return (
      <div className="text-center space-y-6">
        <div className="flex justify-center">
          <CheckCircle2 className="h-16 w-16 text-green-500" />
        </div>
        <h1 className="text-2xl font-bold">{t('auth.forgot_password.success_title')}</h1>
        <p className="text-muted-foreground">
          <Trans
            i18nKey="auth.forgot_password.success_message"
            values={{ email }}
            components={{ strong: <strong /> }}
          />
        </p>
        <p className="text-sm text-muted-foreground">{t('auth.forgot_password.success_hint')}</p>
        <Button asChild className="mt-4">
          <Link href="/login">{t('auth.forgot_password.back_to_login')}</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="text-center space-y-3">
        <div className="flex justify-center">
          <Mail className="h-12 w-12 text-primary" />
        </div>
        <h1 className="text-2xl font-bold">{t('auth.forgot_password.title')}</h1>
        <p className="text-muted-foreground">{t('auth.forgot_password.subtitle')}</p>
      </div>

      {errorMessage && (
        <div className="bg-destructive/10 text-destructive px-4 py-3 rounded-lg text-sm">
          {errorMessage}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email">{t('auth.forgot_password.email_label')}</Label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder={t('auth.forgot_password.email_placeholder')}
            required
          />
        </div>

        <Button type="submit" className="w-full" disabled={status === 'loading'}>
          {status === 'loading'
            ? t('auth.forgot_password.submitting')
            : t('auth.forgot_password.submit')}
        </Button>
      </form>

      <div className="text-center">
        <Link
          href="/login"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          {t('auth.forgot_password.back_to_login')}
        </Link>
      </div>
    </div>
  );
}
